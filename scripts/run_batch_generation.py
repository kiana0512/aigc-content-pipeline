from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import requests
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.generation.comfyui_adapter import (  # noqa: E402
    ComfyUIAdapterError,
    PLACEHOLDER_WORKFLOW_ERROR,
    WorkflowPatchParams,
    load_node_mapping,
    load_workflow_json,
    patch_workflow_with_report,
    save_workflow_json,
)
from src.generation.comfyui_client import ComfyUIClient  # noqa: E402
from src.generation.mapping_suggester import (  # noqa: E402
    suggest_node_mapping,
    save_mapping_diff_markdown,
    save_mapping_manual_review_yaml,
    save_mapping_yaml,
)
from src.generation.prompt_builder import sanitize_filename  # noqa: E402
from src.generation.workflow_inspector import (  # noqa: E402
    detect_workflow_format,
    load_workflow_payload,
    inspect_workflow_path,
    save_inspection_report_json,
    save_inspection_report_markdown,
)
from src.generation.workflow_runner import (  # noqa: E402
    build_comfyui_model_compatibility_report,
    build_run_manifest,
    inspect_workflow_from_config,
    load_prompt_pack_csv,
    load_yaml_config,
    resolve_comfyui_settings,
    resolve_models_from_config,
    save_manifest_json,
    suggest_mapping_from_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Workflow-first batch entrypoint for ComfyUI API workflow operations."
    )
    parser.add_argument("--config", type=str, default="", help="YAML config path.")
    parser.add_argument(
        "--prompt-pack",
        type=str,
        default="",
        help="Optional prompt_pack.csv path.",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="",
        help="Optional manifest output path. Default: results/runs/<run_name>/run_manifest.json",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=[
            "manifest",
            "patch_workflow",
            "submit",
            "inspect_workflow",
            "resolve_models",
            "suggest_mapping",
            "auto_patch_workflow",
            "workflow_import_pipeline",
            "export_default_prompt_pack",
            "scaffold_workflow",
            "import_workflow_scaffold",
            "prepare_workflow_scaffold",
        ],
        default="manifest",
        help="Run mode.",
    )
    parser.add_argument(
        "--workflow-json",
        type=str,
        default="",
        help="Override workflow JSON path from config.comfyui.workflow_json.",
    )
    parser.add_argument(
        "--node-map",
        type=str,
        default="",
        help="Override node map path from config.comfyui.node_map.",
    )
    parser.add_argument(
        "--mapping-mode",
        type=str,
        choices=["manual_map", "auto_detect"],
        default="",
        help="Mapping mode override for patch_workflow: manual_map / auto_detect.",
    )
    parser.add_argument(
        "--comfyui-url",
        type=str,
        default="",
        help="Override ComfyUI base URL for submit mode.",
    )
    parser.add_argument(
        "--client-id",
        type=str,
        default="",
        help="Optional ComfyUI client id for submit mode.",
    )
    parser.add_argument(
        "--comfyui-root",
        type=str,
        default="",
        help="ComfyUI root path override for model resolving.",
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default="",
        help="Optional run name override.",
    )
    parser.add_argument(
        "--slug",
        type=str,
        default="",
        help="Optional scaffold slug. Defaults to inferred slug from workflow JSON file name.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing scaffold target files (with backup).",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run workflow_import_pipeline once after scaffold generation.",
    )
    parser.add_argument(
        "--submit-after-validate",
        action="store_true",
        help="If set with --validate, run submit after validation pipeline.",
    )
    return parser.parse_args()


def _resolve_required_path(cli_value: str, config_value: str, label: str) -> Path:
    value = cli_value.strip() or str(config_value).strip()
    if not value:
        raise ValueError(f"{label} is required for this mode.")
    return Path(value)


def _normalize_mode_alias(mode: str) -> str:
    value = str(mode).strip().lower()
    aliases = {
        "import_workflow_scaffold": "scaffold_workflow",
        "prepare_workflow_scaffold": "scaffold_workflow",
    }
    return aliases.get(value, value)


def _mode_requires_config(mode: str) -> bool:
    return mode in {
        "manifest",
        "patch_workflow",
        "submit",
        "inspect_workflow",
        "resolve_models",
        "suggest_mapping",
        "auto_patch_workflow",
        "workflow_import_pipeline",
        "export_default_prompt_pack",
    }


def _require_config_path_for_mode(args: argparse.Namespace) -> Path:
    config_path_text = str(args.config or "").strip()
    if not config_path_text:
        raise ValueError(f"--config is required for mode `{args.mode}`.")
    return Path(config_path_text)


def _to_snake_slug(value: str) -> str:
    lowered = str(value or "").strip().lower()
    lowered = re.sub(r"[^a-z0-9_]+", "_", lowered)
    lowered = re.sub(r"_+", "_", lowered).strip("_")
    return lowered


def _infer_scaffold_slug(workflow_path: Path, provided_slug: str) -> str:
    if str(provided_slug or "").strip():
        slug = _to_snake_slug(provided_slug)
        if not slug:
            raise ValueError("--slug resolved to empty value; please provide a valid slug.")
        return slug

    stem = workflow_path.stem
    if stem.endswith("_api"):
        stem = stem[:-4]
    slug = _to_snake_slug(stem)
    if not slug:
        raise ValueError("Failed to infer slug from workflow file name.")
    return slug


def _build_item_prefix(item: dict[str, Any], index: int) -> str:
    item_id = str(item.get("item_id", item.get("id", ""))).strip()
    if item_id.isdigit():
        return f"item_{int(item_id):04d}"
    safe_item_id = sanitize_filename(item_id) or f"{index:04d}"
    return f"item_{index:04d}_{safe_item_id}"


def _item_tag(index: int) -> str:
    return f"item_{index:04d}"


def _item_workflow_filename(index: int) -> str:
    return f"{_item_tag(index)}_patched_workflow.json"


def _item_patch_report_filename(index: int) -> str:
    return f"{_item_tag(index)}_patch_report.json"


def _build_default_prompt_rows(config: dict[str, Any]) -> list[dict[str, str]]:
    generation = config.get("generation", {}) or {}
    return [
        {
            "id": "1",
            "prompt_row_index": 1,
            "prompt_row_id": "1",
            "subject": str(generation.get("subject", "smoke_item")),
            "style": "",
            "attributes": "",
            "positive_prompt": str(generation.get("prompt", "")).strip(),
            "positive_prompt_source": "config.generation.prompt",
            "negative_prompt": str(generation.get("negative_prompt", "")).strip(),
            "negative_prompt_source": "config.generation.negative_prompt",
            "negative_prompt_explicit": True,
            "filename_prefix": str(generation.get("filename_prefix", "")).strip(),
            "filename_prefix_source": "config.generation.filename_prefix",
        }
    ]


def _resolve_prompt_rows(args: argparse.Namespace, config: dict[str, Any]) -> list[dict[str, str]]:
    if args.prompt_pack.strip():
        return load_prompt_pack_csv(Path(args.prompt_pack.strip()))
    return _build_default_prompt_rows(config)


def _build_patch_params(
    manifest: dict[str, Any],
    item: dict[str, Any],
    index: int,
    comfy_settings: dict[str, Any],
) -> WorkflowPatchParams:
    output_dir: str | None = None
    if bool(comfy_settings.get("patch_save_image_output_dir", False)):
        raw = str(comfy_settings.get("save_image_output_dir", "")).strip()
        output_dir = raw or None

    filename_prefix = str(item.get("filename_prefix", "")).strip()
    if not filename_prefix:
        base_prefix = str(manifest.get("filename_prefix", "")).strip()
        item_prefix = _build_item_prefix(item, index)
        filename_prefix = f"{base_prefix}/{item_prefix}" if base_prefix else item_prefix

    lora_path = str(item.get("lora_name", "")).strip() or str(
        comfy_settings.get("lora_path", "")
    ).strip()
    lora_strength_raw = item.get("lora_strength_model", "")
    if str(lora_strength_raw).strip():
        try:
            lora_strength = float(lora_strength_raw)
        except ValueError:
            lora_strength = float(comfy_settings.get("lora_strength", 1.0))
    else:
        lora_strength = float(comfy_settings.get("lora_strength", 1.0))

    return WorkflowPatchParams(
        positive_prompt=str(item.get("positive_prompt", "")),
        negative_prompt=str(item.get("negative_prompt", "")),
        seed=int(item.get("seed", manifest.get("seed", 42))),
        width=int(manifest.get("width", 1024)),
        height=int(manifest.get("height", 1024)),
        batch_size=int(manifest.get("batch_size", comfy_settings.get("batch_size", 1))),
        steps=int(manifest.get("num_inference_steps", 30)),
        cfg=float(manifest.get("guidance_scale", 7.0)),
        sampler=str(manifest.get("sampler", "euler")),
        scheduler=str(manifest.get("scheduler", "normal")),
        denoise=float(manifest.get("denoise", comfy_settings.get("denoise", 1.0))),
        filename_prefix=filename_prefix,
        output_dir=output_dir,
        use_lora=bool(comfy_settings.get("use_lora", False)),
        lora_path=lora_path,
        lora_strength=lora_strength,
        use_controlnet=bool(comfy_settings.get("use_controlnet", False)),
        controlnet_model_name=str(comfy_settings.get("controlnet_model_name", "")),
        controlnet_strength=float(comfy_settings.get("controlnet_strength", 0.8)),
        control_image_path=str(
            item.get("control_image_path", comfy_settings.get("control_image_path", ""))
        ),
    )


def _extract_prompt_graph(payload: dict[str, Any]) -> dict[str, Any]:
    prompt = payload.get("prompt")
    if isinstance(prompt, dict):
        return prompt
    return payload


