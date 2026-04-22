from __future__ import annotations

import argparse
from datetime import datetime
import json
import sys
from pathlib import Path
from typing import Any

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
    resolve_report_output_dirs,
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
        help="prompt_pack.csv path (required for manifest/patch/submit/auto_patch modes).",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="results/run_manifest.json",
        help="Manifest output JSON path.",
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
            "prepare_workflow_import",
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
        "--patched-output-dir",
        type=str,
        default="",
        help="Override patched workflow output directory.",
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
        help="统一 run 目录名（用于 workflow_import_pipeline）。",
    )
    return parser.parse_args()


def _resolve_required_path(cli_value: str, config_value: str, label: str) -> Path:
    value = cli_value.strip() or str(config_value).strip()
    if not value:
        raise ValueError(f"{label} is required for this mode.")
    return Path(value)


def _build_item_prefix(item: dict[str, Any], index: int) -> str:
    item_id = str(item.get("id", "")).strip()
    subject = str(item.get("subject", f"item_{index:03d}")).strip()
    safe_subject = sanitize_filename(subject) or f"item_{index:03d}"
    if item_id.isdigit():
        return f"{int(item_id):03d}_{safe_subject}"
    return f"item_{index:03d}_{safe_subject}"


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

    return WorkflowPatchParams(
        positive_prompt=str(item.get("positive_prompt", "")),
        negative_prompt=str(item.get("negative_prompt", "")),
        seed=int(manifest.get("seed", 42)),
        width=int(manifest.get("width", 1024)),
        height=int(manifest.get("height", 1024)),
        steps=int(manifest.get("num_inference_steps", 30)),
        cfg=float(manifest.get("guidance_scale", 7.0)),
        sampler=str(manifest.get("sampler", "euler")),
        scheduler=str(manifest.get("scheduler", "normal")),
        filename_prefix=_build_item_prefix(item, index),
        output_dir=output_dir,
        use_lora=bool(comfy_settings.get("use_lora", False)),
        lora_path=str(comfy_settings.get("lora_path", "")),
        lora_strength=float(comfy_settings.get("lora_strength", 1.0)),
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
    if args.run_name.strip():
        run_name = sanitize_filename(args.run_name.strip())
    else:
        stem = workflow_path.stem if workflow_path is not None else "workflow"
        comfy_settings = resolve_comfyui_settings(config)
        fallback = str(comfy_settings.get("mode", "pipeline")).strip() or "pipeline"
        run_name = sanitize_filename(
            f"{stem}_{fallback}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
    run_name = run_name or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = base_root / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


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


def _require_prompt_pack(args: argparse.Namespace) -> Path:
    value = args.prompt_pack.strip()
    if not value:
        raise ValueError(
            "--prompt-pack is required for manifest/patch_workflow/submit/auto_patch_workflow/workflow_import_pipeline."
        )
    return Path(value)


def _build_manifest_if_needed(
    args: argparse.Namespace,
    config: dict[str, Any],
    force: bool = False,
) -> dict[str, Any] | None:
    if args.mode not in {
        "manifest",
        "patch_workflow",
        "submit",
        "auto_patch_workflow",
        "workflow_import_pipeline",
        "prepare_workflow_import",
    } and not force:
        return None
    prompt_pack_path = _require_prompt_pack(args)
    prompt_rows = load_prompt_pack_csv(prompt_pack_path)
    manifest = build_run_manifest(config, prompt_rows)
    save_manifest_json(manifest, Path(args.output_json))
    print(f"[OK] Run manifest created: {args.output_json}")
    print(f"[OK] Number of generation items: {len(manifest['items'])}")
    return manifest


def run_inspect_workflow(args: argparse.Namespace, config: dict[str, Any]) -> None:
    workflow_path = _resolve_workflow_path(args, config)
    report_dirs = resolve_report_output_dirs(config)
    output_dir = Path(report_dirs["workflow_inspection"])
    inspection = inspect_workflow_path(workflow_path)
    stem = workflow_path.stem
    json_path = output_dir / f"{stem}_inspection.json"
    md_path = output_dir / f"{stem}_inspection.md"
    save_inspection_report_json(inspection, json_path)
    save_inspection_report_markdown(inspection, md_path)
    print(f"[OK] Workflow inspected: {workflow_path}")
    print(f"[OK] Inspection JSON: {json_path}")
    print(f"[OK] Inspection Markdown: {md_path}")


def run_resolve_models(args: argparse.Namespace, config: dict[str, Any]) -> None:
    workflow_path = _resolve_workflow_path(args, config)
    inspection = inspect_workflow_path(workflow_path)
    root_override = args.comfyui_root.strip() or None
    report = resolve_models_from_config(config, inspection, comfyui_root=root_override)
    report_dirs = resolve_report_output_dirs(config)
    output_dir = Path(report_dirs["model_resolution"])
    output_path = output_dir / f"{workflow_path.stem}_model_resolution.json"
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
    inspection = inspect_workflow_path(workflow_path)
    mapping_path = _resolve_mapping_path(args, config, required=False)
    existing_mapping = _load_optional_mapping(mapping_path)
    suggestion = suggest_mapping_from_config(
        config=config, inspection_result=inspection, existing_mapping=existing_mapping
    )
    report_dirs = resolve_report_output_dirs(config)
    output_dir = Path(report_dirs["mapping_suggestions"])
    output_yaml = output_dir / f"{workflow_path.stem}_suggested_node_map.yaml"
    output_json = output_dir / f"{workflow_path.stem}_mapping_suggestion_report.json"
    output_diff_md = output_dir / f"{workflow_path.stem}_mapping_diff.md"
    output_manual_review = output_dir / f"{workflow_path.stem}_mapping_manual_review.yaml"
    save_mapping_yaml(suggestion["mapping"], output_yaml)
    save_mapping_diff_markdown(suggestion.get("diff_vs_existing", {}), output_diff_md)
    save_mapping_manual_review_yaml(suggestion, output_manual_review)
    _write_json(output_json, suggestion)
    print(f"[OK] Mapping suggestion generated for: {workflow_path}")
    print(f"[OK] Suggested node map YAML: {output_yaml}")
    print(f"[OK] Suggestion report JSON: {output_json}")
    print(f"[OK] Mapping diff Markdown: {output_diff_md}")
    print(f"[OK] Manual review YAML: {output_manual_review}")


def run_workflow_import_pipeline(args: argparse.Namespace, config: dict[str, Any]) -> None:
    workflow_path = _resolve_workflow_path(args, config)
    run_dir = _resolve_run_dir(args=args, config=config, workflow_path=workflow_path)

    inspection = inspect_workflow_path(workflow_path)
    _write_json(run_dir / "workflow_inspection.json", inspection)

    root_override = args.comfyui_root.strip() or None
    model_report = resolve_models_from_config(
        config=config, inspection_result=inspection, comfyui_root=root_override
    )
    _write_json(run_dir / "model_resolution.json", model_report)

    # Pipeline mode defaults to pure auto-detect; only apply manual override
    # when user explicitly passes --node-map.
    mapping_path = Path(args.node_map.strip()) if args.node_map.strip() else None
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

    prompt_pack_path = _require_prompt_pack(args)
    prompt_rows = load_prompt_pack_csv(prompt_pack_path)
    manifest = build_run_manifest(config, prompt_rows)
    save_manifest_json(manifest, run_dir / "run_manifest.json")

    items = manifest.get("items", [])
    if not items:
        raise ValueError("prompt_pack 为空，无法执行 auto patch。")

    comfy_settings = resolve_comfyui_settings(config)
    params = _build_patch_params(
        manifest=manifest,
        item=items[0],
        index=1,
        comfy_settings=comfy_settings,
    )
    base_workflow = load_workflow_json(workflow_path)
    patched_workflow, patch_report = patch_workflow_with_report(
        workflow=base_workflow,
        mapping=suggestion["mapping"],
        params=params,
        mapping_mode="auto_detect",
    )
    save_workflow_json(patched_workflow, run_dir / "patched_workflow.json")
    _write_json(run_dir / "patch_report.json", patch_report)
    _render_patch_report_markdown(
        item={"item_id": items[0].get("id", 1), "subject": items[0].get("subject", "")},
        report=patch_report,
        output_path=run_dir / "patch_report.md",
    )

    print(f"[OK] workflow-first pipeline 已完成，输出目录: {run_dir}")


def _resolve_mapping_mode(args: argparse.Namespace, config: dict[str, Any], auto: bool = False) -> str:
    if auto:
        return "auto_detect"
    comfy_settings = resolve_comfyui_settings(config)
    value = args.mapping_mode.strip() or str(comfy_settings.get("mapping_mode", "manual_map"))
    value = value.strip().lower() or "manual_map"
    if value not in {"manual_map", "auto_detect"}:
        raise ValueError("mapping_mode must be `manual_map` or `auto_detect`.")
    return value


def _patch_workflows_common(
    *,
    args: argparse.Namespace,
    config: dict[str, Any],
    manifest: dict[str, Any],
    submit: bool = False,
    force_auto_mode: bool = False,
) -> None:
    comfy_settings = resolve_comfyui_settings(config)
    workflow_path = _resolve_workflow_path(args, config)
    mapping_mode = _resolve_mapping_mode(args, config, auto=force_auto_mode)
    if mapping_mode == "manual_map":
        mapping_path = _resolve_mapping_path(args, config, required=True)
    else:
        # auto_detect mode only applies manual mapping as explicit override from CLI.
        mapping_path = Path(args.node_map.strip()) if args.node_map.strip() else None
    mapping = _load_optional_mapping(mapping_path)

    patched_output_dir = Path(
        args.patched_output_dir.strip()
        or str(comfy_settings.get("save_patched_workflows_dir", "results/patched_workflows"))
    )
    report_dirs = resolve_report_output_dirs(config)
    patch_report_dir = Path(report_dirs["patch_reports"])

    base_workflow = load_workflow_json(workflow_path)
    index_rows: list[dict[str, Any]] = []
    submit_results: list[dict[str, Any]] = []

    client: ComfyUIClient | None = None
    if submit:
        print("[INFO] Submit mode is experimental and best suited for smoke tests.")
        comfyui_url = args.comfyui_url.strip() or str(
            comfy_settings.get("base_url", "http://127.0.0.1:8188")
        )
        client = ComfyUIClient(base_url=comfyui_url)

    for index, item in enumerate(manifest.get("items", []), start=1):
        params = _build_patch_params(manifest, item, index, comfy_settings)
        patched_workflow, patch_report = patch_workflow_with_report(
            workflow=base_workflow,
            mapping=mapping,
            params=params,
            mapping_mode=mapping_mode,
        )

        filename = f"{params.filename_prefix}.json"
        output_path = patched_output_dir / filename
        save_workflow_json(patched_workflow, output_path)

        item_id = item.get("id", index)
        report_json = patch_report_dir / f"{params.filename_prefix}_patch_report.json"
        report_md = patch_report_dir / f"{params.filename_prefix}_patch_report.md"
        _write_json(report_json, patch_report)
        _render_patch_report_markdown(
            item={"item_id": item_id, "subject": item.get("subject", "")},
            report=patch_report,
            output_path=report_md,
        )

        index_rows.append(
            {
                "item_id": item_id,
                "subject": item.get("subject", ""),
                "patched_workflow": str(output_path.as_posix()),
                "patch_report_json": str(report_json.as_posix()),
                "patch_report_md": str(report_md.as_posix()),
                "mapping_mode": mapping_mode,
            }
        )

        if client is not None:
            response = client.submit_prompt(
                _extract_prompt_graph(patched_workflow),
                client_id=args.client_id.strip() or None,
            )
            submit_results.append(
                {
                    "item_id": item_id,
                    "subject": item.get("subject", ""),
                    "response": response,
                }
            )

    patched_output_dir.mkdir(parents=True, exist_ok=True)
    patch_report_dir.mkdir(parents=True, exist_ok=True)

    index_path = patched_output_dir / "patched_workflow_index.json"
    _write_json(index_path, {"items": index_rows})
    print(f"[OK] Patched workflow files generated: {len(index_rows)}")
    print(f"[OK] Output directory: {patched_output_dir}")
    print(f"[OK] Patched workflow index: {index_path}")

    if submit_results:
        submit_log_path = Path("results/comfyui_submit_results.json")
        _write_json(submit_log_path, {"items": submit_results})
        print(f"[OK] Submitted {len(submit_results)} workflows to ComfyUI.")
        print(f"[OK] Submission results saved to: {submit_log_path}")


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
        if args.mode in {"workflow_import_pipeline", "prepare_workflow_import"}:
            run_workflow_import_pipeline(args, config)
            return

        manifest = _build_manifest_if_needed(args, config)
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
                submit=False,
                force_auto_mode=False,
            )
            return
        if args.mode == "auto_patch_workflow":
            _patch_workflows_common(
                args=args,
                config=config,
                manifest=manifest,
                submit=False,
                force_auto_mode=True,
            )
            return
        if args.mode == "submit":
            _patch_workflows_common(
                args=args,
                config=config,
                manifest=manifest,
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


