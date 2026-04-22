from __future__ import annotations

import pytest

from src.generation.comfyui_adapter import ComfyUIAdapterError
from src.generation.workflow_runner import (
    build_comfyui_model_compatibility_report,
    infer_model_dirs_from_inspection,
    resolve_comfyui_model_folders,
    resolve_workflow_model_requirements,
)


def _base_config() -> dict:
    return {
        "comfyui": {
            "workflow_model_family": "classic_checkpoint",
            "workflow_model_requirements": {
                "required": [],
                "recommended": [],
                "optional": [],
            },
            "strict_model_dir_check": False,
        },
        "comfyui_models": {
            "root": "ComfyUI/models",
            "mainline_required": {
                "checkpoints": "ComfyUI/models/checkpoints",
                "diffusion_models": "ComfyUI/models/diffusion_models",
                "vae": "ComfyUI/models/vae",
                "text_encoders": "ComfyUI/models/text_encoders",
            },
            "common_extensions": {
                "clip_vision": "ComfyUI/models/clip_vision",
                "loras": "ComfyUI/models/loras",
                "controlnet": "ComfyUI/models/controlnet",
                "embeddings": "ComfyUI/models/embeddings",
                "style_models": "ComfyUI/models/style_models",
                "upscale_models": "ComfyUI/models/upscale_models",
                "latent_upscale_models": "ComfyUI/models/latent_upscale_models",
                "photomaker": "ComfyUI/models/photomaker",
                "gligen": "ComfyUI/models/gligen",
                "hypernetworks": "ComfyUI/models/hypernetworks",
                "audio_encoders": "ComfyUI/models/audio_encoders",
            },
            "advanced_optional": {
                "diffusers": "ComfyUI/models/diffusers",
                "vae_approx": "ComfyUI/models/vae_approx",
                "classifiers": "ComfyUI/models/classifiers",
                "model_patches": "ComfyUI/models/model_patches",
                "download_model_base": "ComfyUI/models/download_model_base",
            },
        },
    }


def test_resolve_comfyui_model_folders_contains_required_keys() -> None:
    config = _base_config()
    model_folders = resolve_comfyui_model_folders(config)
    flat = model_folders["flat"]

    assert flat["checkpoints"].endswith("models/checkpoints")
    assert flat["diffusion_models"].endswith("models/diffusion_models")
    assert flat["text_encoders"].endswith("models/text_encoders")
    assert flat["audio_encoders"].endswith("models/audio_encoders")
    assert flat["download_model_base"].endswith("models/download_model_base")


def test_classic_checkpoint_family_requirements_resolve() -> None:
    config = _base_config()
    config["comfyui"]["workflow_model_family"] = "classic_checkpoint"
    req = resolve_workflow_model_requirements(config)
    assert req["model_family"] == "classic_checkpoint"
    assert "checkpoints" in req["required"]
    assert "vae" in req["recommended"]


def test_split_model_family_requires_diffusion_text_encoder_vae() -> None:
    config = _base_config()
    config["comfyui"]["workflow_model_family"] = "split_model"
    report = build_comfyui_model_compatibility_report(config)
    assert report["model_family"] == "split_model"
    assert "diffusion_models" in report["required_dirs"]
    assert "text_encoders" in report["required_dirs"]
    assert "vae" in report["required_dirs"]
    assert report["missing_required_dirs"] == []
    assert report["recommended_dirs"] == []


def test_missing_required_directory_declaration_is_reported() -> None:
    config = _base_config()
    config["comfyui"]["workflow_model_family"] = "split_model"
    config["comfyui_models"]["mainline_required"]["diffusion_models"] = ""
    report = build_comfyui_model_compatibility_report(config)
    assert report["strict"] is False
    assert "diffusion_models" in report["missing_required_dirs"]


def test_missing_required_directory_in_non_strict_mode_does_not_raise() -> None:
    config = _base_config()
    config["comfyui"]["workflow_model_family"] = "classic_checkpoint"
    config["comfyui_models"]["mainline_required"]["checkpoints"] = ""

    report = build_comfyui_model_compatibility_report(config)
    assert "checkpoints" in report["missing_required_dirs"]
    assert report["strict"] is False


def test_missing_recommended_directory_is_reported() -> None:
    config = _base_config()
    config["comfyui"]["workflow_model_family"] = "classic_checkpoint"
    config["comfyui_models"]["mainline_required"]["vae"] = ""
    report = build_comfyui_model_compatibility_report(config)
    assert "vae" in report["recommended_dirs"]
    assert "vae" in report["missing_recommended_dirs"]


def test_missing_required_directory_raises_in_strict_mode() -> None:
    config = _base_config()
    config["comfyui"]["workflow_model_family"] = "split_model"
    config["comfyui"]["strict_model_dir_check"] = True
    config["comfyui_models"]["mainline_required"]["text_encoders"] = ""

    with pytest.raises(ComfyUIAdapterError) as exc:
        build_comfyui_model_compatibility_report(config)

    assert "Missing required ComfyUI model directory declarations" in str(exc.value)


def test_detected_family_can_override_declared_family() -> None:
    config = _base_config()
    config["comfyui"]["workflow_model_family"] = "classic_checkpoint"
    config["comfyui"]["workflow_import"] = {"use_detected_family": True}
    inspection = {"suggested_model_family": "split_model", "detected_model_files": []}
    req = resolve_workflow_model_requirements(config, inspection_result=inspection)
    assert req["model_family"] == "split_model"


def test_infer_model_dirs_from_inspection_split_model() -> None:
    inspection = {
        "detected_model_files": [
            {"model_kind": "unet"},
            {"model_kind": "text_encoder"},
            {"model_kind": "vae"},
        ]
    }
    inferred = infer_model_dirs_from_inspection(inspection)
    assert set(inferred["required"]) == {"diffusion_models", "text_encoders", "vae"}
