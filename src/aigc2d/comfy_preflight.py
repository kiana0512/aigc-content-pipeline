"""
Pre-submit validation of ComfyUI API-format workflows against GET /object_info.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .comfy_client import ComfyClient


ENUM_INPUT_NAMES = frozenset(
    {
        "ckpt_name",
        "vae_name",
        "lora_name",
        "clip_name",
        "ipadapter_file",
        "control_net_name",
        "model_name",
        "sampler_name",
        "scheduler",
        "upscale_method",
        "weight_type",
        "combine_embeds",
        "embeds_scaling",
    }
)


class _Accumulator:
    def __init__(self) -> None:
        self.errors: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []

    def err(self, code: str, **fields: Any) -> None:
        row: dict[str, Any] = {"code": code, **fields}
        self.errors.append(row)

    def warn(self, code: str, **fields: Any) -> None:
        row: dict[str, Any] = {"code": code, **fields}
        self.warnings.append(row)


def _split_load_image_path(raw: str) -> tuple[str, str]:
    s = raw.replace("\\", "/").strip("/")
    if "/" not in s:
        return "", s
    parent = s.rsplit("/", 1)
    return parent[0], parent[1]


def _gather_input_schema(class_type: str, object_info: dict[str, Any]) -> dict[str, Any]:
    meta = object_info.get(class_type) or {}
    if not isinstance(meta, dict):
        return {}
    inp = meta.get("input") or meta.get("inputs") or {}
    if not isinstance(inp, dict):
        return {}
    merged: dict[str, Any] = {}
    for bucket in ("required", "optional"):
        block = inp.get(bucket)
        if isinstance(block, dict):
            merged.update(block)
    return merged


def _enum_allowed_values(meta: Any, sample_limit: int = 30) -> list[Any]:
    collected: list[Any] = []
    if meta is None:
        return collected
    if isinstance(meta, (list, tuple)) and meta:
        first = meta[0]
        if isinstance(first, (list, tuple)):
            collected.extend(list(first))
    return collected[:sample_limit]


def _effective_allowed(meta: dict[str, Any], input_name: str) -> tuple[list[Any], bool]:
    spec = meta.get(input_name)
    if isinstance(spec, (list, tuple)) and len(spec) >= 1:
        vals = _enum_allowed_values(spec)
        if vals:
            return vals, True
        if isinstance(spec[0], (list, tuple)):
            inner = list(spec[0])
            return inner[:30], bool(inner)
    return [], False


def preflight_workflow_against_comfy(workflow: dict[str, Any], client: ComfyClient) -> dict[str, Any]:
    acc = _Accumulator()
    try:
        object_info = client.get_object_info()
    except Exception as exc:
        acc.err("object_info_failed", message=str(exc))
        return _finalize(acc, len(workflow))

    node_ids = [str(k) for k in workflow.keys()]
    id_set = set(node_ids)

    missing_class_ct = 0
    invalid_enum_ct = 0
    missing_img_ct = 0

    for node_id, node in workflow.items():
        nid = str(node_id)
        if not isinstance(node, dict):
            acc.err("invalid_node_payload", node_id=nid)
            continue
        class_type = str(node.get("class_type") or "")
        if not class_type:
            acc.err("missing_class_type", node_id=nid, detail="empty class_type string")
            continue

        inputs_block = _gather_input_schema(class_type, object_info)
        if class_type not in object_info:
            missing_class_ct += 1
            acc.err("missing_class_type_registration", node_id=nid, class_type=class_type)

        inputs = node.get("inputs") or {}
        if not isinstance(inputs, dict):
            continue

        for input_name, value in inputs.items():
            linked = isinstance(value, list) and len(value) >= 2
            first = value[0] if linked else None
            linked = linked and isinstance(first, str) and str(first).isdigit()
            if linked:
                tgt = str(first)
                if tgt not in id_set:
                    acc.err(
                        "missing_link_node",
                        node_id=nid,
                        input_name=input_name,
                        linked_node_id=tgt,
                        class_type=class_type,
                    )

        if class_type == "LoadImage":
            img = inputs.get("image")
            if isinstance(img, str) and img.strip():
                sub, fname = _split_load_image_path(img.strip())
                if not client.view_image_exists(fname, subfolder=sub, image_type="input"):
                    missing_img_ct += 1
                    acc.err(
                        "missing_input_image",
                        node_id=nid,
                        image=img.strip(),
                        subfolder=sub,
                        filename=fname,
                    )

        for input_name in list(inputs.keys()):
            if input_name not in ENUM_INPUT_NAMES:
                continue
            val = inputs.get(input_name)
            if val is None:
                continue
            if isinstance(val, (list, tuple)):
                continue
            vals, has_list = _effective_allowed(inputs_block, input_name)
            if not has_list or not vals:
                continue
            str_vals = {str(v) for v in vals}
            if str(val) not in str_vals and val not in vals:
                invalid_enum_ct += 1
                sample = vals[:30]
                acc.err(
                    "invalid_enum_value",
                    node_id=nid,
                    class_type=class_type,
                    input_name=input_name,
                    current_value=str(val),
                    allowed_values_sample=sample,
                    allowed_count=len(vals),
                )

    return _finalize(acc, len(workflow), missing_class_ct, invalid_enum_ct, missing_img_ct)


def _finalize(
    acc: _Accumulator,
    node_count: int,
    missing_class_ct: int,
    invalid_enum_ct: int,
    missing_input_image_ct: int,
) -> dict[str, Any]:
    mc = missing_class_ct or sum(
        1 for e in acc.errors if str(e.get("code", "")).startswith("missing_class_type")
    )
    return {
        "ok": len(acc.errors) == 0,
        "errors": acc.errors,
        "warnings": acc.warnings,
        "summary": {
            "node_count": node_count,
            "missing_class_type_count": mc,
            "invalid_enum_count": invalid_enum_ct,
            "missing_input_image_count": missing_input_image_ct,
        },
    }


def resync_load_images_from_patched_fields(
    workflow: dict[str, Any],
    client: ComfyClient,
    patched_fields: dict[str, Any],
    *,
    preferred_subfolder_prefix: str,
) -> dict[str, Any]:
    """If /view misses a LoadImage path, re-upload from local_source_path captured during patch."""
    by_node: dict[str, Path] = {}
    for _fname, meta in (patched_fields or {}).items():
        if not isinstance(meta, dict):
            continue
        lp = meta.get("local_source_path")
        nid = meta.get("node_id")
        if nid and lp:
            pth = Path(str(lp))
            if pth.is_file():
                by_node[str(nid)] = pth

    updated: list[str] = []
    warnings: list[str] = []
    sf_base = preferred_subfolder_prefix.replace("\\", "/").strip("/")

    for nid, node in workflow.items():
        if not isinstance(node, dict) or node.get("class_type") != "LoadImage":
            continue
        inputs = node.get("inputs") or {}
        img = inputs.get("image")
        if not isinstance(img, str) or not img.strip():
            continue
        sub, fname = _split_load_image_path(img.strip())
        if client.view_image_exists(fname, subfolder=sub, image_type="input"):
            continue
        lp = by_node.get(str(nid))
        if not lp or not lp.is_file():
            warnings.append(f"LoadImage node {nid}: missing on server and no local_source_path to re-upload ({img})")
            continue
        sub_target = sf_base or sub
        payload = client.upload_image(lp, subfolder=sub_target)
        new_path = client.load_image_value_from_upload_result(payload)
        node.setdefault("inputs", {})["image"] = new_path
        updated.append(f"{nid}: {new_path}")

    return {"updated": updated, "warnings": warnings}


def workflow_load_image_local_sources(metadata_patch_fields: dict[str, Any]) -> dict[tuple[str, str], Path]:
    """
    From patched_fields captured during WorkflowRuntime.patch: map (node_id, input) -> local source path.

    patched_fields[field] = {"node_id", "input", "value": comfy_path|string}
    We only attach local_path if present.
    """
    out: dict[tuple[str, str], Path] = {}
    for _fname, blob in (metadata_patch_fields or {}).items():
        if not isinstance(blob, dict):
            continue
        lp = blob.get("local_source_path")
        nid = blob.get("node_id")
        inp = blob.get("input")
        if lp and nid and inp:
            p = Path(str(lp))
            if p.is_file():
                out[(str(nid), str(inp))] = p
    return out
