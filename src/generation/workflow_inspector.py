from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PLACEHOLDER_WORKFLOW_ERROR = (
    "Current workflow JSON is still a placeholder and cannot be patched. "
    "Please replace it with an actual ComfyUI-exported workflow first."
)

KNOWN_NODE_TYPES = {
    "SaveImage",
    "CheckpointLoaderSimple",
    "VAELoader",
    "CLIPLoader",
    "UNETLoader",
    "CLIPTextEncode",
    "KSampler",
    "KSamplerAdvanced",
    "EmptyLatentImage",
    "EmptySD3LatentImage",
    "EmptyImage",
    "LoraLoader",
    "LoraLoaderModelOnly",
    "ControlNetLoader",
    "VAEDecode",
    "LoadImage",
    "ModelSamplingAuraFlow",
    "ConditioningZeroOut",
}

LOADER_MODEL_KEYS: dict[str, dict[str, str]] = {
    "CheckpointLoaderSimple": {"checkpoint": "ckpt_name"},
    "VAELoader": {"vae": "vae_name"},
    "CLIPLoader": {"text_encoder": "clip_name"},
    "UNETLoader": {"unet": "unet_name"},
    "LoraLoader": {"lora": "lora_name"},
    "LoraLoaderModelOnly": {"lora": "lora_name"},
    "ControlNetLoader": {"controlnet": "control_net_name"},
}

LATENT_NODE_TYPES = {"EmptyLatentImage", "EmptySD3LatentImage", "EmptyImage"}
SAMPLER_NODE_TYPES = {"KSampler", "KSamplerAdvanced"}
PROMPT_NODE_TYPES = {"CLIPTextEncode"}
OUTPUT_NODE_TYPES = {"SaveImage"}
LOADER_NODE_TYPES = set(LOADER_MODEL_KEYS.keys()) | {"LoadImage"}
NODE_ID_PATTERN = re.compile(r"^\d+(?::\d+)*$")


def load_workflow_payload(path: str | Path) -> dict[str, Any]:
    workflow_path = Path(path)
    with workflow_path.open("r", encoding="utf-8") as file:
        workflow = json.load(file)
    return workflow


def inspect_workflow_path(path: str | Path) -> dict[str, Any]:
    payload = load_workflow_payload(path)
    result = inspect_workflow(payload)
    result["source_path"] = str(Path(path).as_posix())
    return result


def inspect_workflow(payload: dict[str, Any]) -> dict[str, Any]:
    format_name = detect_workflow_format(payload)
    if format_name == "placeholder":
        raise ValueError(PLACEHOLDER_WORKFLOW_ERROR)
    if format_name == "comfyui_ui":
        raise ValueError(
            "Workflow JSON appears to be ComfyUI UI format (`nodes` list). "
            "Please export using 'Save (API Format)' for patching."
        )
    if format_name not in {"comfyui_api_prompt", "comfyui_api_prompt_wrapped"}:
        raise ValueError(
            "Workflow JSON is not a recognized ComfyUI API prompt format. "
            "Please provide an actual ComfyUI-exported API workflow JSON."
        )

    prompt_graph = extract_prompt_graph(payload)
    edges = _build_edges(prompt_graph)

    detected_prompt_nodes = _detect_prompt_nodes(prompt_graph, edges)
    detected_sampler_nodes = _detect_sampler_nodes(prompt_graph)
    detected_output_nodes = _detect_output_nodes(prompt_graph)
    detected_latent_nodes = _detect_latent_nodes(prompt_graph)
    detected_loader_nodes, detected_model_files = _detect_loader_nodes_and_models(
        prompt_graph
    )

    class_types = sorted(
        {str(node.get("class_type", "Unknown")) for node in prompt_graph.values()}
    )
    known_node_ids = {
        str(node_id)
        for node_id, node in prompt_graph.items()
        if str(node.get("class_type", "")) in KNOWN_NODE_TYPES
    }
    detected_custom_nodes = []
    unresolved_nodes = []
    for node_id, node in prompt_graph.items():
        class_type = str(node.get("class_type", "Unknown"))
        if class_type not in KNOWN_NODE_TYPES:
            detected_custom_nodes.append(
                {
                    "node_id": str(node_id),
                    "class_type": class_type,
                    "note": "Unknown/custom node type; manual confirmation required.",
                }
            )
            unresolved_nodes.append(
                {
                    "node_id": str(node_id),
                    "class_type": class_type,
                    "reason": "Unsupported semantic parser for this node type.",
                }
            )

    detected_parameters = _collect_detected_parameters(
        detected_prompt_nodes=detected_prompt_nodes,
        detected_sampler_nodes=detected_sampler_nodes,
        detected_latent_nodes=detected_latent_nodes,
        detected_output_nodes=detected_output_nodes,
    )
    families = _infer_model_families(prompt_graph, detected_model_files)

    return {
        "workflow_format": format_name,
        "node_count": len(prompt_graph),
        "class_types": class_types,
        "detected_loader_nodes": detected_loader_nodes,
        "detected_prompt_nodes": detected_prompt_nodes,
        "detected_sampler_nodes": detected_sampler_nodes,
        "detected_output_nodes": detected_output_nodes,
        "detected_latent_nodes": detected_latent_nodes,
        "detected_custom_nodes": detected_custom_nodes,
        "detected_model_files": detected_model_files,
        "detected_parameters": detected_parameters,
        "unresolved_nodes": unresolved_nodes,
        "unknown_nodes": unresolved_nodes,
        "edges": edges,
        "known_node_count": len(known_node_ids),
        "detected_model_families": families,
        "suggested_model_family": families[0] if families else "classic_checkpoint",
    }


