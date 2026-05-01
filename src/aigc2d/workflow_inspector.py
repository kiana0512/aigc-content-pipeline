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
    errors, warnings = validate_patch_contract(workflow, metadata.patch_contract)
    return {
        "workflow_id": metadata.workflow_id,
        "workflow_path": metadata.workflow_json_path,
        "registry_path": str(WorkflowRegistry().metadata_path(metadata.workflow_id)),
        "workflow_type": metadata.workflow_type,
        "optional_modules": metadata.optional_modules,
        "detected_modules": metadata.detected_modules or metadata.optional_modules,
        "node_inventory": metadata.node_inventory,
        "graph": metadata.graph,
        "placeholders": placeholders,
        "patch_contract": metadata.patch_contract,
        "candidates": metadata.candidates,
        "ambiguous_candidates": metadata.ambiguous_candidates,
        "warnings": [*metadata.warnings, *warnings],
        "errors": errors,
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


def validate_patch_contract(workflow: dict[str, Any], patch_contract: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for field_name, mapping in (patch_contract.get("node_inputs") or {}).items():
        node_id = str(mapping.get("node_id", ""))
        input_name = str(mapping.get("input", ""))
        optional = bool(mapping.get("optional", True))
        if node_id not in workflow:
            message = f"registry mapping points to missing node: {field_name} -> {node_id}"
            (warnings if optional else errors).append(message)
            continue
        inputs = workflow[node_id].get("inputs", {})
        if not isinstance(inputs, dict) or input_name not in inputs:
            message = f"registry mapping points to missing input: {field_name} -> {node_id}.{input_name}"
            (warnings if optional else errors).append(message)
    return errors, warnings
