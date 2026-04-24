from __future__ import annotations

from pathlib import Path

from src.generation.model_resolver import build_model_resolution_report
from src.generation.workflow_inspector import inspect_workflow_path


ROOT = Path(__file__).resolve().parents[1]
Z_WORKFLOW = ROOT / "workflows/comfyui/image_z_image_turbo_api.json"
QWEN_WORKFLOW = ROOT / "workflows/comfyui/qwen_image_illustration_lora_api.json"


def _model_dir_map() -> dict[str, str]:
    return {
        "checkpoints": "ComfyUI/models/checkpoints",
        "diffusion_models": "ComfyUI/models/diffusion_models",
        "unet": "ComfyUI/models/unet",
        "vae": "ComfyUI/models/vae",
        "text_encoders": "ComfyUI/models/text_encoders",
        "clip": "ComfyUI/models/clip",
        "loras": "ComfyUI/models/loras",
        "controlnet": "ComfyUI/models/controlnet",
    }


def test_model_resolver_extracts_real_export_model_names() -> None:
    inspection_z = inspect_workflow_path(Z_WORKFLOW)
    models_z = {item["model_name"] for item in inspection_z["detected_model_files"]}
    assert "z_image_turbo_bf16.safetensors" in models_z
    assert "qwen_3_4b.safetensors" in models_z
    assert "ae.safetensors" in models_z

    inspection_q = inspect_workflow_path(QWEN_WORKFLOW)
    models_q = {item["model_name"] for item in inspection_q["detected_model_files"]}
    assert "qwen_image_fp8_e4m3fn.safetensors" in models_q
    assert "qwen_2.5_vl_7b_fp8_scaled.safetensors" in models_q
    assert "qwen_image_vae.safetensors" in models_q
    assert "illustration-1.0-qwen-image.safetensors" in models_q


def test_model_resolver_real_exports_missing_models_reported(tmp_path: Path) -> None:
    comfyui_root = tmp_path / "ComfyUI"
    inspection_q = inspect_workflow_path(QWEN_WORKFLOW)

    report = build_model_resolution_report(
        inspection_result=inspection_q,
        comfyui_root=comfyui_root,
        model_dir_map=_model_dir_map(),
    )

    summary = report["resolution"]["summary"]
    assert summary["requested_model_count"] >= 4
    assert summary["missing_count"] >= 4
    assert summary["resolved_count"] == 0
