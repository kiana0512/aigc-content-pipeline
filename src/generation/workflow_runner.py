from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml
from .comfyui_adapter import (
    COMFYUI_MODEL_DIR_KEYS,
    MODEL_FAMILY_ABSTRACTION_NOTE,
    resolve_model_dir_requirements,
    validate_model_directory_requirements,
)
from .mapping_suggester import suggest_node_mapping
from .model_resolver import build_model_resolution_report
from .workflow_inspector import inspect_workflow_path

POSITIVE_PROMPT_ALIASES = [
    "positive_prompt",
    "positive_prompt_text",
    "prompt",
    "prompt_text",
    "text",
]
NEGATIVE_PROMPT_ALIASES = [
    "negative_prompt",
    "negative_prompt_text",
    "neg_prompt",
    "negative",
    "negative_text",
]
FILENAME_PREFIX_ALIASES = [
    "filename_prefix",
    "output_prefix",
    "file_prefix",
]
SEED_ALIASES = [
    "seed",
    "runtime_seed",
]


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_prompt_pack_csv(path: str | Path) -> list[dict[str, str]]:
    path = Path(path)
    with path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [_normalize_prompt_row(row, row_index=i) for i, row in enumerate(rows, start=1)]


def build_run_manifest(
    config: dict[str, Any],
    prompt_rows: list[dict[str, str]],
    *,
    config_path: str = "",
    prompt_pack_path: str = "",
    workflow_path: str = "",
    workflow_defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project_cfg = config.get("project", {})
    task_cfg = config.get("task", {})
    model_cfg = config.get("model", {})
    runtime_cfg = config.get("runtime", {})
    generation_cfg = config.get("generation", {})
    lora_cfg = config.get("lora", {}) or {}
    defaults = workflow_defaults or {}
    steps_value = generation_cfg.get(
        "num_inference_steps",
        generation_cfg.get("steps", 30),
    )
    cfg_value = generation_cfg.get(
        "guidance_scale",
        generation_cfg.get("cfg", 7.0),
    )
    sampler_value = generation_cfg.get(
        "sampler",
        generation_cfg.get("sampler_name", "unknown_sampler"),
    )
    filename_prefix_value = str(generation_cfg.get("filename_prefix", "")).strip()

    manifest: dict[str, Any] = {
        "config_path": str(config_path).strip(),
        "prompt_pack_path": str(prompt_pack_path).strip(),
        "workflow_path": str(workflow_path).strip(),
        "project_name": project_cfg.get("name", "unknown_project"),
        "task_type": task_cfg.get("type", "unknown_task"),
        "asset_type": task_cfg.get("asset_type", "unknown_asset"),
        "scenario": task_cfg.get("scenario", "unknown_scenario"),
        "model_family": model_cfg.get("family", "unknown_family"),
        "base_model_name": model_cfg.get("base_model_name", "unknown_model"),
        "seed": runtime_cfg.get("seed", 42),
        "width": generation_cfg.get("width", 1024),
        "height": generation_cfg.get("height", 1024),
        "batch_size": generation_cfg.get("batch_size", 1),
        "num_inference_steps": steps_value,
        "guidance_scale": cfg_value,
        "sampler": sampler_value,
        "scheduler": generation_cfg.get("scheduler", "unknown_scheduler"),
        "denoise": generation_cfg.get("denoise", 1.0),
        "filename_prefix": filename_prefix_value,
        "lora_name": str(lora_cfg.get("path", model_cfg.get("lora_path", ""))).strip(),
        "lora_strength_model": float(
            lora_cfg.get("strength", model_cfg.get("lora_strength", 1.0))
        ),
        "output_subdir": generation_cfg.get("output_subdir", "outputs/placeholder"),
        "parameter_sources": {
            "seed": "config.runtime.seed",
            "width": "config.generation.width",
            "height": "config.generation.height",
            "batch_size": "config.generation.batch_size",
            "num_inference_steps": "config.generation.num_inference_steps|steps",
            "guidance_scale": "config.generation.guidance_scale|cfg",
            "sampler": "config.generation.sampler|sampler_name",
            "scheduler": "config.generation.scheduler",
            "denoise": "config.generation.denoise",
            "filename_prefix": "config.generation.filename_prefix",
        },
        "items": [],
    }

    default_positive = str(generation_cfg.get("prompt", "")).strip()
    default_negative = str(generation_cfg.get("negative_prompt", "")).strip()
    workflow_default_positive = str(defaults.get("positive_prompt", "")).strip()
    workflow_default_negative = str(defaults.get("negative_prompt", "")).strip()
    for index, row in enumerate(prompt_rows, start=1):
        item_id = str(row.get("id", "")).strip() or str(index)
        positive_prompt = str(row.get("positive_prompt", "")).strip()
        positive_source = str(row.get("positive_prompt_source", "")).strip()
        if not positive_prompt:
            if default_positive:
                positive_prompt = default_positive
                positive_source = "config.generation.prompt"
            elif workflow_default_positive:
                positive_prompt = workflow_default_positive
                positive_source = "workflow_default.positive_prompt"
            else:
                positive_source = "missing"

        negative_prompt = str(row.get("negative_prompt", "")).strip()
        negative_source = str(row.get("negative_prompt_source", "")).strip()
        negative_explicit = bool(row.get("negative_prompt_explicit", False))
        if not negative_explicit and not negative_prompt:
            if default_negative:
                negative_prompt = default_negative
                negative_source = "config.generation.negative_prompt"
            elif workflow_default_negative:
                negative_prompt = workflow_default_negative
                negative_source = "workflow_default.negative_prompt"
            else:
                negative_source = "missing"
        elif negative_explicit and not negative_source:
            negative_source = "prompt_pack.negative_prompt(empty)"

        filename_prefix = str(row.get("filename_prefix", "")).strip()
        filename_prefix_source = str(row.get("filename_prefix_source", "")).strip()
        if filename_prefix and not filename_prefix_source:
            filename_prefix_source = "prompt_pack.filename_prefix"
        if not filename_prefix_source:
            filename_prefix_source = "defer_to_config_or_runtime"

        item_seed = runtime_cfg.get("seed", 42)
        item_seed_source = "config.runtime.seed"
        row_seed = str(row.get("seed", "")).strip()
        if row_seed:
            try:
                item_seed = int(row_seed)
                item_seed_source = str(row.get("seed_source", "prompt_pack.seed")).strip() or (
                    "prompt_pack.seed"
                )
            except ValueError:
                item_seed_source = "config.runtime.seed(fallback_from_invalid_prompt_pack.seed)"

        manifest["items"].append(
            {
                "id": item_id,
                "item_id": item_id,
                "item_index": index,
                "prompt_row_index": int(row.get("prompt_row_index", 0) or 0),
                "prompt_row_id": str(row.get("prompt_row_id", row.get("id", ""))),
                "subject": str(row.get("subject", "")),
                "style": str(row.get("style", "")),
                "attributes": str(row.get("attributes", "")),
                "positive_prompt": positive_prompt,
                "negative_prompt": negative_prompt,
                "positive_prompt_source": positive_source,
                "negative_prompt_source": negative_source,
                "negative_prompt_explicit": negative_explicit,
                "filename_prefix": filename_prefix,
                "filename_prefix_source": filename_prefix_source,
                "seed": int(item_seed),
                "seed_source": item_seed_source,
                "lora_name": str(row.get("lora_name", "")).strip(),
                "lora_strength_model": str(row.get("lora_strength_model", "")).strip(),
                "patched_workflow_path": "",
                "patch_report_path": "",
            }
        )

    return manifest


def save_manifest_json(manifest: dict[str, Any], output_json: str | Path) -> Path:
    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)

    with output_json.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return output_json


