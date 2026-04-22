from __future__ import annotations

from pathlib import Path

from src.generation.model_resolver import (
    build_model_resolution_report,
    scan_model_directories,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")


def _sample_inspection() -> dict:
    return {
        "workflow_format": "comfyui_api_prompt",
        "node_count": 10,
        "suggested_model_family": "split_model",
        "detected_model_files": [
            {
                "node_id": "1",
                "class_type": "UNETLoader",
                "model_kind": "unet",
                "model_name": "qwen_unet.safetensors",
            },
            {
                "node_id": "2",
                "class_type": "CLIPLoader",
                "model_kind": "text_encoder",
                "model_name": "qwen_clip.safetensors",
            },
            {
                "node_id": "3",
                "class_type": "VAELoader",
                "model_kind": "vae",
                "model_name": "qwen_vae.safetensors",
            },
            {
                "node_id": "7",
                "class_type": "LoraLoaderModelOnly",
                "model_kind": "lora",
                "model_name": "qwen_style_v2.safetensors",
            },
        ],
    }


def _model_dir_map() -> dict[str, str]:
    return {
        "checkpoints": "ComfyUI/models/checkpoints",
        "diffusion_models": "ComfyUI/models/diffusion_models",
        "vae": "ComfyUI/models/vae",
        "text_encoders": "ComfyUI/models/text_encoders",
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
        "diffusers": "ComfyUI/models/diffusers",
        "vae_approx": "ComfyUI/models/vae_approx",
        "classifiers": "ComfyUI/models/classifiers",
        "model_patches": "ComfyUI/models/model_patches",
        "download_model_base": "ComfyUI/models/download_model_base",
    }


def test_scan_model_directories_builds_index(tmp_path: Path) -> None:
    root = tmp_path / "ComfyUI"
    _touch(root / "models/diffusion_models/qwen_unet.safetensors")
    _touch(root / "models/text_encoders/qwen_clip.safetensors")
    _touch(root / "models/vae/qwen_vae.safetensors")
    _touch(root / "models/loras/qwen_style_v1.safetensors")

    scanned = scan_model_directories(comfyui_root=root, model_dir_map=_model_dir_map())
    assert scanned["folders"]["diffusion_models"]["exists"] is True
    assert scanned["folders"]["diffusion_models"]["file_count"] == 1
    assert scanned["folders"]["text_encoders"]["file_count"] == 1


def test_build_model_resolution_report_contains_missing_and_maybe(tmp_path: Path) -> None:
    root = tmp_path / "ComfyUI"
    _touch(root / "models/diffusion_models/qwen_unet.safetensors")
    _touch(root / "models/text_encoders/qwen_clip.safetensors")
    _touch(root / "models/vae/qwen_vae.safetensors")
    # intentionally only a fuzzy candidate for lora (v1 vs requested v2)
    _touch(root / "models/loras/qwen_style_v1.safetensors")

    report = build_model_resolution_report(
        inspection_result=_sample_inspection(),
        comfyui_root=root,
        model_dir_map=_model_dir_map(),
    )

    summary = report["resolution"]["summary"]
    assert summary["requested_model_count"] == 4
    assert summary["resolved_count"] == 3
    assert summary["missing_count"] >= 1
    assert summary["maybe_count"] >= 1

    missing = report["resolution"]["missing_models"]
    assert any(item["requested_model_name"] == "qwen_style_v2.safetensors" for item in missing)


def test_build_model_resolution_report_handles_duplicate_candidates(tmp_path: Path) -> None:
    root = tmp_path / "ComfyUI"
    _touch(root / "models/diffusion_models/qwen_unet.safetensors")
    _touch(root / "models/checkpoints/qwen_unet.safetensors")
    _touch(root / "models/text_encoders/qwen_clip.safetensors")
    _touch(root / "models/vae/qwen_vae.safetensors")

    report = build_model_resolution_report(
        inspection_result=_sample_inspection(),
        comfyui_root=root,
        model_dir_map=_model_dir_map(),
    )
    duplicates = report["resolution"]["duplicate_candidates"]
    assert duplicates, "expected ambiguous candidates when same model exists in two dirs"


def test_model_resolution_supports_aliases(tmp_path: Path) -> None:
    root = tmp_path / "ComfyUI"
    _touch(root / "models/diffusion_models/qwen_unet_fp8.safetensors")
    _touch(root / "models/text_encoders/qwen_clip.safetensors")
    _touch(root / "models/vae/qwen_vae.safetensors")
    inspection = {
        "workflow_format": "comfyui_api_prompt",
        "node_count": 3,
        "suggested_model_family": "split_model",
        "detected_model_files": [
            {
                "node_id": "1",
                "class_type": "UNETLoader",
                "model_kind": "unet",
                "model_name": "qwen_image_unet_fp8.safetensors",
            }
        ],
    }
    report = build_model_resolution_report(
        inspection_result=inspection,
        comfyui_root=root,
        model_dir_map=_model_dir_map(),
        policy={
            "aliases": {
                "qwen_image_unet_fp8.safetensors": "qwen_unet_fp8.safetensors",
            }
        },
    )
    summary = report["resolution"]["summary"]
    assert summary["resolved_count"] == 1
    resolved = report["resolution"]["resolved_models"][0]
    assert resolved.get("alias_applied") is True


def test_model_resolution_supports_path_overrides(tmp_path: Path) -> None:
    root = tmp_path / "ComfyUI"
    custom_model = root / "models/custom_bucket/qwen_override.safetensors"
    _touch(custom_model)
    inspection = {
        "workflow_format": "comfyui_api_prompt",
        "node_count": 1,
        "suggested_model_family": "split_model",
        "detected_model_files": [
            {
                "node_id": "1",
                "class_type": "UNETLoader",
                "model_kind": "unet",
                "model_name": "qwen_need_override.safetensors",
            }
        ],
    }
    report = build_model_resolution_report(
        inspection_result=inspection,
        comfyui_root=root,
        model_dir_map=_model_dir_map(),
        policy={
            "path_overrides": {
                "qwen_need_override.safetensors": str(custom_model.as_posix())
            }
        },
    )
    summary = report["resolution"]["summary"]
    assert summary["resolved_count"] == 1
    resolved = report["resolution"]["resolved_models"][0]
    assert resolved["match_type"] == "path_override"
