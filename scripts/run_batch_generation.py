from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any

import requests

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
    save_mapping_diff_markdown,
    save_mapping_manual_review_yaml,
    save_mapping_yaml,
)
from src.generation.prompt_builder import sanitize_filename  # noqa: E402
from src.generation.workflow_inspector import (  # noqa: E402
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
    parser.add_argument("--config", type=str, required=True, help="YAML config path.")
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
    return parser.parse_args()


def _resolve_required_path(cli_value: str, config_value: str, label: str) -> Path:
    value = cli_value.strip() or str(config_value).strip()
    if not value:
        raise ValueError(f"{label} is required for this mode.")
    return Path(value)


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
    config = load_yaml_config(Path(args.config))

    try:
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