def resolve_comfyui_settings(config: dict[str, Any]) -> dict[str, Any]:
    comfyui_cfg = config.get("comfyui", {}) or {}
    generation_cfg = config.get("generation", {}) or {}
    model_cfg = config.get("model", {}) or {}
    lora_cfg = config.get("lora", {}) or {}
    controlnet_cfg = config.get("controlnet", {}) or {}

    use_lora = bool(
        lora_cfg.get("enabled", False) or model_cfg.get("use_lora", False)
    )
    lora_path = str(lora_cfg.get("path", "") or model_cfg.get("lora_path", ""))
    lora_strength = float(
        lora_cfg.get("strength", lora_cfg.get("strength_model", 1.0))
    )

    use_controlnet = bool(
        controlnet_cfg.get("enabled", False) or model_cfg.get("use_controlnet", False)
    )
    controlnet_model_name = str(
        controlnet_cfg.get("model_name", "") or model_cfg.get("controlnet_model_name", "")
    )
    controlnet_strength = float(controlnet_cfg.get("strength", 0.8))
    control_image_path = str(controlnet_cfg.get("control_image_path", ""))

    return {
        "enabled": bool(comfyui_cfg.get("enabled", False)),
        "base_url": str(comfyui_cfg.get("base_url", "http://127.0.0.1:8188")),
        "run_name": str(comfyui_cfg.get("run_name", "")),
        "mode": str(comfyui_cfg.get("mode", "manifest")),
        "mapping_mode": str(comfyui_cfg.get("mapping_mode", "manual_map")),
        "workflow_json": str(comfyui_cfg.get("workflow_json", "")),
        "node_map": str(comfyui_cfg.get("node_map", "")),
        "comfyui_root": str(comfyui_cfg.get("comfyui_root", "ComfyUI")),
        "workflow_import": comfyui_cfg.get("workflow_import", {}) or {},
        "model_resolution_policy": comfyui_cfg.get("model_resolution_policy", {}) or {},
        "report_output_dirs": comfyui_cfg.get("report_output_dirs", {}) or {},
        "save_patched_workflows_dir": str(
            comfyui_cfg.get("save_patched_workflows_dir", "results/patched_workflows")
        ),
        "patch_save_image_output_dir": bool(
            comfyui_cfg.get("patch_save_image_output_dir", False)
        ),
        "save_image_output_dir": str(comfyui_cfg.get("save_image_output_dir", "")),
        "output_subdir": str(generation_cfg.get("output_subdir", "outputs/placeholder")),
        "batch_size": int(generation_cfg.get("batch_size", 1)),
        "denoise": float(generation_cfg.get("denoise", 1.0)),
        "use_lora": use_lora,
        "lora_path": lora_path,
        "lora_name": lora_path,
        "lora_strength": lora_strength,
        "lora_strength_model": lora_strength,
        "use_controlnet": use_controlnet,
        "controlnet_model_name": controlnet_model_name,
        "controlnet_strength": controlnet_strength,
        "control_image_path": control_image_path,
    }


