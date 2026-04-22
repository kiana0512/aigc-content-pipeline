from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .mapping_suggester import suggest_node_mapping
from .workflow_inspector import inspect_workflow

PLACEHOLDER_WORKFLOW_ERROR = (
    "Current workflow JSON is still a placeholder and cannot be patched. "
    "Please replace it with an actual ComfyUI-exported workflow first."
)

COMFYUI_MODEL_DIR_KEYS = {
    "checkpoints",
    "diffusion_models",
    "vae",
    "text_encoders",
    "clip_vision",
    "loras",
    "controlnet",
    "embeddings",
    "style_models",
    "upscale_models",
    "latent_upscale_models",
    "photomaker",
    "gligen",
    "hypernetworks",
    "audio_encoders",
    "diffusers",
    "vae_approx",
    "classifiers",
    "model_patches",
    "download_model_base",
}

# Project-level compatibility abstractions, not official ComfyUI terminology.
MODEL_FAMILY_DEFAULT_REQUIREMENTS: dict[str, dict[str, list[str]]] = {
    "classic_checkpoint": {
        "required": ["checkpoints"],
        "recommended": ["vae"],
        "optional": ["embeddings", "loras", "controlnet"],
    },
    "split_model": {
        "required": ["diffusion_models", "text_encoders", "vae"],
        "recommended": [],
        "optional": ["clip_vision", "embeddings", "loras", "controlnet"],
    },
    "conditioning": {
        "required": [],
        "recommended": ["controlnet", "clip_vision"],
        "optional": ["style_models", "photomaker", "gligen", "hypernetworks"],
    },
    "postprocess": {
        "required": [],
        "recommended": ["upscale_models", "latent_upscale_models"],
        "optional": [],
    },
    "media_extension": {
        "required": [],
        "recommended": ["audio_encoders"],
        "optional": [],
    },
}

MODEL_FAMILY_ABSTRACTION_NOTE = (
    "Workflow model families in this project are compatibility abstractions "
    "(`classic_checkpoint`, `split_model`, `conditioning`, `postprocess`, "
    "`media_extension`), not official ComfyUI terminology."
)


class ComfyUIAdapterError(ValueError):
    """Base exception for ComfyUI workflow patching errors."""


class PlaceholderWorkflowError(ComfyUIAdapterError):
    """Raised when current workflow file is still placeholder JSON."""


class NodeMappingError(ComfyUIAdapterError):
    """Raised when node mapping config is missing required fields."""


@dataclass
class WorkflowPatchParams:
    positive_prompt: str
    negative_prompt: str
    seed: int
    width: int
    height: int
    steps: int
    cfg: float
    sampler: str
    scheduler: str
    filename_prefix: str | None = None
    output_dir: str | None = None
    use_lora: bool = False
    lora_path: str = ""
    lora_strength: float = 1.0
    use_controlnet: bool = False
    controlnet_model_name: str = ""
    controlnet_strength: float = 0.8
    control_image_path: str = ""


def normalize_model_family_name(family: str | None) -> str:
    value = str(family or "classic_checkpoint").strip().lower()
    aliases = {
        "classic": "classic_checkpoint",
        "checkpoint": "classic_checkpoint",
        "checkpoint_family": "classic_checkpoint",
        "split": "split_model",
        "split_models": "split_model",
        "split_model_family": "split_model",
        "conditioning_family": "conditioning",
        "postprocess_family": "postprocess",
        "media": "media_extension",
        "media_family": "media_extension",
    }
    canonical = aliases.get(value, value)
    if canonical not in MODEL_FAMILY_DEFAULT_REQUIREMENTS:
        supported = ", ".join(sorted(MODEL_FAMILY_DEFAULT_REQUIREMENTS.keys()))
        raise ComfyUIAdapterError(
            f"Unsupported workflow model family: `{value}`. Supported: {supported}"
        )
    return canonical