def _load_optional_mapping(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return load_node_mapping(path)


def _get_input_value(
    workflow: dict[str, Any],
    node_id: str,
    input_key: str,
) -> Any:
    graph = _extract_prompt_graph(workflow)
    node = graph.get(str(node_id))
    if not isinstance(node, dict):
        return None
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return None
    return inputs.get(str(input_key))


def _extract_workflow_defaults(
    *,
    workflow: dict[str, Any],
    mapping: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        return {}

    required = mapping.get("required", {}) or {}
    defaults: dict[str, Any] = {}

    positive = required.get("positive_prompt", {}) or {}
    positive_node = str(positive.get("node_id", "")).strip()
    positive_key = str(positive.get("input_key", "")).strip()
    if positive_node and positive_key:
        value = _get_input_value(workflow, positive_node, positive_key)
        if isinstance(value, str):
            defaults["positive_prompt"] = value

    negative = required.get("negative_prompt", {}) or {}
    negative_node = str(negative.get("node_id", "")).strip()
    negative_key = str(negative.get("input_key", "")).strip()
    if negative_node and negative_key:
        value = _get_input_value(workflow, negative_node, negative_key)
        if isinstance(value, str):
            defaults["negative_prompt"] = value
    return defaults


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _resolve_run_dir(
    args: argparse.Namespace,
    config: dict[str, Any],
    workflow_path: Path | None = None,
) -> Path:
    base_root = Path("results") / "runs"
    comfy_settings = resolve_comfyui_settings(config)
    config_run_name = str(comfy_settings.get("run_name", "")).strip()

    if args.run_name.strip():
        run_name = sanitize_filename(args.run_name.strip())
    elif config_run_name:
        run_name = sanitize_filename(config_run_name)
    else:
        stem = workflow_path.stem if workflow_path is not None else "workflow"
        fallback = str(comfy_settings.get("mode", "pipeline")).strip() or "pipeline"
        run_name = sanitize_filename(
            f"{stem}_{fallback}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
    run_name = run_name or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = base_root / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _resolve_manifest_output_path(args: argparse.Namespace, run_dir: Path) -> Path:
    explicit = str(args.output_json or "").strip()
    if explicit:
        return Path(explicit)
    return run_dir / "run_manifest.json"


def _shorten_text(value: str, limit: int = 140) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _print_prompt_override_context(
    *,
    stage: str,
    workflow_path: Path | str | None,
    manifest: dict[str, Any],
) -> None:
    workflow_path_text = str(workflow_path or manifest.get("workflow_path", "")).strip()
    if workflow_path_text:
        print(f"[INFO] {stage}: source workflow path: {workflow_path_text}")

    workflow_default_positive = str(manifest.get("workflow_default_positive_prompt", "")).strip()
    if workflow_default_positive:
        print(
            "[INFO] {stage}: workflow default positive prompt text: \"{text}\"".format(
                stage=stage,
                text=_shorten_text(workflow_default_positive),
            )
        )
    else:
        print(f"[INFO] {stage}: workflow default positive prompt text: <empty or unmapped>")

    print("[INFO] prompt pack values override workflow default prompt text")

    items = manifest.get("items", [])
    for item in items:
        item_index = int(item.get("item_index", 0) or 0)
        positive_prompt = str(
            item.get("final_positive_prompt", item.get("positive_prompt", ""))
        ).strip()
        negative_prompt = str(item.get("negative_prompt", "")).strip()
        print(
            "[INFO] {stage}: item {idx} final positive_prompt=\"{pos}\"".format(
                stage=stage,
                idx=item_index,
                pos=_shorten_text(positive_prompt),
            )
        )
        print(
            "[INFO] {stage}: item {idx} final negative_prompt=\"{neg}\"".format(
                stage=stage,
                idx=item_index,
                neg=_shorten_text(negative_prompt),
            )
        )


def _collect_detected_lora_nodes(inspection: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in inspection.get("detected_loader_nodes", []):
        class_type = str(node.get("class_type", ""))
        if class_type in {"LoraLoader", "LoraLoaderModelOnly"}:
            out.append(node)
    return out


def _collect_detected_model_loaders(inspection: dict[str, Any]) -> list[dict[str, Any]]:
    allowed = {
        "UNETLoader",
        "CheckpointLoaderSimple",
        "CLIPLoader",
        "DualCLIPLoader",
        "VAELoader",
    }
    out: list[dict[str, Any]] = []
    for node in inspection.get("detected_loader_nodes", []):
        class_type = str(node.get("class_type", ""))
        if class_type in allowed:
            out.append(node)
    return out


def _extract_latent_defaults(inspection: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    latent_nodes = inspection.get("detected_latent_nodes", [])
    fallback: list[str] = []
    if latent_nodes:
        chosen = latent_nodes[0]
        width = chosen.get("width")
        height = chosen.get("height")
        batch_size = chosen.get("batch_size")
    else:
        chosen = {}
        width = None
        height = None
        batch_size = None

    if not isinstance(width, int):
        width = 1024
        fallback.append("generation.width")
    if not isinstance(height, int):
        height = 1024
        fallback.append("generation.height")
    if not isinstance(batch_size, int):
        batch_size = 1
        fallback.append("generation.batch_size")
    return {
        "width": int(width),
        "height": int(height),
        "batch_size": int(batch_size),
        "node_id": str(chosen.get("node_id", "")),
    }, fallback


def _extract_sampler_defaults(inspection: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    sampler_nodes = inspection.get("detected_sampler_nodes", [])
    fallback: list[str] = []
    values: dict[str, Any] = {}
    if sampler_nodes:
        values = sampler_nodes[0].get("values", {}) or {}
    seed = values.get("seed")
    steps = values.get("steps")
    cfg = values.get("cfg")
    sampler_name = values.get("sampler")
    scheduler = values.get("scheduler")
    denoise = values.get("denoise")

    if not isinstance(seed, int):
        seed = 42
        fallback.append("runtime.seed")
    if not isinstance(steps, int):
        steps = 30
        fallback.append("generation.num_inference_steps")
    if not isinstance(cfg, (int, float)):
        cfg = 7.0
        fallback.append("generation.guidance_scale")
    if not isinstance(sampler_name, str) or not sampler_name.strip():
        sampler_name = "euler"
        fallback.append("generation.sampler")
    if not isinstance(scheduler, str) or not scheduler.strip():
        scheduler = "normal"
        fallback.append("generation.scheduler")
    if not isinstance(denoise, (int, float)):
        denoise = 1.0
        fallback.append("generation.denoise")

    return {
        "seed": int(seed),
        "steps": int(steps),
        "cfg": float(cfg),
        "sampler": str(sampler_name),
        "scheduler": str(scheduler),
        "denoise": float(denoise),
    }, fallback


def _extract_filename_prefix_default(
    inspection: dict[str, Any], slug: str
) -> tuple[str, list[str]]:
    output_nodes = inspection.get("detected_output_nodes", [])
    fallback: list[str] = []
    if output_nodes:
        value = str(output_nodes[0].get("filename_prefix", "")).strip()
        if value:
            return value, fallback
    fallback.append("generation.filename_prefix")
    return slug, fallback


def _extract_lora_defaults(
    *,
    inspection: dict[str, Any],
    workflow: dict[str, Any],
) -> dict[str, Any] | None:
    prompt_graph = _extract_prompt_graph(workflow)
    for node in _collect_detected_lora_nodes(inspection):
        node_id = str(node.get("node_id", "")).strip()
        if not node_id:
            continue
        raw = prompt_graph.get(node_id, {})
        if not isinstance(raw, dict):
            continue
        inputs = raw.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        lora_name = str(inputs.get("lora_name", "")).strip()
        strength_model = inputs.get("strength_model", inputs.get("strength", 1.0))
        strength_clip = inputs.get("strength_clip")
        payload: dict[str, Any] = {
            "enabled": True,
            "path": lora_name,
            "strength": float(strength_model) if isinstance(strength_model, (int, float)) else 1.0,
            "strength_model": (
                float(strength_model) if isinstance(strength_model, (int, float)) else 1.0
            ),
        }
        if isinstance(strength_clip, (int, float)):
            payload["strength_clip"] = float(strength_clip)
        return payload
    return None


def _infer_model_family_for_scaffold(inspection: dict[str, Any]) -> str:
    loader_nodes = inspection.get("detected_loader_nodes", [])
    class_types = {str(item.get("class_type", "")) for item in loader_nodes}
    if any("Upscale" in class_type for class_type in class_types):
        return "postprocess"
    if "ControlNetLoader" in class_types:
        return "conditioning"
    if {"UNETLoader", "CLIPLoader", "VAELoader"}.intersection(class_types):
        return "split_model"
    if "CheckpointLoaderSimple" in class_types:
        return "classic_checkpoint"
    return str(inspection.get("suggested_model_family", "classic_checkpoint"))


def _write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _render_scaffold_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Scaffold Report",
        "",
        f"- workflow_json_path: `{report.get('workflow_json_path', '')}`",
        f"- slug: `{report.get('slug', '')}`",
        "",
        "## Generated Files",
    ]
    generated_files = report.get("generated_files", [])
    if generated_files:
        lines.extend([f"- `{path}`" for path in generated_files])
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Extracted Defaults",
            f"- positive_prompt: `{report.get('extracted_default_positive_prompt', '')}`",
            f"- negative_prompt: `{report.get('extracted_default_negative_prompt', '')}`",
            f"- filename_prefix: `{report.get('extracted_filename_prefix', '')}`",
        ]
    )

    manual = report.get("manual_review_items", [])
    lines.append("")
    lines.append("## Manual Review Items")
    if manual:
        lines.extend([f"- {item}" for item in manual])
    else:
        lines.append("- None")

    warnings = report.get("warnings", [])
    lines.append("")
    lines.append("## Warnings")
    if warnings:
        lines.extend([f"- {item}" for item in warnings])
    else:
        lines.append("- None")

    next_commands = report.get("next_commands", [])
    lines.append("")
    lines.append("## Next Commands")
    if next_commands:
        lines.extend([f"- `{cmd}`" for cmd in next_commands])
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def _build_next_commands(slug: str) -> list[str]:
    return [
        (
            "python scripts/run_batch_generation.py --config configs/{slug}_api.yaml "
            "--prompt-pack examples/prompt_packs/{slug}_default_from_workflow.csv "
            "--mode workflow_import_pipeline --run-name {slug}_default_round1"
        ).format(slug=slug),
        (
            "python scripts/run_batch_generation.py --config configs/{slug}_api.yaml "
            "--prompt-pack examples/prompt_packs/{slug}_default_from_workflow.csv "
            "--mode submit --run-name {slug}_default_round1"
        ).format(slug=slug),
        (
            "python scripts/run_batch_generation.py --config configs/{slug}_api.yaml "
            "--prompt-pack examples/prompt_packs/{slug}_prompt_pack.csv "
            "--mode workflow_import_pipeline --run-name {slug}_round1"
        ).format(slug=slug),
        (
            "python scripts/run_batch_generation.py --config configs/{slug}_api.yaml "
            "--prompt-pack examples/prompt_packs/{slug}_prompt_pack.csv "
            "--mode submit --run-name {slug}_round1"
        ).format(slug=slug),
        "results/runs/{slug}_round1/".format(slug=slug),
    ]


def _write_next_commands_file(path: Path, commands: list[str]) -> None:
    lines = [
        "# Next Commands",
        "",
        "## Use workflow default prompt",
        commands[0] if len(commands) > 0 else "",
        "",
        commands[1] if len(commands) > 1 else "",
        "",
        "## Use editable prompt pack",
        commands[2] if len(commands) > 2 else "",
        "",
        commands[3] if len(commands) > 3 else "",
        "",
        "## Check outputs",
        commands[4] if len(commands) > 4 else "",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _prepare_scaffold_targets(
    *,
    targets: list[Path],
    force: bool,
    backup_dir: Path,
) -> None:
    existing = [path for path in targets if path.exists()]
    if not existing:
        return
    if not force:
        first = existing[0]
        raise FileExistsError(
            f"File already exists. Use --force to overwrite. Existing path: {first.as_posix()}"
        )

    backup_dir.mkdir(parents=True, exist_ok=True)
    for path in existing:
        rel = path.as_posix().replace("/", "__")
        shutil.copy2(path, backup_dir / rel)


def _validate_workflow_for_scaffold(workflow_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = load_workflow_payload(workflow_path)
    if isinstance(payload.get("nodes"), list):
        raise ValueError(
            "This looks like a ComfyUI UI workflow, not API workflow. Please use Export(API)."
        )
    format_name = detect_workflow_format(payload)
    if format_name == "comfyui_ui":
        raise ValueError(
            "This looks like a ComfyUI UI workflow, not API workflow. Please use Export(API)."
        )
    workflow = load_workflow_json(workflow_path)
    inspection = inspect_workflow_path(workflow_path)
    if not inspection.get("detected_output_nodes", []):
        raise ValueError(
            "Scaffold requires at least one SaveImage or equivalent output node."
        )
    if not inspection.get("detected_prompt_nodes", []):
        raise ValueError(
            "Scaffold requires at least one prompt-related node (for example CLIPTextEncode)."
        )
    return workflow, inspection


def _render_patch_report_markdown(
    item: dict[str, Any],
    report: dict[str, Any],
    output_path: Path,
) -> Path:
    lines = [
        "# Patch Report",
        "",
        f"- item_id: `{item.get('item_id')}`",
        f"- subject: `{item.get('subject')}`",
        f"- mapping_mode: `{report.get('mapping_mode', 'manual_map')}`",
        "",
        "## Patched Fields",
    ]
    patched = report.get("patched_fields", [])
    if patched:
        lines.extend([f"- {value}" for value in patched])
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## Skipped Fields")
    skipped = report.get("skipped_fields", [])
    if skipped:
        lines.extend([f"- {value}" for value in skipped])
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## Unresolved Fields")
    unresolved = report.get("unresolved_fields", [])
    if unresolved:
        lines.extend([f"- {value}" for value in unresolved])
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## Unsupported Fields")
    unsupported = report.get("unsupported_fields", [])
    if unsupported:
        lines.extend([f"- {value}" for value in unsupported])
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## Fallback Fields")
    fallback = report.get("fallback_fields", [])
    if fallback:
        lines.extend([f"- {value}" for value in fallback])
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## Value Sources")
    value_sources = report.get("value_sources", {})
    if isinstance(value_sources, dict) and value_sources:
        for key in sorted(value_sources.keys()):
            lines.append(f"- `{key}`: `{value_sources[key]}`")
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## Prompt Override")
    lines.append(
        "- Workflow default prompt: `{}`".format(
            report.get("workflow_default_prompt", "")
        )
    )
    lines.append(
        "- Final patched prompt: `{}`".format(
            report.get("final_patched_prompt", "")
        )
    )
    lines.append(
        "- Override source: `{}`".format(
            report.get("prompt_override_source", "unknown")
        )
    )
    lines.append(
        "- prompt_override_applied: `{}`".format(
            bool(report.get("prompt_override_applied", False))
        )
    )

    custom_notes = report.get("custom_node_notes", [])
    lines.append("")
    lines.append("## Custom Node Notes")
    if custom_notes:
        lines.extend([f"- {value}" for value in custom_notes])
    else:
        lines.append("- None")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def _render_batch_patch_report_markdown(
    *,
    manifest: dict[str, Any],
    output_path: Path,
) -> Path:
    items = manifest.get("items", [])
    lines = [
        "# Batch Patch Report",
        "",
        f"- run_name: `{manifest.get('run_name', '')}`",
        f"- total_items: `{len(items)}`",
        "",
        "## Items",
    ]
    if not items:
        lines.append("- None")
    else:
        for item in items:
            item_index = int(item.get("item_index", 0) or 0)
            item_id = str(item.get("item_id", item.get("id", ""))).strip() or str(item_index)
            status = str(item.get("patch_status", "unknown"))
            lines.append(
                (
                    f"- item `{item_index}` (id `{item_id}`): "
                    f"status=`{status}`, filename_prefix=`{item.get('filename_prefix', '')}`"
                )
            )
            lines.append(f"  workflow_default_prompt: `{item.get('workflow_default_positive_prompt', '')}`")
            lines.append(f"  final_patched_prompt: `{item.get('final_positive_prompt', item.get('positive_prompt', ''))}`")
            lines.append(f"  override_source: `{item.get('prompt_override_source', 'unknown')}`")
            lines.append(f"  prompt_override_applied: `{bool(item.get('prompt_override_applied', False))}`")
            lines.append(
                f"  patched_workflow_path: `{item.get('patched_workflow_path', '') or 'N/A'}`"
            )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def _print_model_compatibility_report(report: dict[str, Any]) -> None:
    print(f"[INFO] ComfyUI workflow model family: {report['model_family']}")
    print(f"[INFO] {report['model_family_note']}")
    print("[INFO] Required model directories: " + ", ".join(report["required_dirs"]))

    if report["recommended_dirs"]:
        print(
            "[INFO] Recommended model directories: "
            + ", ".join(report["recommended_dirs"])
        )
    if report["optional_dirs"]:
        print("[INFO] Optional model directories: " + ", ".join(report["optional_dirs"]))
    if report["missing_required_dirs"]:
        level = "WARN" if not report["strict"] else "ERROR"
        print(
            f"[{level}] Missing required model directory declarations: "
            + ", ".join(report["missing_required_dirs"])
        )
    if report["missing_recommended_dirs"]:
        print(
            "[WARN] Missing recommended model directory declarations: "
            + ", ".join(report["missing_recommended_dirs"])
        )


def _resolve_workflow_path(args: argparse.Namespace, config: dict[str, Any]) -> Path:
    comfy_settings = resolve_comfyui_settings(config)
    return _resolve_required_path(
        args.workflow_json,
        str(comfy_settings.get("workflow_json", "")),
        "ComfyUI workflow JSON",
    )


def _resolve_mapping_path(
    args: argparse.Namespace, config: dict[str, Any], required: bool
) -> Path | None:
    comfy_settings = resolve_comfyui_settings(config)
    value = args.node_map.strip() or str(comfy_settings.get("node_map", "")).strip()
    if not value:
        if required:
            raise ValueError("ComfyUI node map YAML is required in manual_map mode.")
        return None
    return Path(value)


def _is_strict_model_check(config: dict[str, Any]) -> bool:
    comfy = config.get("comfyui", {}) or {}
    return bool(comfy.get("strict_model_dir_check", False))


def _assert_model_resolution_if_strict(config: dict[str, Any], report: dict[str, Any]) -> None:
    if not _is_strict_model_check(config):
        return
    summary = report.get("resolution", {}).get("summary", {})
    missing = int(summary.get("missing_count", 0))
    if missing > 0:
        raise RuntimeError(
            f"strict_model_dir_check=true and {missing} model references are unresolved."
        )


def _build_manifest_if_needed(
    args: argparse.Namespace,
    config: dict[str, Any],
    run_dir: Path,
    force: bool = False,
) -> dict[str, Any] | None:
    if args.mode not in {
        "manifest",
        "patch_workflow",
        "submit",
        "auto_patch_workflow",
        "workflow_import_pipeline",
    } and not force:
        return None
    prompt_rows = _resolve_prompt_rows(args, config)
    workflow_defaults: dict[str, Any] = {}
    workflow_path_text = ""
    try:
        workflow_path = _resolve_workflow_path(args, config)
        workflow_path_text = str(workflow_path.as_posix())
        mapping_path = _resolve_mapping_path(args, config, required=False)
        mapping = _load_optional_mapping(mapping_path)
        workflow_defaults = _extract_workflow_defaults(
            workflow=load_workflow_json(workflow_path),
            mapping=mapping,
        )
    except Exception:
        workflow_defaults = {}

    manifest = build_run_manifest(
        config,
        prompt_rows,
        config_path=args.config,
        prompt_pack_path=str(args.prompt_pack or "").strip(),
        workflow_path=workflow_path_text,
        workflow_defaults=workflow_defaults,
    )
    manifest["run_name"] = run_dir.name
    output_path = _resolve_manifest_output_path(args, run_dir)
    save_manifest_json(manifest, output_path)
    print(f"[OK] Run manifest created: {output_path}")
    print(f"[OK] Number of generation items: {len(manifest['items'])}")
    if args.mode == "submit":
        _print_prompt_override_context(
            stage="submit",
            workflow_path=workflow_path_text,
            manifest=manifest,
        )
    return manifest


def run_inspect_workflow(args: argparse.Namespace, config: dict[str, Any]) -> None:
    workflow_path = _resolve_workflow_path(args, config)
    run_dir = _resolve_run_dir(args=args, config=config, workflow_path=workflow_path)
    inspection = inspect_workflow_path(workflow_path)
    json_path = run_dir / "workflow_inspection.json"
    md_path = run_dir / "workflow_inspection.md"
    save_inspection_report_json(inspection, json_path)
    save_inspection_report_markdown(inspection, md_path)
    print(f"[OK] Workflow inspected: {workflow_path}")
    print(f"[OK] Inspection JSON: {json_path}")
    print(f"[OK] Inspection Markdown: {md_path}")


def run_resolve_models(args: argparse.Namespace, config: dict[str, Any]) -> None:
    workflow_path = _resolve_workflow_path(args, config)
    run_dir = _resolve_run_dir(args=args, config=config, workflow_path=workflow_path)
    inspection = inspect_workflow_path(workflow_path)
    root_override = args.comfyui_root.strip() or None
    report = resolve_models_from_config(config, inspection, comfyui_root=root_override)
    _assert_model_resolution_if_strict(config, report)
    output_path = run_dir / "model_resolution.json"
    _write_json(output_path, report)
    summary = report.get("resolution", {}).get("summary", {})
    print(f"[OK] Model resolution completed for: {workflow_path}")
    print(
        "[OK] resolved={resolved_count}, missing={missing_count}, maybe={maybe_count}, "
        "duplicate={duplicate_count}".format(
            resolved_count=summary.get("resolved_count", 0),
            missing_count=summary.get("missing_count", 0),
            maybe_count=summary.get("maybe_count", 0),
            duplicate_count=summary.get("duplicate_count", 0),
        )
    )
    print(f"[OK] Model resolution report: {output_path}")


def run_suggest_mapping(args: argparse.Namespace, config: dict[str, Any]) -> None:
    workflow_path = _resolve_workflow_path(args, config)
    run_dir = _resolve_run_dir(args=args, config=config, workflow_path=workflow_path)
    inspection = inspect_workflow_path(workflow_path)
    mapping_path = _resolve_mapping_path(args, config, required=False)
    existing_mapping = _load_optional_mapping(mapping_path)
    suggestion = suggest_mapping_from_config(
        config=config, inspection_result=inspection, existing_mapping=existing_mapping
    )
    output_yaml = run_dir / "mapping_suggestion.yaml"
    output_json = run_dir / "mapping_suggestion_report.json"
    output_diff_md = run_dir / "mapping_diff.md"
    output_manual_review = run_dir / "mapping_manual_review.yaml"
    save_mapping_yaml(suggestion["mapping"], output_yaml)
    save_mapping_diff_markdown(suggestion.get("diff_vs_existing", {}), output_diff_md)
    save_mapping_manual_review_yaml(suggestion, output_manual_review)
    _write_json(output_json, suggestion)
    print(f"[OK] Mapping suggestion generated for: {workflow_path}")
    print(f"[OK] Suggested node map YAML: {output_yaml}")
    print(f"[OK] Suggestion report JSON: {output_json}")
    print(f"[OK] Mapping diff Markdown: {output_diff_md}")
    print(f"[OK] Manual review YAML: {output_manual_review}")


def _collect_prompt_candidates(
    *,
    workflow: dict[str, Any],
    inspection: dict[str, Any],
) -> list[dict[str, Any]]:
    graph = _extract_prompt_graph(workflow)
    candidates: list[dict[str, Any]] = []
    for node in inspection.get("detected_prompt_nodes", []):
        node_id = str(node.get("node_id", "")).strip()
        input_key = str(node.get("input_key", "text")).strip() or "text"
        value = _get_input_value(graph, node_id, input_key)
        text = str(value).strip() if isinstance(value, str) else ""
        candidates.append(
            {
                "node_id": node_id,
                "role": str(node.get("role", "unknown")),
                "input_key": input_key,
                "text": text,
            }
        )
    return candidates


def _select_default_prompts_for_scaffold(
    *,
    workflow: dict[str, Any],
    inspection: dict[str, Any],
    mapping: dict[str, Any],
) -> tuple[str, str, list[str], list[str]]:
    defaults = _extract_workflow_defaults(workflow=workflow, mapping=mapping)
    positive = str(defaults.get("positive_prompt", "")).strip()
    negative = str(defaults.get("negative_prompt", "")).strip()
    warnings: list[str] = []
    manual_review_items: list[str] = []

    candidates = _collect_prompt_candidates(workflow=workflow, inspection=inspection)
    positive_candidates = [item for item in candidates if item.get("role") == "positive"]
    if len(positive_candidates) > 1:
        manual_review_items.append(
            "Multiple positive prompt nodes detected; auto-selected highest-confidence mapping."
        )
    if not positive:
        preferred = positive_candidates or [item for item in candidates if item.get("text", "")]
        if preferred:
            positive = str(preferred[0].get("text", "")).strip()
            warnings.append("positive_prompt fallback used first detected prompt node text.")

    negative_candidates = [item for item in candidates if item.get("role") == "negative"]
    if not negative and negative_candidates:
        negative = str(negative_candidates[0].get("text", "")).strip()
        warnings.append("negative_prompt fallback used detected negative prompt node text.")
    if not negative_candidates:
        manual_review_items.append("No negative_prompt node detected; negative prompt left empty.")
    return positive, negative, warnings, manual_review_items


def _build_scaffold_config_payload(
    *,
    slug: str,
    workflow_json_path: Path,
    node_map_path: Path,
    prompt_pack_path: Path,
    positive_prompt: str,
    negative_prompt: str,
    filename_prefix: str,
    latent_defaults: dict[str, Any],
    sampler_defaults: dict[str, Any],
    model_family: str,
    lora_defaults: dict[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt_pack_default": str(prompt_pack_path.as_posix()),
        "project": {
            "name": "game-aigc-asset-workflow",
            "task_group": "workflow_scaffold",
            "stage": "scaffold_generated",
            "description": f"Auto-generated scaffold config for {slug}.",
        },
        "task": {
            "type": "baseline_generation",
            "asset_type": "concept_art",
            "scenario": f"{slug}_scaffold",
            "target_engine": "UE5",
        },
        "runtime": {
            "seed": int(sampler_defaults["seed"]),
            "device": "cuda",
            "dtype": "fp16",
            "mixed_precision": True,
        },
        "generation": {
            "prompt": positive_prompt,
            "negative_prompt": negative_prompt,
            "width": int(latent_defaults["width"]),
            "height": int(latent_defaults["height"]),
            "batch_size": int(latent_defaults["batch_size"]),
            "num_images": 1,
            "num_inference_steps": int(sampler_defaults["steps"]),
            "guidance_scale": float(sampler_defaults["cfg"]),
            "sampler": str(sampler_defaults["sampler"]),
            "scheduler": str(sampler_defaults["scheduler"]),
            "denoise": float(sampler_defaults["denoise"]),
            "filename_prefix": filename_prefix,
            "output_subdir": f"outputs/{slug}",
        },
        "model": {
            "family": model_family,
            "base_model_name": slug,
            "variant": "api_workflow",
            "use_lora": bool(lora_defaults),
            "lora_path": str((lora_defaults or {}).get("path", "")),
            "lora_strength": float((lora_defaults or {}).get("strength_model", 1.0)),
            "use_controlnet": False,
            "controlnet_model_name": "",
            "controlnet_strength": 0.8,
        },
        "comfyui": {
            "enabled": True,
            "comfyui_root": "ComfyUI",
            "base_url": "http://127.0.0.1:8000",
            "run_name": f"{slug}_api",
            "mode": "workflow_import_pipeline",
            "mapping_mode": "manual_map",
            "workflow_json": str(workflow_json_path.as_posix()),
            "node_map": str(node_map_path.as_posix()),
            "default_prompt_pack": str(prompt_pack_path.as_posix()),
            "workflow_model_family": model_family,
            "strict_model_dir_check": False,
            "patch_save_image_output_dir": False,
            "save_image_output_dir": "",
        },
        "lora": {
            "enabled": bool(lora_defaults),
            "path": str((lora_defaults or {}).get("path", "")),
            "strength": float((lora_defaults or {}).get("strength_model", 1.0)),
            "strength_model": float((lora_defaults or {}).get("strength_model", 1.0)),
        },
        "controlnet": {
            "enabled": False,
            "model_name": "",
            "control_image_path": "",
            "strength": 0.8,
        },
    }
    if lora_defaults and "strength_clip" in lora_defaults:
        payload["lora"]["strength_clip"] = float(lora_defaults["strength_clip"])
    return payload


def _run_scaffold_validate(
    *,
    config_path: Path,
    prompt_pack_path: Path,
    slug: str,
    submit_after_validate: bool,
) -> dict[str, Any]:
    validate_run_name = f"{slug}_scaffold_validate"
    result: dict[str, Any] = {
        "enabled": True,
        "run_name": validate_run_name,
        "submit_after_validate": bool(submit_after_validate),
        "pipeline_success": False,
        "submit_success": False,
        "error": "",
    }
    config = load_yaml_config(config_path)
    args_pipeline = argparse.Namespace(
        config=str(config_path.as_posix()),
        prompt_pack=str(prompt_pack_path.as_posix()),
        output_json="",
        mode="workflow_import_pipeline",
        workflow_json="",
        node_map="",
        mapping_mode="",
        comfyui_url="",
        client_id="",
        comfyui_root="",
        run_name=validate_run_name,
        slug="",
        force=False,
        validate=False,
        submit_after_validate=False,
    )
    run_workflow_import_pipeline(args_pipeline, config)
    result["pipeline_success"] = True

    if submit_after_validate:
        args_submit = argparse.Namespace(
            config=str(config_path.as_posix()),
            prompt_pack=str(prompt_pack_path.as_posix()),
            output_json="",
            mode="submit",
            workflow_json="",
            node_map="",
            mapping_mode="manual_map",
            comfyui_url="",
            client_id="",
            comfyui_root="",
            run_name=validate_run_name,
            slug="",
            force=False,
            validate=False,
            submit_after_validate=False,
        )
        workflow_path = _resolve_workflow_path(args_submit, config)
        run_dir = _resolve_run_dir(args=args_submit, config=config, workflow_path=workflow_path)
        manifest = _build_manifest_if_needed(args_submit, config, run_dir=run_dir)
        if manifest is None:
            raise RuntimeError("Validate submit failed: manifest could not be generated.")
        _patch_workflows_common(
            args=args_submit,
            config=config,
            manifest=manifest,
            run_dir=run_dir,
            submit=True,
            force_auto_mode=False,
        )
        result["submit_success"] = True
    return result


def run_scaffold_workflow(args: argparse.Namespace) -> None:
    workflow_path_text = str(args.workflow_json or "").strip()
    if not workflow_path_text:
        raise ValueError("--workflow-json is required for scaffold_workflow.")
    workflow_path = Path(workflow_path_text)
    if not workflow_path.exists():
        raise FileNotFoundError(f"Workflow JSON not found: {workflow_path.as_posix()}")

    slug = _infer_scaffold_slug(workflow_path, str(args.slug or ""))
    run_dir = Path("results") / "runs" / f"scaffold_{slug}"
    run_dir.mkdir(parents=True, exist_ok=True)

    workflow, inspection = _validate_workflow_for_scaffold(workflow_path)
    mapping_suggestion = suggest_node_mapping(inspection_result=inspection, existing_mapping=None)
    mapping = mapping_suggestion["mapping"]
    required = mapping.get("required", {}) if isinstance(mapping, dict) else {}
    if isinstance(required, dict):
        negative_binding = required.get("negative_prompt", {})
        if isinstance(negative_binding, dict):
            node_id = str(negative_binding.get("node_id", "")).strip()
            if not node_id:
                negative_binding["node_id"] = ""
                negative_binding["input_key"] = ""

    positive_default, negative_default, prompt_warnings, prompt_manual_review = (
        _select_default_prompts_for_scaffold(
            workflow=workflow,
            inspection=inspection,
            mapping=mapping,
        )
    )
    if not positive_default:
        raise ValueError("Failed to extract default positive prompt from workflow.")

    latent_defaults, latent_fallback = _extract_latent_defaults(inspection)
    sampler_defaults, sampler_fallback = _extract_sampler_defaults(inspection)
    filename_prefix, prefix_fallback = _extract_filename_prefix_default(inspection, slug)
    lora_defaults = _extract_lora_defaults(inspection=inspection, workflow=workflow)
    model_family = _infer_model_family_for_scaffold(inspection)

    config_path = Path("configs") / f"{slug}_api.yaml"
    node_map_path = Path("configs") / "node_maps" / f"{slug}_node_map.yaml"
    default_prompt_pack_path = (
        Path("examples") / "prompt_packs" / f"{slug}_default_from_workflow.csv"
    )
    editable_prompt_pack_path = Path("examples") / "prompt_packs" / f"{slug}_prompt_pack.csv"
    scaffold_report_json_path = run_dir / "scaffold_report.json"
    scaffold_report_md_path = run_dir / "scaffold_report.md"
    next_commands_path = run_dir / "next_commands.md"

    _prepare_scaffold_targets(
        targets=[config_path, node_map_path, default_prompt_pack_path, editable_prompt_pack_path],
        force=bool(args.force),
        backup_dir=run_dir / "backup",
    )

    config_payload = _build_scaffold_config_payload(
        slug=slug,
        workflow_json_path=workflow_path,
        node_map_path=node_map_path,
        prompt_pack_path=editable_prompt_pack_path,
        positive_prompt=positive_default,
        negative_prompt=negative_default,
        filename_prefix=filename_prefix,
        latent_defaults=latent_defaults,
        sampler_defaults=sampler_defaults,
        model_family=model_family,
        lora_defaults=lora_defaults,
    )

    unsupported_fields: list[str] = []
    neg = required.get("negative_prompt", {}) if isinstance(required, dict) else {}
    if not str(neg.get("node_id", "")).strip():
        unsupported_fields.append("negative_prompt")

    manual_review_items = list(mapping_suggestion.get("needs_manual_confirmation", []))
    manual_review_items.extend(prompt_manual_review)
    warnings = list(prompt_warnings)
    if _collect_detected_lora_nodes(inspection) and not lora_defaults:
        manual_review_items.append("LoRA node exists but defaults could not be extracted.")
    if "generation.batch_size" in latent_fallback:
        manual_review_items.append("batch_size field not found in latent node; fallback value used.")
    for custom in inspection.get("detected_custom_nodes", []):
        manual_review_items.append(
            "Unrecognized custom node: {class_type} (node {node_id})".format(
                class_type=custom.get("class_type", "unknown"),
                node_id=custom.get("node_id", ""),
            )
        )

    save_mapping_yaml(mapping, node_map_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(config_payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    _write_csv_rows(
        default_prompt_pack_path,
        fieldnames=["id", "positive_prompt", "negative_prompt", "filename_prefix"],
        rows=[
            {
                "id": "1",
                "positive_prompt": positive_default,
                "negative_prompt": negative_default,
                "filename_prefix": filename_prefix,
            }
        ],
    )
    _write_csv_rows(
        editable_prompt_pack_path,
        fieldnames=[
            "id",
            "subject",
            "style",
            "attributes",
            "positive_prompt",
            "negative_prompt",
            "filename_prefix",
        ],
        rows=[
            {
                "id": "1",
                "subject": slug,
                "style": "workflow_default",
                "attributes": "imported_from_comfyui",
                "positive_prompt": positive_default,
                "negative_prompt": negative_default,
                "filename_prefix": filename_prefix,
            }
        ],
    )

    next_commands = _build_next_commands(slug)
    _write_next_commands_file(next_commands_path, next_commands)

    report: dict[str, Any] = {
        "workflow_json_path": str(workflow_path.as_posix()),
        "slug": slug,
        "generated_files": [
            str(config_path.as_posix()),
            str(node_map_path.as_posix()),
            str(default_prompt_pack_path.as_posix()),
            str(editable_prompt_pack_path.as_posix()),
            str(scaffold_report_json_path.as_posix()),
            str(scaffold_report_md_path.as_posix()),
            str(next_commands_path.as_posix()),
        ],
        "detected_nodes": {
            "node_count": int(inspection.get("node_count", 0)),
            "class_types": inspection.get("class_types", []),
        },
        "detected_prompt_nodes": inspection.get("detected_prompt_nodes", []),
        "detected_sampler_nodes": inspection.get("detected_sampler_nodes", []),
        "detected_size_nodes": inspection.get("detected_latent_nodes", []),
        "detected_save_nodes": inspection.get("detected_output_nodes", []),
        "detected_lora_nodes": _collect_detected_lora_nodes(inspection),
        "detected_model_loaders": _collect_detected_model_loaders(inspection),
        "generated_node_map": mapping,
        "config_defaults": {
            "width": latent_defaults["width"],
            "height": latent_defaults["height"],
            "batch_size": latent_defaults["batch_size"],
            "seed": sampler_defaults["seed"],
            "steps": sampler_defaults["steps"],
            "cfg": sampler_defaults["cfg"],
            "sampler_name": sampler_defaults["sampler"],
            "scheduler": sampler_defaults["scheduler"],
            "denoise": sampler_defaults["denoise"],
            "filename_prefix": filename_prefix,
            "fallback_fields": sorted(set(latent_fallback + sampler_fallback + prefix_fallback)),
            "model_family": model_family,
        },
        "extracted_default_positive_prompt": positive_default,
        "extracted_default_negative_prompt": negative_default,
        "extracted_filename_prefix": filename_prefix,
        "unsupported_fields": unsupported_fields,
        "manual_review_items": sorted(set(manual_review_items)),
        "warnings": sorted(set(warnings)),
        "next_commands": next_commands,
        "validate": {"enabled": bool(args.validate), "run_name": "", "pipeline_success": False},
    }

    if args.validate:
        validate_result = _run_scaffold_validate(
            config_path=config_path,
            prompt_pack_path=default_prompt_pack_path,
            slug=slug,
            submit_after_validate=bool(args.submit_after_validate),
        )
        report["validate"] = validate_result

    _write_json(scaffold_report_json_path, report)
    scaffold_report_md_path.write_text(
        _render_scaffold_report_markdown(report),
        encoding="utf-8",
    )

    print(f"[OK] Scaffold completed for slug: {slug}")
    print(f"[OK] Generated config: {config_path.as_posix()}")
    print(f"[OK] Generated node map: {node_map_path.as_posix()}")
    print(f"[OK] Generated default prompt pack: {default_prompt_pack_path.as_posix()}")
    print(f"[OK] Generated editable prompt pack: {editable_prompt_pack_path.as_posix()}")
    print(f"[OK] Scaffold report JSON: {scaffold_report_json_path.as_posix()}")
    print(f"[OK] Scaffold report Markdown: {scaffold_report_md_path.as_posix()}")
    print(f"[OK] Next commands: {next_commands_path.as_posix()}")


def run_export_default_prompt_pack(args: argparse.Namespace, config: dict[str, Any]) -> None:
    workflow_path = _resolve_workflow_path(args, config)
    mapping_path = _resolve_mapping_path(args, config, required=False)
    mapping = _load_optional_mapping(mapping_path)
    workflow = load_workflow_json(workflow_path)
    defaults = _extract_workflow_defaults(workflow=workflow, mapping=mapping)

    generation_cfg = config.get("generation", {}) or {}
    positive_prompt = str(defaults.get("positive_prompt", "")).strip() or str(
        generation_cfg.get("prompt", "")
    ).strip()
    negative_prompt = str(defaults.get("negative_prompt", "")).strip() or str(
        generation_cfg.get("negative_prompt", "")
    ).strip()
    filename_prefix = str(generation_cfg.get("filename_prefix", "")).strip()

    base_stem = sanitize_filename(Path(args.config).stem) or sanitize_filename(workflow_path.stem)
    if base_stem.endswith("_api"):
        base_stem = base_stem[:-4]
    if base_stem.startswith("image_"):
        base_stem = base_stem[len("image_") :]
    base_stem = base_stem or "workflow"

    output_path = Path("examples") / "prompt_packs" / f"{base_stem}_default_from_workflow.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["id", "positive_prompt", "negative_prompt", "filename_prefix"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "1",
                "positive_prompt": positive_prompt,
                "negative_prompt": negative_prompt,
                "filename_prefix": filename_prefix,
            }
        )

    print(f"[INFO] source workflow path: {workflow_path.as_posix()}")
    print(
        '[INFO] workflow default positive prompt text: "{}"'.format(
            _shorten_text(str(defaults.get("positive_prompt", "")).strip())
        )
    )
    print(f"[OK] Exported default prompt pack: {output_path.as_posix()}")


def run_workflow_import_pipeline(args: argparse.Namespace, config: dict[str, Any]) -> None:
    workflow_path = _resolve_workflow_path(args, config)
    run_dir = _resolve_run_dir(args=args, config=config, workflow_path=workflow_path)

    inspection = inspect_workflow_path(workflow_path)
    _write_json(run_dir / "workflow_inspection.json", inspection)

    root_override = args.comfyui_root.strip() or None
    model_report = resolve_models_from_config(
        config=config, inspection_result=inspection, comfyui_root=root_override
    )
    _assert_model_resolution_if_strict(config, model_report)
    _write_json(run_dir / "model_resolution.json", model_report)

    mapping_path = _resolve_mapping_path(args, config, required=False)
    existing_mapping = _load_optional_mapping(mapping_path)
    suggestion = suggest_mapping_from_config(
        config=config,
        inspection_result=inspection,
        existing_mapping=existing_mapping,
    )
    save_mapping_yaml(suggestion["mapping"], run_dir / "mapping_suggestion.yaml")
    save_mapping_diff_markdown(
        suggestion.get("diff_vs_existing", {}), run_dir / "mapping_diff.md"
    )
    save_mapping_manual_review_yaml(suggestion, run_dir / "mapping_manual_review.yaml")

    prompt_rows = _resolve_prompt_rows(args, config)
    workflow_defaults = _extract_workflow_defaults(
        workflow=load_workflow_json(workflow_path),
        mapping=suggestion.get("mapping"),
    )
    manifest = build_run_manifest(
        config,
        prompt_rows,
        config_path=args.config,
        prompt_pack_path=str(args.prompt_pack or "").strip(),
        workflow_path=str(workflow_path.as_posix()),
        workflow_defaults=workflow_defaults,
    )
    manifest["run_name"] = run_dir.name
    save_manifest_json(manifest, run_dir / "run_manifest.json")
    _print_prompt_override_context(
        stage="workflow_import_pipeline",
        workflow_path=workflow_path,
        manifest=manifest,
    )

    _patch_workflows_common(
        args=args,
        config=config,
        manifest=manifest,
        run_dir=run_dir,
        submit=False,
        force_auto_mode=True,
        mapping_override=suggestion.get("mapping"),
        mapping_mode_override="auto_detect",
        workflow_path_override=workflow_path,
    )

    print(f"[OK] workflow-first pipeline completed. Output directory: {run_dir}")


def _resolve_mapping_mode(args: argparse.Namespace, config: dict[str, Any], auto: bool = False) -> str:
    if auto:
        return "auto_detect"
    comfy_settings = resolve_comfyui_settings(config)
    value = args.mapping_mode.strip() or str(comfy_settings.get("mapping_mode", "manual_map"))
    value = value.strip().lower() or "manual_map"
    if value not in {"manual_map", "auto_detect"}:
        raise ValueError("mapping_mode must be `manual_map` or `auto_detect`.")
    return value


def _extract_submit_error(exc: Exception) -> tuple[str, Any]:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        try:
            payload = exc.response.json()
        except Exception:
            payload = {"raw_text": exc.response.text}
        if isinstance(payload, dict):
            return str(payload.get("error", exc)), payload.get("node_errors", {})
        return str(exc), {}
    return str(exc), {}


def _is_mapping_field_supported(mapping: dict[str, Any] | None, field: str) -> bool:
    if not isinstance(mapping, dict):
        return False
    required = mapping.get("required", {}) or {}
    if field == "negative_prompt":
        neg = required.get("negative_prompt", {}) or {}
        return bool(str(neg.get("node_id", "")).strip() and str(neg.get("input_key", "")).strip())
    if field == "positive_prompt":
        pos = required.get("positive_prompt", {}) or {}
        return bool(str(pos.get("node_id", "")).strip() and str(pos.get("input_key", "")).strip())
    return False


def _build_value_sources(manifest: dict[str, Any], item: dict[str, Any]) -> dict[str, str]:
    param_sources = manifest.get("parameter_sources", {}) or {}
    return {
        "positive_prompt": str(item.get("positive_prompt_source", "unknown")),
        "negative_prompt": str(item.get("negative_prompt_source", "unknown")),
        "filename_prefix": str(item.get("filename_prefix_source", "defer_to_runtime")),
        "seed": str(item.get("seed_source", param_sources.get("seed", "config.runtime.seed"))),
        "width": str(param_sources.get("width", "config.generation.width")),
        "height": str(param_sources.get("height", "config.generation.height")),
        "batch_size": str(param_sources.get("batch_size", "config.generation.batch_size")),
        "steps": str(
            param_sources.get("num_inference_steps", "config.generation.num_inference_steps")
        ),
        "cfg": str(param_sources.get("guidance_scale", "config.generation.guidance_scale")),
        "sampler_name": str(param_sources.get("sampler", "config.generation.sampler")),
        "scheduler": str(param_sources.get("scheduler", "config.generation.scheduler")),
        "denoise": str(param_sources.get("denoise", "config.generation.denoise")),
        "lora_name": (
            "prompt_pack.lora_name"
            if str(item.get("lora_name", "")).strip()
            else "config.lora.path|model.lora_path"
        ),
        "lora_strength_model": (
            "prompt_pack.lora_strength_model"
            if str(item.get("lora_strength_model", "")).strip()
            else "config.lora.strength|model.lora_strength"
        ),
    }


def _build_fallback_fields(value_sources: dict[str, str]) -> list[str]:
    fallback_fields: list[str] = []
    fallback_markers = ("config.", "workflow_default.", "defer_", "prompt_pack.composed")
    for key, value in value_sources.items():
        if any(marker in value for marker in fallback_markers):
            fallback_fields.append(f"{key} <- {value}")
    return fallback_fields


def _build_unsupported_fields(
    *,
    mapping: dict[str, Any] | None,
    params: WorkflowPatchParams,
) -> list[str]:
    if not isinstance(mapping, dict):
        return []
    unsupported: list[str] = []
    if params.negative_prompt.strip() and not _is_mapping_field_supported(mapping, "negative_prompt"):
        unsupported.append(
            "negative_prompt: workflow does not provide mapped negative prompt node/input; ignored."
        )
    return unsupported


def _resolve_manifest_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    items = manifest.get("items", [])
    if not isinstance(items, list):
        return []
    for index, item in enumerate(items, start=1):
        item["item_index"] = int(item.get("item_index", index) or index)
        item_id = str(item.get("item_id", item.get("id", ""))).strip() or str(index)
        item["item_id"] = item_id
        item["id"] = str(item.get("id", item_id)).strip() or item_id
        if str(item.get("seed", "")).strip():
            try:
                item["seed"] = int(item.get("seed"))
            except (TypeError, ValueError):
                item["seed"] = int(manifest.get("seed", 42))
        else:
            item["seed"] = int(manifest.get("seed", 42))
        item.setdefault("seed_source", "config.runtime.seed")
        item.setdefault("final_positive_prompt", str(item.get("positive_prompt", "")).strip())
        item.setdefault(
            "workflow_default_positive_prompt",
            str(manifest.get("workflow_default_positive_prompt", "")).strip(),
        )
        item.setdefault("prompt_override_source", "unknown")
        item.setdefault("prompt_override_applied", False)
        item.setdefault("patched_workflow_path", "")
        item.setdefault("patch_report_path", "")
        item.setdefault("patch_status", "pending")
    return items


def _resolve_existing_path(path_text: str, run_dir: Path) -> Path | None:
    value = str(path_text).strip()
    if not value:
        return None
    candidate = Path(value)
    if candidate.exists():
        return candidate
    joined = run_dir / value
    if joined.exists():
        return joined
    return None


def _write_submit_results(
    *,
    run_dir: Path,
    server_url: str,
    results: list[dict[str, Any]],
    used_existing_patched_workflows: bool,
) -> Path:
    submit_log_path = run_dir / "comfyui_submit_results.json"
    _write_json(
        submit_log_path,
        {
            "submit_time": datetime.now().isoformat(),
            "server_url": server_url,
            "run_name": run_dir.name,
            "total_items": len(results),
            "submitted_items": len([row for row in results if bool(row.get("success"))]),
            "failed_items": len([row for row in results if not bool(row.get("success"))]),
            "used_existing_patched_workflows": used_existing_patched_workflows,
            "results": results,
        },
    )
    return submit_log_path


def _load_existing_patched_entries(
    *,
    run_dir: Path,
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    items = _resolve_manifest_items(manifest)
    total_items = len(items)

    patched_dir = run_dir / "patched_workflows"
    batch_files: dict[int, Path] = {}
    if patched_dir.exists():
        for path in sorted(patched_dir.glob("item_*_patched_workflow.json")):
            match = re.match(r"item_(\d+)_patched_workflow\.json$", path.name)
            if match:
                batch_files[int(match.group(1))] = path

    if batch_files:
        entries: list[dict[str, Any]] = []
        missing: list[int] = []
        for index, item in enumerate(items, start=1):
            manifest_path = _resolve_existing_path(str(item.get("patched_workflow_path", "")), run_dir)
            workflow_path = batch_files.get(index) or manifest_path
            if workflow_path is None or not workflow_path.exists():
                missing.append(index)
                continue
            entries.append(
                {
                    "item_index": index,
                    "item_id": str(item.get("item_id", index)),
                    "subject": item.get("subject", ""),
                    "positive_prompt": item.get("positive_prompt", ""),
                    "filename_prefix": item.get("filename_prefix", ""),
                    "workflow_path": workflow_path,
                }
            )
        if missing:
            print(
                "[WARN] Incomplete batch patched workflows detected. "
                f"Missing item indexes: {missing}"
            )
            raise RuntimeError(
                "Manifest contains multiple items, but patched workflows are incomplete."
            )
        return entries

    index_path = run_dir / "patched_workflow_index.json"
    if index_path.exists():
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            index_items = payload.get("items", [])
            entries = []
            for index, item in enumerate(items, start=1):
                if index > len(index_items):
                    break
                row = index_items[index - 1]
                workflow_path = _resolve_existing_path(str(row.get("patched_workflow", "")), run_dir)
                if workflow_path is None:
                    continue
                entries.append(
                    {
                        "item_index": index,
                        "item_id": str(item.get("item_id", index)),
                        "subject": item.get("subject", ""),
                        "positive_prompt": item.get("positive_prompt", ""),
                        "filename_prefix": item.get("filename_prefix", ""),
                        "workflow_path": workflow_path,
                    }
                )
            if entries:
                if total_items > len(entries):
                    print(
                        "[WARN] Incomplete patched_workflow_index.json entries for batch submit. "
                        f"manifest_items={total_items}, indexed={len(entries)}"
                    )
                    raise RuntimeError(
                        "Manifest contains multiple items, but patched workflow index is incomplete."
                    )
                return entries
        except RuntimeError:
            raise
        except Exception:
            pass

    single = run_dir / "patched_workflow.json"
    if single.exists():
        if total_items > 1:
            print(
                "[WARN] Using legacy single patched_workflow.json; batch submit is not available for this run."
            )
            raise RuntimeError(
                "Manifest contains multiple items but only legacy single patched_workflow.json exists."
            )
        item = items[0] if items else {"item_id": "1", "subject": "", "positive_prompt": "", "filename_prefix": ""}
        print(
            "[WARN] Using legacy single patched_workflow.json; batch submit is not available for this run."
        )
        return [
            {
                "item_index": int(item.get("item_index", 1) or 1),
                "item_id": str(item.get("item_id", "1")),
                "subject": item.get("subject", ""),
                "positive_prompt": item.get("positive_prompt", ""),
                "filename_prefix": item.get("filename_prefix", ""),
                "workflow_path": single,
            }
        ]
    return []


def _patch_workflows_common(
    *,
    args: argparse.Namespace,
    config: dict[str, Any],
    manifest: dict[str, Any],
    run_dir: Path,
    submit: bool = False,
    force_auto_mode: bool = False,
    mapping_override: dict[str, Any] | None = None,
    mapping_mode_override: str | None = None,
    workflow_path_override: Path | None = None,
) -> None:
    comfy_settings = resolve_comfyui_settings(config)
    manifest["run_name"] = run_dir.name
    items = _resolve_manifest_items(manifest)
    if not items:
        raise ValueError("Prompt rows are empty; cannot patch or submit.")

    patched_output_dir = run_dir / "patched_workflows"
    patch_report_dir = run_dir / "patch_reports"
    patched_output_dir.mkdir(parents=True, exist_ok=True)
    patch_report_dir.mkdir(parents=True, exist_ok=True)

    index_rows: list[dict[str, Any]] = []
    submit_items: list[dict[str, Any]] = []

    client: ComfyUIClient | None = None
    comfyui_url = ""
    if submit:
        comfyui_url = args.comfyui_url.strip() or str(
            comfy_settings.get("base_url", "http://127.0.0.1:8188")
        )
        client = ComfyUIClient(base_url=comfyui_url)

    if submit and client is not None:
        existing_entries = _load_existing_patched_entries(run_dir=run_dir, manifest=manifest)
        if existing_entries:
            print(
                "[INFO] Submit mode will use existing patched workflow files from current run "
                f"directory: {run_dir}"
            )
            total_existing = len(existing_entries)
            for position, entry in enumerate(existing_entries, start=1):
                workflow_to_submit = load_workflow_json(entry["workflow_path"])
                item_index = int(entry.get("item_index", position) or position)
                item_id = str(entry.get("item_id", item_index))
                subject = str(entry.get("subject", ""))
                try:
                    response = client.submit_prompt(
                        _extract_prompt_graph(workflow_to_submit),
                        client_id=args.client_id.strip() or None,
                    )
                    prompt_id = str(response.get("prompt_id", "")).strip()
                    if prompt_id:
                        print(
                            f"[OK] Submit success for item {position}/{total_existing}, prompt_id={prompt_id}"
                        )
                    else:
                        print(
                            f"[WARN] Submit returned without prompt_id for item {position}/{total_existing}"
                        )
                    submit_items.append(
                        {
                            "item_index": item_index,
                            "item_id": item_id,
                            "patched_workflow_path": str(
                                Path(entry["workflow_path"]).as_posix()
                            ),
                            "positive_prompt": str(entry.get("positive_prompt", "")),
                            "filename_prefix": str(entry.get("filename_prefix", "")),
                            "prompt_id": prompt_id,
                            "success": True,
                            "subject": subject,
                            "response": response,
                        }
                    )
                except Exception as exc:
                    error, node_errors = _extract_submit_error(exc)
                    print(f"[ERROR] Submit failed for item {position}/{total_existing}: {error}")
                    if node_errors:
                        print(f"[ERROR] node_errors: {json.dumps(node_errors, ensure_ascii=False)}")
                    submit_items.append(
                        {
                            "item_index": item_index,
                            "item_id": item_id,
                            "patched_workflow_path": str(
                                Path(entry["workflow_path"]).as_posix()
                            ),
                            "positive_prompt": str(entry.get("positive_prompt", "")),
                            "filename_prefix": str(entry.get("filename_prefix", "")),
                            "prompt_id": "",
                            "success": False,
                            "error": error,
                            "node_errors": node_errors,
                            "subject": subject,
                        }
                    )

            submit_log_path = _write_submit_results(
                run_dir=run_dir,
                server_url=comfyui_url,
                results=submit_items,
                used_existing_patched_workflows=True,
            )
            for entry in existing_entries:
                item_index = int(entry.get("item_index", 0) or 0)
                if item_index <= 0 or item_index > len(items):
                    continue
                manifest_item = items[item_index - 1]
                workflow_path = Path(entry["workflow_path"])
                manifest_item["patched_workflow_path"] = str(workflow_path.as_posix())
                report_path = patch_report_dir / _item_patch_report_filename(item_index)
                manifest_item["patch_report_path"] = (
                    str(report_path.as_posix()) if report_path.exists() else ""
                )
                manifest_item["patch_status"] = "success"
                manifest_item["patch_error"] = ""
            save_manifest_json(manifest, run_dir / "run_manifest.json")
            print(f"[OK] Submit results saved to: {submit_log_path}")
            failed = [item for item in submit_items if not bool(item.get("success"))]
            if failed:
                raise RuntimeError(
                    "One or more submit requests failed. Check `comfyui_submit_results.json`."
                )
            return

    workflow_path = workflow_path_override or _resolve_workflow_path(args, config)
    mapping_mode = (
        str(mapping_mode_override).strip()
        if str(mapping_mode_override or "").strip()
        else _resolve_mapping_mode(args, config, auto=force_auto_mode)
    )
    if mapping_override is not None:
        mapping = mapping_override
    else:
        if mapping_mode == "manual_map":
            mapping_path = _resolve_mapping_path(args, config, required=True)
        else:
            mapping_path = Path(args.node_map.strip()) if args.node_map.strip() else None
        mapping = _load_optional_mapping(mapping_path)

    base_workflow = load_workflow_json(workflow_path)

    for index, item in enumerate(items, start=1):
        item["final_positive_prompt"] = str(
            item.get("final_positive_prompt", item.get("positive_prompt", ""))
        ).strip()
        item["workflow_default_positive_prompt"] = str(
            item.get(
                "workflow_default_positive_prompt",
                manifest.get("workflow_default_positive_prompt", ""),
            )
        ).strip()
        if str(item.get("prompt_override_source", "")).strip() == "":
            item["prompt_override_source"] = "unknown"
        params = _build_patch_params(manifest, item, index, comfy_settings)
        item["filename_prefix"] = params.filename_prefix
        if not str(item.get("filename_prefix_source", "")).strip():
            item["filename_prefix_source"] = "config.generation.filename_prefix+item_index"
        item["seed"] = int(params.seed)
        output_path = patched_output_dir / _item_workflow_filename(index)
        report_json = patch_report_dir / _item_patch_report_filename(index)
        report_md = patch_report_dir / f"{_item_tag(index)}_patch_report.md"
        item_id = str(item.get("item_id", item.get("id", index)))

        try:
            patched_workflow, patch_report = patch_workflow_with_report(
                workflow=base_workflow,
                mapping=mapping,
                params=params,
                mapping_mode=mapping_mode,
            )
            patch_report["item_index"] = index
            patch_report["item_id"] = item_id
            patch_report["value_sources"] = _build_value_sources(manifest, item)
            patch_report["fallback_fields"] = _build_fallback_fields(patch_report["value_sources"])
            patch_report["unsupported_fields"] = _build_unsupported_fields(
                mapping=mapping,
                params=params,
            )
            patch_report["workflow_default_prompt"] = item.get(
                "workflow_default_positive_prompt", ""
            )
            patch_report["final_patched_prompt"] = item.get("final_positive_prompt", "")
            patch_report["prompt_override_source"] = item.get(
                "prompt_override_source", "unknown"
            )
            patch_report["prompt_override_applied"] = bool(
                item.get("prompt_override_applied", False)
            )

            save_workflow_json(patched_workflow, output_path)
            _write_json(report_json, patch_report)
            _render_patch_report_markdown(
                item={"item_id": item_id, "subject": item.get("subject", "")},
                report=patch_report,
                output_path=report_md,
            )

            item["patched_workflow_path"] = str(output_path.as_posix())
            item["patch_report_path"] = str(report_json.as_posix())
            item["patch_status"] = "success"
            item["patch_error"] = ""
        except Exception as exc:
            item["patched_workflow_path"] = ""
            item["patch_report_path"] = ""
            item["patch_status"] = "failed"
            item["patch_error"] = str(exc)
            print(f"[ERROR] Patch failed for item {index}/{len(items)}: {exc}")

        index_rows.append(
            {
                "item_index": index,
                "item_id": item_id,
                "subject": item.get("subject", ""),
                "patched_workflow": str(item.get("patched_workflow_path", "")),
                "patch_report_json": str(item.get("patch_report_path", "")),
                "mapping_mode": mapping_mode,
                "patch_status": item.get("patch_status", "unknown"),
                "patch_error": item.get("patch_error", ""),
                "filename_prefix": item.get("filename_prefix", ""),
                "final_positive_prompt": item.get("final_positive_prompt", ""),
                "workflow_default_positive_prompt": item.get(
                    "workflow_default_positive_prompt", ""
                ),
                "prompt_override_source": item.get("prompt_override_source", "unknown"),
                "prompt_override_applied": bool(item.get("prompt_override_applied", False)),
            }
        )

        if client is not None and str(item.get("patched_workflow_path", "")).strip():
            try:
                response = client.submit_prompt(
                    _extract_prompt_graph(patched_workflow),
                    client_id=args.client_id.strip() or None,
                )
                prompt_id = str(response.get("prompt_id", "")).strip()
                if prompt_id:
                    print(
                        f"[OK] Submit success for item {index}/{len(items)}, prompt_id={prompt_id}"
                    )
                else:
                    print(f"[WARN] Submit returned without prompt_id for item {index}/{len(items)}")
                submit_items.append(
                    {
                        "item_index": index,
                        "item_id": item_id,
                        "patched_workflow_path": str(output_path.as_posix()),
                        "positive_prompt": str(item.get("positive_prompt", "")),
                        "filename_prefix": str(item.get("filename_prefix", "")),
                        "prompt_id": prompt_id,
                        "success": True,
                        "subject": item.get("subject", ""),
                        "response": response,
                    }
                )
            except Exception as exc:
                error, node_errors = _extract_submit_error(exc)
                print(f"[ERROR] Submit failed for item {index}/{len(items)}: {error}")
                if node_errors:
                    print(f"[ERROR] node_errors: {json.dumps(node_errors, ensure_ascii=False)}")
                submit_items.append(
                    {
                        "item_index": index,
                        "item_id": item_id,
                        "patched_workflow_path": str(output_path.as_posix()),
                        "positive_prompt": str(item.get("positive_prompt", "")),
                        "filename_prefix": str(item.get("filename_prefix", "")),
                        "prompt_id": "",
                        "success": False,
                        "error": error,
                        "node_errors": node_errors,
                        "subject": item.get("subject", ""),
                    }
                )
        elif client is not None:
            submit_items.append(
                {
                    "item_index": index,
                    "item_id": item_id,
                    "patched_workflow_path": "",
                    "positive_prompt": str(item.get("positive_prompt", "")),
                    "filename_prefix": str(item.get("filename_prefix", "")),
                    "prompt_id": "",
                    "success": False,
                    "error": str(item.get("patch_error", "patch failed")),
                    "node_errors": {},
                    "subject": item.get("subject", ""),
                }
            )

    index_path = run_dir / "patched_workflow_index.json"
    _write_json(index_path, {"items": index_rows})
    successful_rows = [
        row for row in index_rows if str(row.get("patch_status", "")) == "success"
    ]
    if successful_rows:
        single = successful_rows[0]
        patched_src = Path(single["patched_workflow"])
        report_json_src = Path(single["patch_report_json"])
        save_workflow_json(load_workflow_json(patched_src), run_dir / "patched_workflow.json")
        if report_json_src.exists():
            _write_json(
                run_dir / "patch_report.json",
                json.loads(report_json_src.read_text(encoding="utf-8")),
            )
    _render_batch_patch_report_markdown(
        manifest=manifest,
        output_path=run_dir / "patch_report.md",
    )
    save_manifest_json(manifest, run_dir / "run_manifest.json")

    print(f"[OK] Patched workflow files generated: {len(successful_rows)}/{len(index_rows)}")
    print(f"[OK] Output directory: {patched_output_dir}")
    print(f"[OK] Patched workflow index: {index_path}")

    if submit_items:
        submit_log_path = _write_submit_results(
            run_dir=run_dir,
            server_url=comfyui_url,
            results=submit_items,
            used_existing_patched_workflows=False,
        )
        print(f"[OK] Submit results saved to: {submit_log_path}")
    failed_submit_items = [item for item in submit_items if not bool(item.get("success"))]
    if failed_submit_items:
        raise RuntimeError(
            "One or more submit requests failed. Check console logs and "
            "`comfyui_submit_results.json` in this run directory."
        )
    failed_patch_items = [item for item in items if item.get("patch_status") != "success"]
    if failed_patch_items:
        raise RuntimeError(
            "One or more workflow patch operations failed. Check `patch_report.md` and "
            "`patched_workflow_index.json` for details."
        )


def main() -> None:
    args = parse_args()
    args.mode = _normalize_mode_alias(args.mode)

    try:
        if args.mode == "scaffold_workflow":
            run_scaffold_workflow(args)
            return

        if _mode_requires_config(args.mode):
            config_path = _require_config_path_for_mode(args)
            config = load_yaml_config(config_path)
        else:
            config = {}

        if args.mode == "inspect_workflow":
            run_inspect_workflow(args, config)
            return

        if args.mode == "resolve_models":
            run_resolve_models(args, config)
            return

        if args.mode == "suggest_mapping":
            run_suggest_mapping(args, config)
            return
        if args.mode == "export_default_prompt_pack":
            run_export_default_prompt_pack(args, config)
            return
        if args.mode == "workflow_import_pipeline":
            run_workflow_import_pipeline(args, config)
            return

        workflow_path: Path | None = None
        if args.mode in {"manifest", "patch_workflow", "auto_patch_workflow", "submit"}:
            try:
                workflow_path = _resolve_workflow_path(args, config)
            except Exception:
                workflow_path = None
        run_dir = _resolve_run_dir(args=args, config=config, workflow_path=workflow_path)

        manifest = _build_manifest_if_needed(args, config, run_dir=run_dir)
        if manifest is None:
            raise RuntimeError("Manifest was not generated for selected mode.")

        workflow_for_compat = None
        try:
            workflow_for_compat = inspect_workflow_from_config(
                config, workflow_path=args.workflow_json or None
            )
        except Exception:
            workflow_for_compat = None
        model_report = build_comfyui_model_compatibility_report(
            config=config, inspection_result=workflow_for_compat
        )
        _print_model_compatibility_report(model_report)

        if args.mode == "manifest":
            print("[INFO] Manifest mode completed.")
            return
        if args.mode == "patch_workflow":
            _patch_workflows_common(
                args=args,
                config=config,
                manifest=manifest,
                run_dir=run_dir,
                submit=False,
                force_auto_mode=False,
            )
            return
        if args.mode == "auto_patch_workflow":
            _patch_workflows_common(
                args=args,
                config=config,
                manifest=manifest,
                run_dir=run_dir,
                submit=False,
                force_auto_mode=True,
            )
            return
        if args.mode == "submit":
            _patch_workflows_common(
                args=args,
                config=config,
                manifest=manifest,
                run_dir=run_dir,
                submit=True,
                force_auto_mode=False,
            )
            return
    except ComfyUIAdapterError as exc:
        if str(exc) == PLACEHOLDER_WORKFLOW_ERROR:
            raise SystemExit(str(exc)) from exc
        raise SystemExit(f"ComfyUI compatibility error: {exc}") from exc
    except Exception as exc:
        raise SystemExit(f"Batch run failed in mode `{args.mode}`: {exc}") from exc


if __name__ == "__main__":
    main()