def resolve_comfyui_model_folders(config: dict[str, Any]) -> dict[str, Any]:
    comfyui_models_cfg = config.get("comfyui_models", {}) or {}
    paths_cfg = config.get("paths", {}) or {}

    root = str(comfyui_models_cfg.get("root", "ComfyUI/models"))

    mainline_defaults = {
        "checkpoints": str(paths_cfg.get("comfyui_checkpoints_dir", "ComfyUI/models/checkpoints")),
        "diffusion_models": "ComfyUI/models/diffusion_models",
        "unet": "ComfyUI/models/unet",
        "vae": str(paths_cfg.get("comfyui_vae_dir", "ComfyUI/models/vae")),
        "text_encoders": "ComfyUI/models/text_encoders",
        "clip": "ComfyUI/models/clip",
    }
    extension_defaults = {
        "clip_vision": "ComfyUI/models/clip_vision",
        "loras": str(paths_cfg.get("comfyui_loras_dir", "ComfyUI/models/loras")),
        "controlnet": str(paths_cfg.get("comfyui_controlnet_dir", "ComfyUI/models/controlnet")),
        "embeddings": "ComfyUI/models/embeddings",
        "style_models": "ComfyUI/models/style_models",
        "upscale_models": "ComfyUI/models/upscale_models",
        "latent_upscale_models": "ComfyUI/models/latent_upscale_models",
        "photomaker": "ComfyUI/models/photomaker",
        "gligen": "ComfyUI/models/gligen",
        "hypernetworks": "ComfyUI/models/hypernetworks",
        "audio_encoders": "ComfyUI/models/audio_encoders",
    }
    advanced_defaults = {
        "diffusers": "ComfyUI/models/diffusers",
        "vae_approx": "ComfyUI/models/vae_approx",
        "classifiers": "ComfyUI/models/classifiers",
        "model_patches": "ComfyUI/models/model_patches",
        "download_model_base": "ComfyUI/models/download_model_base",
    }

    mainline_cfg = comfyui_models_cfg.get("mainline_required", {}) or {}
    extension_cfg = comfyui_models_cfg.get("common_extensions", {}) or {}
    advanced_cfg = comfyui_models_cfg.get("advanced_optional", {}) or {}

    mainline = {
        key: str(mainline_cfg.get(key, mainline_defaults[key]))
        for key in mainline_defaults.keys()
    }
    extensions = {
        key: str(extension_cfg.get(key, extension_defaults[key]))
        for key in extension_defaults.keys()
    }
    advanced = {
        key: str(advanced_cfg.get(key, advanced_defaults[key]))
        for key in advanced_defaults.keys()
    }

    # Backward-compatible flat key support inside `comfyui_models`.
    for key in COMFYUI_MODEL_DIR_KEYS:
        if key in comfyui_models_cfg and str(comfyui_models_cfg.get(key, "")).strip():
            value = str(comfyui_models_cfg[key])
            if key in mainline:
                mainline[key] = value
            elif key in extensions:
                extensions[key] = value
            elif key in advanced:
                advanced[key] = value

    flat: dict[str, str] = {}
    flat.update(mainline)
    flat.update(extensions)
    flat.update(advanced)

    return {
        "root": root,
        "mainline_required": mainline,
        "common_extensions": extensions,
        "advanced_optional": advanced,
        "flat": flat,
    }