def resolve_model_dir_requirements(
    model_family: str | None,
    declared_required: list[str] | None = None,
    declared_recommended: list[str] | None = None,
    declared_optional: list[str] | None = None,
) -> dict[str, Any]:
    family = normalize_model_family_name(model_family)
    defaults = MODEL_FAMILY_DEFAULT_REQUIREMENTS[family]

    required = _sanitize_model_dir_keys(defaults["required"], label="default_required")
    recommended = _sanitize_model_dir_keys(
        defaults.get("recommended", []), label="default_recommended"
    )
    optional = _sanitize_model_dir_keys(defaults["optional"], label="default_optional")

    required.extend(_sanitize_model_dir_keys(declared_required or [], label="required"))
    recommended.extend(
        _sanitize_model_dir_keys(declared_recommended or [], label="recommended")
    )
    optional.extend(_sanitize_model_dir_keys(declared_optional or [], label="optional"))

    required_unique = _unique_items(required)
    recommended_unique = [
        item for item in _unique_items(recommended) if item not in required_unique
    ]
    optional_unique = [
        item
        for item in _unique_items(optional)
        if item not in required_unique and item not in recommended_unique
    ]

    return {
        "model_family": family,
        "required": required_unique,
        "recommended": recommended_unique,
        "optional": optional_unique,
    }


def validate_model_directory_requirements(
    model_folders: dict[str, str],
    requirements: dict[str, Any],
    strict: bool = False,
) -> dict[str, Any]:
    required = _sanitize_model_dir_keys(
        requirements.get("required", []), label="requirements.required"
    )
    recommended = _sanitize_model_dir_keys(
        requirements.get("recommended", []), label="requirements.recommended"
    )
    optional = _sanitize_model_dir_keys(
        requirements.get("optional", []), label="requirements.optional"
    )

    missing_required = [
        key for key in required if not str(model_folders.get(key, "")).strip()
    ]
    missing_recommended = [
        key for key in recommended if not str(model_folders.get(key, "")).strip()
    ]
    missing_optional = [
        key for key in optional if not str(model_folders.get(key, "")).strip()
    ]

    if strict and missing_required:
        raise ComfyUIAdapterError(
            "Missing required ComfyUI model directory declarations: "
            + ", ".join(missing_required)
        )

    return {
        "required": required,
        "recommended": recommended,
        "optional": optional,
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
        "missing_optional": missing_optional,
    }


def load_workflow_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        workflow = json.load(f)
    validate_workflow_json(workflow)
    return workflow


