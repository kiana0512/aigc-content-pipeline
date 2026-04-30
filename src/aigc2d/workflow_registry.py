from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .config import PROJECT_ROOT, load_json, load_yaml, write_json


PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")
REGISTRY_DIR = PROJECT_ROOT / "workflows" / "comfyui" / "registry"
ACTIVE_WORKFLOW_PATH = PROJECT_ROOT / "configs" / "workflows" / "active_workflow.yaml"


@dataclass
class WorkflowMetadata:
    workflow_id: str
    workflow_json_path: str
    source_json_path: str = ""
    imported_time: str = ""
    workflow_type: str = "hybrid"
    supported_inputs: list[str] = field(default_factory=list)
    optional_modules: dict[str, bool] = field(default_factory=dict)
    placeholders: list[str] = field(default_factory=list)
    patch_contract: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def is_comfy_api_prompt(data: dict[str, Any]) -> bool:
    if not isinstance(data, dict) or not data:
        return False
    return all(isinstance(value, dict) and "class_type" in value for value in data.values())


def find_placeholders(data: Any) -> list[str]:
    text = json.dumps(data, ensure_ascii=False)
    return sorted(set(PLACEHOLDER_RE.findall(text)))


def infer_workflow_type(data: dict[str, Any]) -> str:
    classes = {node.get("class_type", "").lower() for node in data.values() if isinstance(node, dict)}
    has_load_image = any("loadimage" in item for item in classes)
    has_sampler = any("ksampler" in item for item in classes)
    if has_load_image and has_sampler:
        return "img2img"
    if has_sampler:
        return "text2img"
    return "hybrid"


def infer_optional_modules(data: dict[str, Any]) -> dict[str, bool]:
    classes = " ".join(
        node.get("class_type", "").lower()
        for node in data.values()
        if isinstance(node, dict)
    )
    return {
        "lora": "lora" in classes,
        "ipadapter": "ipadapter" in classes or "ip adapter" in classes,
        "controlnet": "controlnet" in classes or "control net" in classes,
        "upscale": "upscale" in classes or "scale" in classes,
        "vae": "vae" in classes,
    }


def default_patch_contract(placeholders: list[str]) -> dict[str, Any]:
    return {
        "placeholder_fields": {name: {"placeholder": name, "optional": True} for name in placeholders},
        "node_inputs": {},
        "notes": "Edit node_inputs manually for exported workflows without {{placeholders}}.",
    }


class WorkflowRegistry:
    def __init__(
        self,
        registry_dir: str | Path = REGISTRY_DIR,
        active_path: str | Path = ACTIVE_WORKFLOW_PATH,
        workflow_dir: str | Path = PROJECT_ROOT / "workflows" / "comfyui",
    ) -> None:
        self.registry_dir = Path(registry_dir)
        self.active_path = Path(active_path)
        self.workflow_dir = Path(workflow_dir)

    def import_workflow(
        self,
        workflow_json: str | Path,
        workflow_id: str,
        set_active: bool = False,
    ) -> WorkflowMetadata:
        source = Path(workflow_json)
        data = load_json(source)
        if not is_comfy_api_prompt(data):
            raise ValueError(
                "Input is not a valid ComfyUI API prompt JSON. "
                "Please export API JSON from a manually verified ComfyUI workflow."
            )
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.workflow_dir.mkdir(parents=True, exist_ok=True)
        target_json = self.workflow_dir / f"{workflow_id}.json"
        shutil.copy2(source, target_json)
        placeholders = find_placeholders(data)
        warnings = []
        if not placeholders:
            warnings.append(
                "No {{placeholders}} found. Add mappings in registry metadata patch_contract.node_inputs."
            )
        metadata = WorkflowMetadata(
            workflow_id=workflow_id,
            workflow_json_path=str(target_json),
            source_json_path=str(source),
            imported_time=datetime.now(timezone.utc).isoformat(),
            workflow_type=infer_workflow_type(data),
            supported_inputs=placeholders,
            optional_modules=infer_optional_modules(data),
            placeholders=placeholders,
            patch_contract=default_patch_contract(placeholders),
            warnings=warnings,
        )
        self.write_metadata(metadata)
        if set_active:
            self.set_active(workflow_id)
        return metadata

    def metadata_path(self, workflow_id: str) -> Path:
        return self.registry_dir / f"{workflow_id}.yaml"

    def write_metadata(self, metadata: WorkflowMetadata) -> Path:
        path = self.metadata_path(metadata.workflow_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(metadata.__dict__, f, allow_unicode=True, sort_keys=False)
        return path

    def load_metadata(self, workflow_id: str) -> WorkflowMetadata:
        data = load_yaml(self.metadata_path(workflow_id))
        return WorkflowMetadata(**data)

    def set_active(self, workflow_id: str) -> Path:
        metadata = self.load_metadata(workflow_id)
        self.active_path.parent.mkdir(parents=True, exist_ok=True)
        with self.active_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                {
                    "active_workflow_id": workflow_id,
                    "workflow_json_path": metadata.workflow_json_path,
                    "workflow_type": metadata.workflow_type,
                    "metadata_path": str(self.metadata_path(workflow_id)),
                },
                f,
                allow_unicode=True,
                sort_keys=False,
            )
        return self.active_path

    def get_active(self) -> WorkflowMetadata | None:
        if not self.active_path.exists():
            return None
        data = load_yaml(self.active_path)
        workflow_id = data.get("active_workflow_id", "")
        if not workflow_id:
            return None
        return self.load_metadata(workflow_id)

    def apply_patch_contract(self, workflow: dict[str, Any], values: dict[str, Any], metadata: WorkflowMetadata | None) -> list[str]:
        warnings: list[str] = []
        if not metadata:
            return warnings
        node_inputs = metadata.patch_contract.get("node_inputs", {})
        for field_name, mapping in node_inputs.items():
            value = values.get(field_name)
            optional = bool(mapping.get("optional", True))
            if value in (None, "", [], {}):
                if optional:
                    continue
                warnings.append(f"Required workflow field is empty: {field_name}")
                continue
            node_id = str(mapping.get("node_id", ""))
            input_name = mapping.get("input", "")
            if node_id not in workflow or "inputs" not in workflow[node_id]:
                warnings.append(f"Patch mapping not found in workflow: {field_name} -> node {node_id}")
                continue
            workflow[node_id]["inputs"][input_name] = value
        return warnings


def ensure_default_active_workflow() -> None:
    registry = WorkflowRegistry()
    if registry.get_active():
        return
    workflow_id = "img2img_ipadapter_controlnet_wallpaper_v1"
    workflow_path = PROJECT_ROOT / "workflows" / "comfyui" / f"{workflow_id}.json"
    if not workflow_path.exists():
        return
    data = load_json(workflow_path)
    metadata = WorkflowMetadata(
        workflow_id=workflow_id,
        workflow_json_path=str(workflow_path),
        source_json_path=str(workflow_path),
        imported_time=datetime.now(timezone.utc).isoformat(),
        workflow_type=infer_workflow_type(data),
        supported_inputs=find_placeholders(data),
        optional_modules=infer_optional_modules(data),
        placeholders=find_placeholders(data),
        patch_contract=default_patch_contract(find_placeholders(data)),
        warnings=[],
    )
    registry.write_metadata(metadata)
    registry.set_active(workflow_id)