def resolve_workflow_model_requirements(
    config: dict[str, Any],
    inspection_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    comfyui_cfg = config.get("comfyui", {}) or {}
    requirement_cfg = comfyui_cfg.get("workflow_model_requirements", {}) or {}
    workflow_import_cfg = comfyui_cfg.get("workflow_import", {}) or {}

    detected_family = str(
        (inspection_result or {}).get("suggested_model_family", "classic_checkpoint")
    ).strip() or "classic_checkpoint"
    declared_family = str(comfyui_cfg.get("workflow_model_family", "")).strip()
    prefer_detected_family = bool(workflow_import_cfg.get("use_detected_family", False))
    model_family = (
        detected_family
        if prefer_detected_family and inspection_result is not None
        else (declared_family or detected_family)
    )

    declared_required = _to_string_list(requirement_cfg.get("required", []))
    declared_recommended = _to_string_list(requirement_cfg.get("recommended", []))
    declared_optional = _to_string_list(requirement_cfg.get("optional", []))
    # Backward compatibility: if only `optional` is provided, use it as recommended.
    if not declared_recommended and declared_optional:
        declared_recommended = list(declared_optional)
        declared_optional = []

    if inspection_result is not None and bool(
        workflow_import_cfg.get("prefer_workflow_requirements", True)
    ):
        inferred = infer_model_dirs_from_inspection(inspection_result)
        declared_required.extend(inferred["required"])
        declared_recommended.extend(inferred["recommended"])
        declared_optional.extend(inferred["optional"])

    resolved = resolve_model_dir_requirements(
        model_family=model_family,
        declared_required=declared_required,
        declared_recommended=declared_recommended,
        declared_optional=declared_optional,
    )
    resolved["strict"] = bool(comfyui_cfg.get("strict_model_dir_check", False))
    return resolved


def build_comfyui_model_compatibility_report(
    config: dict[str, Any],
    inspection_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model_folders = resolve_comfyui_model_folders(config)
    requirements = resolve_workflow_model_requirements(
        config, inspection_result=inspection_result
    )
    validation = validate_model_directory_requirements(
        model_folders=model_folders["flat"],
        requirements=requirements,
        strict=requirements["strict"],
    )

    return {
        "model_family": requirements["model_family"],
        "model_family_note": MODEL_FAMILY_ABSTRACTION_NOTE,
        "strict": requirements["strict"],
        "required_dirs": validation["required"],
        "recommended_dirs": validation["recommended"],
        "optional_dirs": validation["optional"],
        "missing_required_dirs": validation["missing_required"],
        "missing_recommended_dirs": validation["missing_recommended"],
        "missing_optional_dirs": validation["missing_optional"],
        "model_folder_map": model_folders["flat"],
    }


def inspect_workflow_from_config(
    config: dict[str, Any], workflow_path: str | Path | None = None
) -> dict[str, Any]:
    comfyui = resolve_comfyui_settings(config)
    target = str(workflow_path or comfyui.get("workflow_json", "")).strip()
    if not target:
        raise ValueError("Workflow JSON path is required for workflow inspection.")
    return inspect_workflow_path(target)


def resolve_models_from_config(
    config: dict[str, Any],
    inspection_result: dict[str, Any],
    comfyui_root: str | Path | None = None,
) -> dict[str, Any]:
    comfyui = resolve_comfyui_settings(config)
    model_folders = resolve_comfyui_model_folders(config)
    root = str(comfyui_root or comfyui.get("comfyui_root") or "ComfyUI")
    policy = comfyui.get("model_resolution_policy", {}) or {}
    return build_model_resolution_report(
        inspection_result=inspection_result,
        comfyui_root=root,
        model_dir_map=model_folders["flat"],
        policy=policy,
    )


def suggest_mapping_from_config(
    config: dict[str, Any],
    inspection_result: dict[str, Any],
    existing_mapping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _ = config
    return suggest_node_mapping(
        inspection_result=inspection_result, existing_mapping=existing_mapping
    )


def infer_model_dirs_from_inspection(inspection_result: dict[str, Any]) -> dict[str, list[str]]:
    model_kinds = {
        str(item.get("model_kind", "")) for item in inspection_result.get("detected_model_files", [])
    }
    required: set[str] = set()
    recommended: set[str] = set()
    optional: set[str] = set()

    if "checkpoint" in model_kinds:
        required.add("checkpoints")
        recommended.add("vae")
    if {"unet", "text_encoder", "vae"}.issubset(model_kinds):
        required.update({"diffusion_models", "text_encoders", "vae"})
    if "lora" in model_kinds:
        optional.add("loras")
    if "controlnet" in model_kinds:
        optional.add("controlnet")
    if "clip_vision" in model_kinds:
        optional.add("clip_vision")

    return {
        "required": sorted(required),
        "recommended": sorted(recommended - required),
        "optional": sorted(optional - required - recommended),
    }


def _to_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _normalize_prompt_row(row: dict[str, Any], row_index: int) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    raw_id = str(row.get("id", "")).strip()
    normalized["id"] = raw_id or str(row_index)
    normalized["prompt_row_index"] = row_index
    normalized["prompt_row_id"] = raw_id or str(row_index)
    normalized["subject"] = str(row.get("subject", "")).strip()
    normalized["style"] = str(row.get("style", "")).strip()
    normalized["attributes"] = str(row.get("attributes", "")).strip()

    positive_value, positive_alias, positive_explicit = _extract_alias(
        row, POSITIVE_PROMPT_ALIASES
    )
    if positive_explicit and positive_value:
        normalized["positive_prompt"] = positive_value
        normalized["positive_prompt_source"] = f"prompt_pack.{positive_alias}"
    else:
        composed = _compose_prompt_from_parts(
            normalized["subject"],
            normalized["style"],
            normalized["attributes"],
        )
        normalized["positive_prompt"] = composed
        normalized["positive_prompt_source"] = (
            "prompt_pack.composed(subject,style,attributes)" if composed else ""
        )

    negative_value, negative_alias, negative_explicit = _extract_alias(
        row, NEGATIVE_PROMPT_ALIASES
    )
    normalized["negative_prompt"] = negative_value
    normalized["negative_prompt_explicit"] = negative_explicit
    if negative_explicit:
        if negative_value:
            normalized["negative_prompt_source"] = f"prompt_pack.{negative_alias}"
        else:
            normalized["negative_prompt_source"] = (
                f"prompt_pack.{negative_alias}(empty)"
            )
    else:
        normalized["negative_prompt_source"] = ""

    filename_value, filename_alias, filename_explicit = _extract_alias(
        row, FILENAME_PREFIX_ALIASES
    )
    normalized["filename_prefix"] = filename_value
    normalized["filename_prefix_source"] = (
        f"prompt_pack.{filename_alias}" if filename_explicit and filename_value else ""
    )
    normalized["lora_name"] = str(row.get("lora_name", "")).strip()
    normalized["lora_strength_model"] = str(row.get("lora_strength_model", "")).strip()
    seed_value, seed_alias, seed_explicit = _extract_alias(row, SEED_ALIASES)
    normalized["seed"] = seed_value
    normalized["seed_source"] = (
        f"prompt_pack.{seed_alias}" if seed_explicit and seed_value else ""
    )
    return normalized


def _extract_alias(
    row: dict[str, Any], aliases: list[str]
) -> tuple[str, str, bool]:
    first_seen_empty_key = ""
    for key in aliases:
        if key in row:
            raw = row.get(key, "")
            value = str(raw).strip()
            if value:
                return (value, key, True)
            if not first_seen_empty_key:
                first_seen_empty_key = key
    if first_seen_empty_key:
        return ("", first_seen_empty_key, True)
    return ("", "", False)


def _compose_prompt_from_parts(subject: str, style: str, attributes: str) -> str:
    parts = [subject.strip(), style.strip(), attributes.strip()]
    non_empty = [part for part in parts if part]
    return ", ".join(non_empty)
