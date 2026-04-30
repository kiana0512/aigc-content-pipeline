from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .config import load_json
from .model_profiles import ModelProfileResolver
from .workflow_registry import WorkflowMetadata, WorkflowRegistry, find_placeholders


def inspect_workflow(metadata: WorkflowMetadata) -> dict[str, Any]:
    workflow = load_json(metadata.workflow_json_path)
    placeholders = find_placeholders(workflow)
    return {
        "workflow_id": metadata.workflow_id,
        "workflow_path": metadata.workflow_json_path,
        "workflow_type": metadata.workflow_type,
        "optional_modules": metadata.optional_modules,
        "placeholders": placeholders,
        "patch_contract": metadata.patch_contract,
        "warnings": metadata.warnings,
    }


def inspect_active_workflow() -> dict[str, Any]:
    metadata = WorkflowRegistry().get_active()
    if not metadata:
        raise FileNotFoundError("No active workflow configured. Run scripts/import_comfy_workflow.py --set-active first.")
    return inspect_workflow(metadata)


def check_model_mapping(generation_config: dict[str, Any] | None = None) -> list[str]:
    generation_config = generation_config or {}
    resolver = ModelProfileResolver()
    warnings: list[str] = []
    checks = {
        "model_profile": "checkpoints",
        "vae_profile": "vae",
        "controlnet_profile": "controlnet",
        "ipadapter_profile": "ipadapter",
        "upscale_model": "upscalers",
    }
    for field, section in checks.items():
        name = generation_config.get(field, "")
        if not name:
            continue
        try:
            resolver.get_profile(section, name)
        except KeyError:
            warnings.append(f"Missing model profile mapping: {section}.{name}")
    return warnings
