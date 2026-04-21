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


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_prompt_pack_csv(path: str | Path) -> list[dict[str, str]]:
    path = Path(path)
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_run_manifest(
    config: dict[str, Any],
    prompt_rows: list[dict[str, str]],
) -> dict[str, Any]:
    project_cfg = config.get("project", {})
    task_cfg = config.get("task", {})
    model_cfg = config.get("model", {})
    runtime_cfg = config.get("runtime", {})
    generation_cfg = config.get("generation", {})

    manifest: dict[str, Any] = {
        "project_name": project_cfg.get("name", "unknown_project"),
        "task_type": task_cfg.get("type", "unknown_task"),
        "asset_type": task_cfg.get("asset_type", "unknown_asset"),
        "scenario": task_cfg.get("scenario", "unknown_scenario"),
        "model_family": model_cfg.get("family", "unknown_family"),
        "base_model_name": model_cfg.get("base_model_name", "unknown_model"),
        "seed": runtime_cfg.get("seed", 42),
        "width": generation_cfg.get("width", 1024),
        "height": generation_cfg.get("height", 1024),
        "num_inference_steps": generation_cfg.get("num_inference_steps", 30),
        "guidance_scale": generation_cfg.get("guidance_scale", 7.0),
        "sampler": generation_cfg.get("sampler", "unknown_sampler"),
        "scheduler": generation_cfg.get("scheduler", "unknown_scheduler"),
        "output_subdir": generation_cfg.get("output_subdir", "outputs/placeholder"),
        "items": [],
    }

    for row in prompt_rows:
        positive_prompt = row.get("positive_prompt_text", "").strip()

        if not positive_prompt and row.get("positive_prompt_path"):
            prompt_path = Path(row["positive_prompt_path"])
            if prompt_path.exists():
                positive_prompt = prompt_path.read_text(encoding="utf-8").strip()

        negative_prompt = row.get("negative_prompt_text", "").strip()
        if not negative_prompt:
            negative_prompt = row.get("negative_prompt", "").strip()

        manifest["items"].append(
            {
                "id": row.get("id", ""),
                "subject": row.get("subject", ""),
                "style": row.get("style", ""),
                "attributes": row.get("attributes", ""),
                "positive_prompt": positive_prompt,
                "negative_prompt": negative_prompt,
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
        "mode": str(comfyui_cfg.get("mode", "manifest")),
        "workflow_json": str(comfyui_cfg.get("workflow_json", "")),
        "node_map": str(comfyui_cfg.get("node_map", "")),
        "save_patched_workflows_dir": str(
            comfyui_cfg.get("save_patched_workflows_dir", "results/patched_workflows")
        ),
        "patch_save_image_output_dir": bool(
            comfyui_cfg.get("patch_save_image_output_dir", False)
        ),
        "save_image_output_dir": str(comfyui_cfg.get("save_image_output_dir", "")),
        "output_subdir": str(generation_cfg.get("output_subdir", "outputs/placeholder")),
        "use_lora": use_lora,
        "lora_path": lora_path,
        "lora_strength": lora_strength,
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
        "vae": str(paths_cfg.get("comfyui_vae_dir", "ComfyUI/models/vae")),
        "text_encoders": "ComfyUI/models/text_encoders",
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


def resolve_workflow_model_requirements(config: dict[str, Any]) -> dict[str, Any]:
    comfyui_cfg = config.get("comfyui", {}) or {}
    requirement_cfg = comfyui_cfg.get("workflow_model_requirements", {}) or {}

    model_family = comfyui_cfg.get("workflow_model_family", "classic_checkpoint")
    declared_required = _to_string_list(requirement_cfg.get("required", []))
    declared_recommended = _to_string_list(requirement_cfg.get("recommended", []))
    declared_optional = _to_string_list(requirement_cfg.get("optional", []))
    # Backward compatibility: if only `optional` is provided, use it as recommended.
    if not declared_recommended and declared_optional:
        declared_recommended = list(declared_optional)
        declared_optional = []

    resolved = resolve_model_dir_requirements(
        model_family=model_family,
        declared_required=declared_required,
        declared_recommended=declared_recommended,
        declared_optional=declared_optional,
    )
    resolved["strict"] = bool(comfyui_cfg.get("strict_model_dir_check", False))
    return resolved


def build_comfyui_model_compatibility_report(config: dict[str, Any]) -> dict[str, Any]:
    model_folders = resolve_comfyui_model_folders(config)
    requirements = resolve_workflow_model_requirements(config)
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


def _to_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]