def detect_workflow_format(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return "unknown"
    if _is_placeholder_workflow(payload):
        return "placeholder"
    if "nodes" in payload and isinstance(payload["nodes"], list):
        return "comfyui_ui"
    if _is_api_prompt_graph(payload):
        return "comfyui_api_prompt"
    prompt = payload.get("prompt")
    if _is_api_prompt_graph(prompt):
        return "comfyui_api_prompt_wrapped"
    return "unknown"


def extract_prompt_graph(payload: dict[str, Any]) -> dict[str, Any]:
    if _is_api_prompt_graph(payload):
        return payload
    prompt = payload.get("prompt")
    if _is_api_prompt_graph(prompt):
        return prompt
    return {}


def save_inspection_report_json(result: dict[str, Any], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def build_inspection_markdown(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Workflow Inspection Report")
    lines.append("")
    lines.append(f"- workflow_format: `{result.get('workflow_format', 'unknown')}`")
    lines.append(f"- node_count: `{result.get('node_count', 0)}`")
    lines.append(
        f"- suggested_model_family: `{result.get('suggested_model_family', 'unknown')}`"
    )
    lines.append("")
    lines.append("## Detected Node Groups")
    lines.append(
        f"- loader_nodes: {len(result.get('detected_loader_nodes', []))}, "
        f"prompt_nodes: {len(result.get('detected_prompt_nodes', []))}, "
        f"sampler_nodes: {len(result.get('detected_sampler_nodes', []))}, "
        f"latent_nodes: {len(result.get('detected_latent_nodes', []))}, "
        f"output_nodes: {len(result.get('detected_output_nodes', []))}"
    )
    lines.append("")
    lines.append("## Detected Model Files")
    model_files = result.get("detected_model_files", [])
    if model_files:
        for item in model_files:
            lines.append(
                "- "
                + f"{item.get('model_kind')} -> `{item.get('model_name')}` "
                + f"(node {item.get('node_id')} / {item.get('class_type')})"
            )
    else:
        lines.append("- None")
    lines.append("")
    lines.append("## Unresolved / Custom Nodes")
    unresolved = result.get("unresolved_nodes", [])
    if unresolved:
        for item in unresolved:
            lines.append(
                "- "
                + f"node {item.get('node_id')} / {item.get('class_type')}: "
                + f"{item.get('reason')}"
            )
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def save_inspection_report_markdown(
    result: dict[str, Any], output_path: str | Path
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_inspection_markdown(result), encoding="utf-8")
    return output


def _is_placeholder_workflow(payload: dict[str, Any]) -> bool:
    status = payload.get("status")
    if isinstance(status, dict) and bool(status.get("is_placeholder")):
        return True
    placeholder_keys = {"workflow_name", "workflow_type", "planned_nodes"}
    if placeholder_keys.intersection(payload.keys()) and not _is_api_prompt_graph(payload):
        return True
    return False


def _is_api_prompt_graph(payload: Any) -> bool:
    if not isinstance(payload, dict) or not payload:
        return False
    node_keys = [str(key) for key in payload.keys() if _looks_like_node_id(str(key))]
    if not node_keys:
        return False
    for key in node_keys:
        node = payload.get(key)
        if not isinstance(node, dict):
            return False
        if "class_type" not in node:
            return False
        if not isinstance(node.get("inputs"), dict):
            return False
    return True


def _build_edges(prompt_graph: dict[str, Any]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for node_id, node in prompt_graph.items():
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        for input_key, input_value in inputs.items():
            if (
                isinstance(input_value, list)
                and len(input_value) >= 1
                and _looks_like_node_id(str(input_value[0]))
            ):
                edge = {
                    "from_node_id": str(input_value[0]),
                    "to_node_id": str(node_id),
                    "to_input_key": str(input_key),
                    "source_slot": int(input_value[1]) if len(input_value) > 1 else 0,
                }
                edges.append(edge)
    return edges


def _detect_prompt_nodes(
    prompt_graph: dict[str, Any], edges: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    role_by_node: dict[str, str] = {}
    for edge in edges:
        to_node = prompt_graph.get(edge["to_node_id"], {})
        if str(to_node.get("class_type", "")) in SAMPLER_NODE_TYPES:
            input_key = str(edge["to_input_key"]).lower()
            if input_key in {"positive", "negative"}:
                role_by_node[edge["from_node_id"]] = input_key

    out: list[dict[str, Any]] = []
    for node_id, node in prompt_graph.items():
        class_type = str(node.get("class_type", ""))
        if class_type not in PROMPT_NODE_TYPES:
            continue
        inputs = node.get("inputs", {})
        text_key = "text" if "text" in inputs else next(iter(inputs.keys()), "")
        text_value = str(inputs.get(text_key, ""))
        role = role_by_node.get(str(node_id), "unknown")
        title = str((node.get("_meta", {}) or {}).get("title", "")).lower()
        lower_text = text_value.lower()
        if role == "unknown":
            if "negative" in title:
                role = "negative"
            elif "positive" in title or "prompt" in title:
                role = "positive"
        if role == "unknown":
            if any(token in lower_text for token in ["negative", "low quality", "blurry"]):
                role = "negative"
            elif text_value.strip() or "positive" in title:
                role = "positive"
        out.append(
            {
                "node_id": str(node_id),
                "class_type": class_type,
                "role": role,
                "input_key": text_key,
                "text_preview": text_value[:200],
            }
        )
    return out


def _detect_sampler_nodes(prompt_graph: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node_id, node in prompt_graph.items():
        class_type = str(node.get("class_type", ""))
        if class_type not in SAMPLER_NODE_TYPES:
            continue
        inputs = node.get("inputs", {})
        seed_key = "seed" if "seed" in inputs else ("noise_seed" if "noise_seed" in inputs else "")
        sampler_key = "sampler_name" if "sampler_name" in inputs else ("sampler" if "sampler" in inputs else "")
        scheduler_key = "scheduler" if "scheduler" in inputs else ""
        out.append(
            {
                "node_id": str(node_id),
                "class_type": class_type,
                "seed_key": seed_key,
                "steps_key": "steps" if "steps" in inputs else "",
                "cfg_key": "cfg" if "cfg" in inputs else "",
                "sampler_key": sampler_key if sampler_key in inputs else "",
                "scheduler_key": scheduler_key if scheduler_key in inputs else "",
                "denoise_key": "denoise" if "denoise" in inputs else "",
                "values": {
                    "seed": inputs.get(seed_key) if seed_key else None,
                    "steps": inputs.get("steps"),
                    "cfg": inputs.get("cfg"),
                    "sampler": inputs.get(sampler_key),
                    "scheduler": inputs.get(scheduler_key) if scheduler_key else None,
                    "denoise": inputs.get("denoise"),
                },
            }
        )
    return out


def _detect_output_nodes(prompt_graph: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node_id, node in prompt_graph.items():
        class_type = str(node.get("class_type", ""))
        if class_type not in OUTPUT_NODE_TYPES:
            continue
        inputs = node.get("inputs", {})
        out.append(
            {
                "node_id": str(node_id),
                "class_type": class_type,
                "filename_prefix_key": "filename_prefix"
                if "filename_prefix" in inputs
                else "",
                "filename_prefix": inputs.get("filename_prefix", ""),
            }
        )
    return out


def _detect_latent_nodes(prompt_graph: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node_id, node in prompt_graph.items():
        class_type = str(node.get("class_type", ""))
        if class_type not in LATENT_NODE_TYPES:
            continue
        inputs = node.get("inputs", {})
        out.append(
            {
                "node_id": str(node_id),
                "class_type": class_type,
                "width_key": "width" if "width" in inputs else "",
                "height_key": "height" if "height" in inputs else "",
                "batch_size_key": "batch_size" if "batch_size" in inputs else "",
                "width": inputs.get("width"),
                "height": inputs.get("height"),
                "batch_size": inputs.get("batch_size"),
            }
        )
    return out


def _detect_loader_nodes_and_models(
    prompt_graph: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    loader_nodes: list[dict[str, Any]] = []
    model_files: list[dict[str, Any]] = []
    for node_id, node in prompt_graph.items():
        class_type = str(node.get("class_type", ""))
        if class_type not in LOADER_NODE_TYPES:
            continue
        inputs = node.get("inputs", {})
        loader_nodes.append(
            {
                "node_id": str(node_id),
                "class_type": class_type,
                "input_keys": sorted([str(key) for key in inputs.keys()]),
            }
        )

        if class_type == "LoadImage":
            image_name = str(inputs.get("image", "")).strip()
            if image_name:
                model_files.append(
                    {
                        "node_id": str(node_id),
                        "class_type": class_type,
                        "model_kind": "input_image",
                        "input_key": "image",
                        "model_name": image_name,
                    }
                )
            continue

        key_map = LOADER_MODEL_KEYS.get(class_type, {})
        for model_kind, input_key in key_map.items():
            model_name = str(inputs.get(input_key, "")).strip()
            if model_name:
                model_files.append(
                    {
                        "node_id": str(node_id),
                        "class_type": class_type,
                        "model_kind": model_kind,
                        "input_key": input_key,
                        "model_name": model_name,
                    }
                )
    return loader_nodes, model_files


def _collect_detected_parameters(
    detected_prompt_nodes: list[dict[str, Any]],
    detected_sampler_nodes: list[dict[str, Any]],
    detected_latent_nodes: list[dict[str, Any]],
    detected_output_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "positive_prompt": "",
        "negative_prompt": "",
        "seed": None,
        "steps": None,
        "cfg": None,
        "sampler": "",
        "scheduler": "",
        "denoise": None,
        "width": None,
        "height": None,
        "batch_size": None,
        "filename_prefix": "",
    }

    for prompt_node in detected_prompt_nodes:
        role = prompt_node.get("role")
        if role == "positive" and not params["positive_prompt"]:
            params["positive_prompt"] = prompt_node.get("text_preview", "")
        if role == "negative" and not params["negative_prompt"]:
            params["negative_prompt"] = prompt_node.get("text_preview", "")

    if detected_sampler_nodes:
        values = detected_sampler_nodes[0].get("values", {})
        params["seed"] = values.get("seed")
        params["steps"] = values.get("steps")
        params["cfg"] = values.get("cfg")
        params["sampler"] = values.get("sampler") or ""
        params["scheduler"] = values.get("scheduler") or ""
        params["denoise"] = values.get("denoise")

    if detected_latent_nodes:
        params["width"] = detected_latent_nodes[0].get("width")
        params["height"] = detected_latent_nodes[0].get("height")
        params["batch_size"] = detected_latent_nodes[0].get("batch_size")

    if detected_output_nodes:
        params["filename_prefix"] = detected_output_nodes[0].get("filename_prefix", "")

    return params


def _infer_model_families(
    prompt_graph: dict[str, Any], detected_model_files: list[dict[str, Any]]
) -> list[str]:
    class_types = {str(node.get("class_type", "")) for node in prompt_graph.values()}
    model_kinds = {str(item.get("model_kind", "")) for item in detected_model_files}

    families: list[str] = []
    if "CheckpointLoaderSimple" in class_types or "checkpoint" in model_kinds:
        families.append("classic_checkpoint")

    has_split_core = all(
        name in class_types for name in ("UNETLoader", "CLIPLoader", "VAELoader")
    ) or {"unet", "text_encoder", "vae"}.issubset(model_kinds)
    if has_split_core:
        families.append("split_model")

    if "ControlNetLoader" in class_types or "controlnet" in model_kinds:
        families.append("conditioning")
    if "LoraLoader" in class_types or "LoraLoaderModelOnly" in class_types:
        if "conditioning" not in families:
            families.append("conditioning")

    if not families:
        families.append("classic_checkpoint")

    return families


def _looks_like_node_id(value: str) -> bool:
    return bool(NODE_ID_PATTERN.match(value))
