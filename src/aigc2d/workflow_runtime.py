from __future__ import annotations

import copy
import json
import random
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, load_json, resolve_path
from .generation_config import GenerationConfig, apply_overrides, load_generation_config
from .model_profiles import ModelProfileResolver, ResolvedModels
from .prompt_bundle import PromptBundle, load_prompt_bundle
from .workflow_registry import WorkflowMetadata, WorkflowRegistry


def replace_placeholders(obj: Any, values: dict[str, Any]) -> Any:
    if isinstance(obj, dict):
        return {key: replace_placeholders(value, values) for key, value in obj.items()}
    if isinstance(obj, list):
        return [replace_placeholders(value, values) for value in obj]
    if isinstance(obj, str):
        stripped = obj.strip()
        if stripped.startswith("{{") and stripped.endswith("}}"):
            return values.get(stripped[2:-2].strip(), "")
        for key, value in values.items():
            obj = obj.replace("{{" + key + "}}", str(value or ""))
        return obj
    return obj


def resolve_seed(seed_policy: str, seed: int) -> int:
    if seed_policy == "random":
        return random.randint(0, 2**32 - 1)
    return seed


class WorkflowRuntime:
    def __init__(
        self,
        workflow_dir: str | Path | None = None,
        model_resolver: ModelProfileResolver | None = None,
        workflow_registry: WorkflowRegistry | None = None,
    ) -> None:
        self.workflow_dir = Path(workflow_dir) if workflow_dir else PROJECT_ROOT / "workflows" / "comfyui"
        self.model_resolver = model_resolver or ModelProfileResolver()
        self.workflow_registry = workflow_registry or WorkflowRegistry()

    def workflow_template_path(self, workflow: str) -> Path:
        candidate = Path(workflow)
        path = candidate if candidate.is_absolute() else self.workflow_dir / workflow
        if path.suffix != ".json":
            path = path.with_suffix(".json")
        if not path.exists():
            raise FileNotFoundError(f"Workflow template not found: {path}")
        return path

    def build_from_config(
        self,
        generation_config_path: str | Path,
        prompt_row: dict[str, Any] | None = None,
        manifest_item: dict[str, Any] | None = None,
        cli_overrides: dict[str, Any] | None = None,
        use_active_workflow: bool = True,
    ) -> dict[str, Any]:
        prompt_row = prompt_row or {}
        manifest_item = manifest_item or {}
        config = apply_overrides(
            load_generation_config(generation_config_path),
            manifest_item,
            prompt_row,
            cli_overrides,
        )
        models = self.model_resolver.resolve(
            model_profile=config.model_profile,
            vae_profile=config.vae_profile,
            controlnet_profile=config.controlnet_profile if config.enable_controlnet else "",
            ipadapter_profile=config.ipadapter_profile if config.enable_ipadapter else "",
            upscale_model=config.upscale_model,
            segmentation_profile=config.segmentation_profile,
            detector_profile=config.detector_profile,
            vlm_profile=config.vlm_profile,
            tagger_profile=config.tagger_profile,
            lora_profiles=config.lora_profiles if config.enable_lora else [],
            lora_weights=config.lora_weights,
            lora_trigger_words=config.lora_trigger_words,
        )
        values = self.build_values(config, models, prompt_row, manifest_item)
        active_metadata = self.workflow_registry.get_active() if use_active_workflow else None
        template_path = self._resolve_workflow_path(config.workflow, active_metadata)
        workflow = replace_placeholders(copy.deepcopy(load_json(template_path)), values)
        patch_warnings = self.workflow_registry.apply_patch_contract(workflow, values, active_metadata)
        lora_warnings = self._lora_warnings(config, active_metadata)
        return {
            "workflow": workflow,
            "values": values,
            "generation_config": config,
            "resolved_models": models,
            "workflow_template_path": template_path,
            "active_workflow": active_metadata.__dict__ if active_metadata else {},
            "patch_warnings": [*patch_warnings, *lora_warnings],
        }

    def _resolve_workflow_path(self, workflow: str, active_metadata: WorkflowMetadata | None) -> Path:
        if active_metadata:
            path = Path(active_metadata.workflow_json_path)
            return path if path.is_absolute() else PROJECT_ROOT / path
        if workflow in {"active", "active_workflow", ""}:
            raise FileNotFoundError(
                "No active workflow configured. Import a verified ComfyUI API JSON first: "
                "python scripts/import_comfy_workflow.py --workflow-json <api.json> --workflow-id <id> --set-active"
            )
        return self.workflow_template_path(workflow)

    def _lora_warnings(self, config: GenerationConfig, metadata: WorkflowMetadata | None) -> list[str]:
        if not config.enable_lora:
            return []
        if not metadata:
            return ["LoRA is enabled but no active workflow metadata was loaded."]
        if not metadata.optional_modules.get("lora", False):
            return ["LoRA is enabled in config, but active workflow metadata does not advertise LoRA nodes. LoRA patch skipped unless metadata patch_contract is edited."]
        return []

    def build_values(
        self,
        config: GenerationConfig,
        models: ResolvedModels,
        prompt_row: dict[str, Any],
        manifest_item: dict[str, Any],
    ) -> dict[str, Any]:
        prompt_bundle = self._load_prompt_bundle(prompt_row, manifest_item)
        positive = (
            prompt_row.get("positive_prompt")
            or (prompt_bundle.positive_prompt if prompt_bundle else "")
            or prompt_row.get("prompt")
            or ""
        )
        negative = prompt_row.get("negative_prompt") or (prompt_bundle.negative_prompt if prompt_bundle else "")
        reference = (
            prompt_row.get("reference_image")
            or manifest_item.get("init_image")
            or manifest_item.get("reference_image")
            or manifest_item.get("image_path")
            or config.reference_image
        )
        logical_inputs = self.build_logical_inputs(prompt_row, manifest_item, prompt_bundle, reference)
        return {
            "positive_prompt": positive,
            "negative_prompt": negative,
            "width": config.width,
            "height": config.height,
            "seed": resolve_seed(config.seed_policy, config.seed),
            "steps": config.steps,
            "cfg": config.cfg,
            "sampler": config.sampler,
            "scheduler": config.scheduler,
            "denoise": config.denoise,
            "checkpoint": models.checkpoint,
            "model_name": models.checkpoint,
            "vae": models.vae,
            "vae_name": models.vae,
            "reference_image": str(reference or ""),
            "input_image_path": str(reference or ""),
            "ipadapter_model": models.ipadapter,
            "ipadapter_name": models.ipadapter,
            "clip_vision_model": models.clip_vision,
            "controlnet_model": models.controlnet,
            "controlnet_name": models.controlnet,
            "control_weight": config.extra.get("control_weight", 0.65),
            "controlnet_weight": config.extra.get("control_weight", 0.65),
            "ip_weight": config.extra.get("ip_weight", 0.75),
            "ipadapter_weight": config.extra.get("ip_weight", 0.75),
            "upscale_model": models.upscaler,
            "segmentation_model": models.segmentation,
            "detector_model": models.detector,
            "vlm_model": models.vlm,
            "tagger_model": models.tagger,
            "lora_settings": models.loras,
            "lora_1_name": models.loras[0]["path"] if models.loras else "",
            "lora_1_weight": models.loras[0]["weight"] if models.loras else 0,
            "lora_trigger_words": ", ".join(
                word for lora in models.loras for word in lora.get("trigger_words", [])
            ),
            "upscale_ratio": config.upscale_ratio,
            "final_width": config.final_target_resolution[0],
            "final_height": config.final_target_resolution[1],
            "output_prefix": f"aigc2d/{config.output_subdir}",
            **logical_inputs,
        }

    def build_logical_inputs(
        self,
        prompt_row: dict[str, Any],
        manifest_item: dict[str, Any],
        prompt_bundle: PromptBundle | None,
        reference: str | None,
    ) -> dict[str, Any]:
        def list_field(name: str) -> list[str]:
            value = prompt_row.get(name) or manifest_item.get(name) or ""
            if isinstance(value, list):
                return [str(item) for item in value if item]
            return [item.strip() for item in str(value).split("|") if item.strip()]

        values = {
            "init_image": str(reference or ""),
            "identity_ref_images": list_field("identity_refs"),
            "face_ref_images": list_field("face_refs"),
            "mecha_ref_images": list_field("mecha_refs"),
            "composition_ref_images": list_field("composition_refs"),
            "style_ref_images": list_field("style_refs"),
            "background_ref_images": list_field("background_refs"),
            "character_mask": prompt_row.get("character_mask") or manifest_item.get("character_mask") or "",
            "mecha_mask": prompt_row.get("mecha_mask") or manifest_item.get("mecha_mask") or "",
            "ui_mask": prompt_row.get("ui_mask") or manifest_item.get("ui_mask") or "",
            "prompt_bundle": prompt_bundle.to_dict() if prompt_bundle else {},
        }
        for key, value in list(values.items()):
            if isinstance(value, list):
                values[f"{key}_first"] = value[0] if value else ""
                values[f"{key}_json"] = json.dumps(value, ensure_ascii=False)
        return values

    def _load_prompt_bundle(
        self,
        prompt_row: dict[str, Any],
        manifest_item: dict[str, Any],
    ) -> PromptBundle | None:
        bundle_path = prompt_row.get("prompt_bundle") or manifest_item.get("prompt_bundle")
        if bundle_path:
            path = Path(bundle_path)
            if path.exists():
                return load_prompt_bundle(path)
        return None


def runtime_snapshot(
    config: GenerationConfig,
    models: ResolvedModels,
    values: dict[str, Any],
) -> dict[str, Any]:
    return {
        "generation_config": asdict(config),
        "resolved_models": asdict(models),
        "resolved_params": values,
    }


def write_workflow(path: str | Path, workflow: dict[str, Any]) -> Path:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target