def load_node_mapping(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        mapping = yaml.safe_load(f)

    if not isinstance(mapping, dict):
        raise NodeMappingError(
            f"Node mapping file must be a YAML dictionary, got: {type(mapping)!r}"
        )
    validate_node_mapping(mapping)
    return mapping


def save_workflow_json(workflow: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(workflow, f, ensure_ascii=False, indent=2)
    return path


def validate_workflow_json(workflow: dict[str, Any]) -> None:
    if not isinstance(workflow, dict):
        raise ComfyUIAdapterError(
            f"Workflow JSON must be a dictionary object, got: {type(workflow)!r}"
        )

    if is_placeholder_workflow(workflow):
        raise PlaceholderWorkflowError(PLACEHOLDER_WORKFLOW_ERROR)

    if "nodes" in workflow and isinstance(workflow["nodes"], list):
        raise ComfyUIAdapterError(
            "Workflow JSON appears to be ComfyUI UI format (`nodes` list). "
            "Please export using 'Save (API Format)' for patching."
        )

    prompt_graph = _extract_prompt_graph(workflow)
    if not _is_comfyui_prompt_graph(prompt_graph):
        raise ComfyUIAdapterError(
            "Workflow JSON is not a recognized ComfyUI API prompt format. "
            "Please provide an actual ComfyUI-exported API workflow JSON."
        )


def is_placeholder_workflow(workflow: dict[str, Any]) -> bool:
    status = workflow.get("status")
    if isinstance(status, dict) and bool(status.get("is_placeholder")):
        return True

    placeholder_keys = {"workflow_name", "workflow_type", "planned_nodes"}
    if placeholder_keys.intersection(workflow.keys()) and not _is_comfyui_prompt_graph(
        workflow
    ):
        return True
    return False


def validate_node_mapping(mapping: dict[str, Any]) -> None:
    required_section = mapping.get("required")
    if not isinstance(required_section, dict):
        raise NodeMappingError(
            "Node mapping must include a `required` section with node bindings."
        )

    expected_fields: dict[str, tuple[str, ...]] = {
        "positive_prompt": ("node_id", "input_key"),
        "negative_prompt": ("node_id", "input_key"),
        "latent_size": ("node_id", "width_key", "height_key"),
        "sampler": (
            "node_id",
            "seed_key",
            "steps_key",
            "cfg_key",
            "sampler_key",
            "scheduler_key",
        ),
    }
    missing: list[str] = []
    for section_name, keys in expected_fields.items():
        section = required_section.get(section_name)
        if not isinstance(section, dict):
            missing.append(f"required.{section_name}")
            continue
        for key in keys:
            if not str(section.get(key, "")).strip():
                missing.append(f"required.{section_name}.{key}")

    if missing:
        raise NodeMappingError(
            "Node mapping is missing required fields: " + ", ".join(missing)
        )


def patch_workflow(
    workflow: dict[str, Any],
    mapping: dict[str, Any] | None,
    params: WorkflowPatchParams,
    mapping_mode: str = "manual_map",
) -> dict[str, Any]:
    patched, _ = patch_workflow_with_report(
        workflow=workflow,
        mapping=mapping,
        params=params,
        mapping_mode=mapping_mode,
    )
    return patched


def patch_workflow_with_report(
    workflow: dict[str, Any],
    mapping: dict[str, Any] | None,
    params: WorkflowPatchParams,
    mapping_mode: str = "manual_map",
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_workflow_json(workflow)
    mode = str(mapping_mode or "manual_map").strip().lower()
    if mode not in {"manual_map", "auto_detect"}:
        raise ComfyUIAdapterError(
            f"Unsupported mapping mode: `{mapping_mode}`. "
            "Use `manual_map` or `auto_detect`."
        )

    if mode == "manual_map":
        if not isinstance(mapping, dict):
            raise NodeMappingError(
                "manual_map mode requires a valid node mapping dictionary."
            )
        patched = _patch_workflow_manual(workflow, mapping, params)
        report = {
            "mapping_mode": "manual_map",
            "patched_fields": [
                "positive_prompt",
                "negative_prompt",
                "seed",
                "width",
                "height",
                "steps",
                "cfg",
                "sampler",
                "scheduler",
            ],
            "skipped_fields": [],
            "unresolved_fields": [],
            "missing_model_references": [],
            "custom_node_notes": [],
            "mapping_source": "manual_node_map",
        }
        return patched, report

    return _patch_workflow_auto_detect(workflow=workflow, mapping_override=mapping, params=params)


def _patch_workflow_manual(
    workflow: dict[str, Any],
    mapping: dict[str, Any],
    params: WorkflowPatchParams,
) -> dict[str, Any]:
    validate_node_mapping(mapping)

    workflow_copy = copy.deepcopy(workflow)
    prompt_graph = _extract_prompt_graph(workflow_copy)
    required = mapping["required"]

    _set_input(
        prompt_graph,
        required["positive_prompt"]["node_id"],
        required["positive_prompt"]["input_key"],
        params.positive_prompt,
        label="positive_prompt",
    )
    _set_input(
        prompt_graph,
        required["negative_prompt"]["node_id"],
        required["negative_prompt"]["input_key"],
        params.negative_prompt,
        label="negative_prompt",
    )

    latent_mapping = required["latent_size"]
    _set_input(
        prompt_graph,
        latent_mapping["node_id"],
        latent_mapping["width_key"],
        int(params.width),
        label="width",
    )
    _set_input(
        prompt_graph,
        latent_mapping["node_id"],
        latent_mapping["height_key"],
        int(params.height),
        label="height",
    )

    sampler_mapping = required["sampler"]
    _set_input(
        prompt_graph,
        sampler_mapping["node_id"],
        sampler_mapping["seed_key"],
        int(params.seed),
        label="seed",
    )
    _set_input(
        prompt_graph,
        sampler_mapping["node_id"],
        sampler_mapping["steps_key"],
        int(params.steps),
        label="steps",
    )
    _set_input(
        prompt_graph,
        sampler_mapping["node_id"],
        sampler_mapping["cfg_key"],
        float(params.cfg),
        label="cfg",
    )
    _set_input(
        prompt_graph,
        sampler_mapping["node_id"],
        sampler_mapping["sampler_key"],
        params.sampler,
        label="sampler",
    )
    _set_input(
        prompt_graph,
        sampler_mapping["node_id"],
        sampler_mapping["scheduler_key"],
        params.scheduler,
        label="scheduler",
    )

    _patch_save_image(prompt_graph, mapping, params)
    _patch_lora(prompt_graph, mapping, params)
    _patch_controlnet(prompt_graph, mapping, params)
    return workflow_copy


def _patch_workflow_auto_detect(
    workflow: dict[str, Any],
    mapping_override: dict[str, Any] | None,
    params: WorkflowPatchParams,
) -> tuple[dict[str, Any], dict[str, Any]]:
    workflow_copy = copy.deepcopy(workflow)
    prompt_graph = _extract_prompt_graph(workflow_copy)
    inspection = inspect_workflow(workflow_copy)
    suggestion = suggest_node_mapping(
        inspection_result=inspection,
        existing_mapping=mapping_override if isinstance(mapping_override, dict) else None,
    )
    auto_mapping = suggestion["mapping"]
    confidence = suggestion.get("confidence", {})

    report = {
        "mapping_mode": "auto_detect",
        "patched_fields": [],
        "skipped_fields": [],
        "unresolved_fields": [],
        "missing_model_references": [],
        "custom_node_notes": [
            f"node {item.get('node_id')} / {item.get('class_type')}: {item.get('reason')}"
            for item in inspection.get("unresolved_nodes", [])
        ],
        "needs_manual_confirmation": suggestion.get("needs_manual_confirmation", []),
        "detected_mapping": auto_mapping,
        "diff_vs_existing_mapping": suggestion.get("diff_vs_existing", {}),
        "workflow_inspection": {
            "workflow_format": inspection.get("workflow_format"),
            "node_count": inspection.get("node_count"),
            "detected_model_families": inspection.get("detected_model_families", []),
            "suggested_model_family": inspection.get("suggested_model_family"),
        },
    }

    required = auto_mapping.get("required", {})
    override_paths = _collect_non_empty_mapping_paths(mapping_override)

    _auto_patch_required_field(
        prompt_graph=prompt_graph,
        confidence=confidence,
        override_paths=override_paths,
        mapping_path="required.positive_prompt",
        node_id=str(required.get("positive_prompt", {}).get("node_id", "")),
        input_key=str(required.get("positive_prompt", {}).get("input_key", "")),
        value=params.positive_prompt,
        label="positive_prompt",
        report=report,
    )
    _auto_patch_required_field(
        prompt_graph=prompt_graph,
        confidence=confidence,
        override_paths=override_paths,
        mapping_path="required.negative_prompt",
        node_id=str(required.get("negative_prompt", {}).get("node_id", "")),
        input_key=str(required.get("negative_prompt", {}).get("input_key", "")),
        value=params.negative_prompt,
        label="negative_prompt",
        report=report,
    )

    latent = required.get("latent_size", {})
    _auto_patch_required_field(
        prompt_graph=prompt_graph,
        confidence=confidence,
        override_paths=override_paths,
        mapping_path="required.latent_size",
        node_id=str(latent.get("node_id", "")),
        input_key=str(latent.get("width_key", "")),
        value=int(params.width),
        label="width",
        report=report,
    )
    _auto_patch_required_field(
        prompt_graph=prompt_graph,
        confidence=confidence,
        override_paths=override_paths,
        mapping_path="required.latent_size",
        node_id=str(latent.get("node_id", "")),
        input_key=str(latent.get("height_key", "")),
        value=int(params.height),
        label="height",
        report=report,
    )

    sampler = required.get("sampler", {})
    _auto_patch_required_field(
        prompt_graph=prompt_graph,
        confidence=confidence,
        override_paths=override_paths,
        mapping_path="required.sampler",
        node_id=str(sampler.get("node_id", "")),
        input_key=str(sampler.get("seed_key", "")),
        value=int(params.seed),
        label="seed",
        report=report,
    )
    _auto_patch_required_field(
        prompt_graph=prompt_graph,
        confidence=confidence,
        override_paths=override_paths,
        mapping_path="required.sampler",
        node_id=str(sampler.get("node_id", "")),
        input_key=str(sampler.get("steps_key", "")),
        value=int(params.steps),
        label="steps",
        report=report,
    )
    _auto_patch_required_field(
        prompt_graph=prompt_graph,
        confidence=confidence,
        override_paths=override_paths,
        mapping_path="required.sampler",
        node_id=str(sampler.get("node_id", "")),
        input_key=str(sampler.get("cfg_key", "")),
        value=float(params.cfg),
        label="cfg",
        report=report,
    )
    _auto_patch_required_field(
        prompt_graph=prompt_graph,
        confidence=confidence,
        override_paths=override_paths,
        mapping_path="required.sampler",
        node_id=str(sampler.get("node_id", "")),
        input_key=str(sampler.get("sampler_key", "")),
        value=params.sampler,
        label="sampler",
        report=report,
    )
    _auto_patch_required_field(
        prompt_graph=prompt_graph,
        confidence=confidence,
        override_paths=override_paths,
        mapping_path="required.sampler",
        node_id=str(sampler.get("node_id", "")),
        input_key=str(sampler.get("scheduler_key", "")),
        value=params.scheduler,
        label="scheduler",
        report=report,
    )

    _patch_save_image(prompt_graph, auto_mapping, params)
    _patch_lora(prompt_graph, auto_mapping, params)
    _patch_controlnet(prompt_graph, auto_mapping, params)

    return workflow_copy, report


def patch_workflow_from_paths(
    workflow_path: str | Path,
    node_map_path: str | Path | None,
    params: WorkflowPatchParams,
    mapping_mode: str = "manual_map",
) -> dict[str, Any]:
    workflow = load_workflow_json(workflow_path)
    mapping = load_node_mapping(node_map_path) if node_map_path else None
    return patch_workflow(
        workflow=workflow,
        mapping=mapping,
        params=params,
        mapping_mode=mapping_mode,
    )


def _patch_save_image(
    prompt_graph: dict[str, Any],
    mapping: dict[str, Any],
    params: WorkflowPatchParams,
) -> None:
    save_mapping = mapping.get("optional", {}).get("save_image", {})
    if not isinstance(save_mapping, dict) or not save_mapping:
        return

    node_id = str(save_mapping.get("node_id", "")).strip()
    if not node_id:
        return

    filename_prefix_key = str(save_mapping.get("filename_prefix_key", "")).strip()
    output_dir_key = str(save_mapping.get("output_dir_key", "")).strip()

    if params.filename_prefix and filename_prefix_key:
        _set_input(
            prompt_graph,
            node_id,
            filename_prefix_key,
            params.filename_prefix,
            label="filename_prefix",
        )

    # output_dir patching is best-effort and considered experimental.
    if params.output_dir:
        if output_dir_key:
            _set_input(
                prompt_graph,
                node_id,
                output_dir_key,
                params.output_dir,
                label="output_dir",
            )
        elif filename_prefix_key and params.filename_prefix:
            merged_prefix = str(
                PurePosixPath(params.output_dir) / PurePosixPath(params.filename_prefix)
            )
            _set_input(
                prompt_graph,
                node_id,
                filename_prefix_key,
                merged_prefix,
                label="output_dir_via_filename_prefix",
            )


def _patch_lora(
    prompt_graph: dict[str, Any],
    mapping: dict[str, Any],
    params: WorkflowPatchParams,
) -> None:
    lora_mapping = mapping.get("optional", {}).get("lora", {})
    if not isinstance(lora_mapping, dict):
        return

    node_id = str(lora_mapping.get("node_id", "")).strip()
    enabled_key = str(lora_mapping.get("enabled_key", "")).strip()
    path_key = str(lora_mapping.get("path_key", "")).strip()
    strength_key = str(lora_mapping.get("strength_key", "")).strip()

    if not params.use_lora:
        if node_id and enabled_key:
            _set_input(prompt_graph, node_id, enabled_key, False, label="lora_disabled")
        return

    if not node_id:
        raise ComfyUIAdapterError(
            "LoRA is enabled in config but node mapping `optional.lora.node_id` is not set."
        )
    if not path_key:
        raise NodeMappingError(
            "LoRA is enabled but mapping `optional.lora.path_key` is missing."
        )
    if not params.lora_path.strip():
        raise ComfyUIAdapterError(
            "LoRA is enabled but `lora_path` is empty. "
            "Please set `lora.path` (or legacy `model.lora_path`) in config."
        )

    _set_input(prompt_graph, node_id, path_key, params.lora_path, label="lora_path")
    if strength_key:
        _set_input(
            prompt_graph,
            node_id,
            strength_key,
            float(params.lora_strength),
            label="lora_strength",
        )
    if enabled_key:
        _set_input(prompt_graph, node_id, enabled_key, True, label="lora_enabled")


def _patch_controlnet(
    prompt_graph: dict[str, Any],
    mapping: dict[str, Any],
    params: WorkflowPatchParams,
) -> None:
    control_mapping = mapping.get("optional", {}).get("controlnet", {})
    if not isinstance(control_mapping, dict):
        return

    enabled_key = str(control_mapping.get("enabled_key", "")).strip()
    enabled_node_id = str(control_mapping.get("enabled_node_id", "")).strip()

    if not params.use_controlnet:
        if enabled_node_id and enabled_key:
            _set_input(
                prompt_graph,
                enabled_node_id,
                enabled_key,
                False,
                label="controlnet_disabled",
            )
        return

    model_node_id = str(control_mapping.get("model_node_id", "")).strip()
    model_key = str(control_mapping.get("model_key", "")).strip()
    strength_node_id = str(control_mapping.get("strength_node_id", "")).strip()
    strength_key = str(control_mapping.get("strength_key", "")).strip()
    image_node_id = str(control_mapping.get("image_node_id", "")).strip()
    image_key = str(control_mapping.get("image_key", "")).strip()

    missing = []
    if not model_node_id:
        missing.append("optional.controlnet.model_node_id")
    if not model_key:
        missing.append("optional.controlnet.model_key")
    if not strength_node_id:
        missing.append("optional.controlnet.strength_node_id")
    if not strength_key:
        missing.append("optional.controlnet.strength_key")
    if not image_node_id:
        missing.append("optional.controlnet.image_node_id")
    if not image_key:
        missing.append("optional.controlnet.image_key")
    if missing:
        raise ComfyUIAdapterError(
            "ControlNet is enabled in config but mapping is incomplete: "
            + ", ".join(missing)
        )
    if not params.controlnet_model_name.strip():
        raise ComfyUIAdapterError(
            "ControlNet is enabled but `controlnet_model_name` is empty."
        )
    if not params.control_image_path.strip():
        raise ComfyUIAdapterError(
            "ControlNet is enabled but `control_image_path` is empty."
        )

    _set_input(
        prompt_graph,
        model_node_id,
        model_key,
        params.controlnet_model_name,
        label="controlnet_model",
    )
    _set_input(
        prompt_graph,
        strength_node_id,
        strength_key,
        float(params.controlnet_strength),
        label="controlnet_strength",
    )
    _set_input(
        prompt_graph,
        image_node_id,
        image_key,
        params.control_image_path,
        label="control_image_path",
    )
    if enabled_node_id and enabled_key:
        _set_input(
            prompt_graph,
            enabled_node_id,
            enabled_key,
            True,
            label="controlnet_enabled",
        )


def _auto_patch_required_field(
    prompt_graph: dict[str, Any],
    confidence: dict[str, str],
    override_paths: set[str],
    mapping_path: str,
    node_id: str,
    input_key: str,
    value: Any,
    label: str,
    report: dict[str, Any],
) -> None:
    level = str(confidence.get(mapping_path, "low")).lower()
    has_override = mapping_path in override_paths
    if level != "high" and not has_override:
        report["skipped_fields"].append(
            f"{label} (low_confidence={level}, mapping_path={mapping_path})"
        )
        return
    if not node_id or not input_key:
        report["unresolved_fields"].append(
            f"{label} (missing mapping fields at {mapping_path})"
        )
        return

    try:
        _set_input(
            prompt_graph=prompt_graph,
            node_id=node_id,
            input_key=input_key,
            value=value,
            label=label,
        )
        report["patched_fields"].append(label)
    except (ComfyUIAdapterError, NodeMappingError) as exc:
        report["unresolved_fields"].append(f"{label}: {exc}")


def _collect_non_empty_mapping_paths(mapping: dict[str, Any] | None) -> set[str]:
    if not isinstance(mapping, dict):
        return set()
    paths: set[str] = set()

    def walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, sub in value.items():
                sub_path = f"{prefix}.{key}" if prefix else str(key)
                walk(sub_path, sub)
            return
        if value is None:
            return
        if isinstance(value, str) and not value.strip():
            return
        if prefix:
            parts = prefix.split(".")
            if len(parts) >= 2:
                paths.add(".".join(parts[:2]))

    walk("", mapping)
    return paths


def _set_input(
    prompt_graph: dict[str, Any],
    node_id: str | int,
    input_key: str,
    value: Any,
    label: str,
) -> None:
    node_id_key = str(node_id).strip()
    if node_id_key not in prompt_graph:
        raise ComfyUIAdapterError(
            f"Cannot patch `{label}`: node id `{node_id_key}` not found in workflow."
        )

    node = prompt_graph[node_id_key]
    if not isinstance(node, dict):
        raise ComfyUIAdapterError(
            f"Cannot patch `{label}`: node `{node_id_key}` is not a dictionary."
        )

    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        raise ComfyUIAdapterError(
            f"Cannot patch `{label}`: node `{node_id_key}` does not have `inputs`."
        )

    if not str(input_key).strip():
        raise NodeMappingError(f"Cannot patch `{label}`: input key is empty.")

    inputs[input_key] = value


def _extract_prompt_graph(workflow: dict[str, Any]) -> dict[str, Any]:
    if _is_comfyui_prompt_graph(workflow):
        return workflow

    prompt = workflow.get("prompt")
    if isinstance(prompt, dict) and _is_comfyui_prompt_graph(prompt):
        return prompt
    return {}


def _is_comfyui_prompt_graph(data: dict[str, Any]) -> bool:
    if not isinstance(data, dict) or not data:
        return False

    digit_keys = [key for key in data.keys() if str(key).isdigit()]
    if not digit_keys:
        return False

    for key in digit_keys:
        node = data[key]
        if not isinstance(node, dict):
            return False
        if "class_type" not in node:
            return False
        if not isinstance(node.get("inputs"), dict):
            return False
    return True


def _sanitize_model_dir_keys(items: list[str], label: str) -> list[str]:
    out: list[str] = []
    for item in items:
        key = str(item).strip()
        if not key:
            continue
        if key not in COMFYUI_MODEL_DIR_KEYS:
            supported = ", ".join(sorted(COMFYUI_MODEL_DIR_KEYS))
            raise ComfyUIAdapterError(
                f"Unknown model directory key in `{label}`: `{key}`. Supported: {supported}"
            )
        out.append(key)
    return out


def _unique_items(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
