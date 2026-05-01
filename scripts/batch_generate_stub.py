from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aigc2d.comfy_client import ComfyClient
from aigc2d.comfy_preflight import (
    preflight_workflow_against_comfy,
    resync_load_images_from_patched_fields,
)
from aigc2d.config import load_json, write_json
from aigc2d.generation_config import load_generation_config
from aigc2d.prompting import load_prompt_sheet
from aigc2d.run_manager import RunManager, make_run_id
from aigc2d.scoring import aggregate_score_records
from aigc2d.workflow_runtime import WorkflowRuntime, runtime_snapshot, write_workflow


def read_manifest_rows(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return [{}]
    if not Path(path).exists():
        return [{}]
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f)) or [{}]


def pair_rows(manifest_rows: list[dict[str, Any]], prompt_rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if not prompt_rows:
        prompt_rows = [{"positive_prompt": "", "negative_prompt": ""}]
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for idx, prompt_row in enumerate(prompt_rows):
        manifest_row = manifest_rows[idx] if idx < len(manifest_rows) else manifest_rows[0]
        pairs.append((manifest_row, prompt_row))
    return pairs


def collect_explicit_model_patch_fields(args: Any, manifest_row: dict[str, Any]) -> frozenset[str]:
    """Overrides that unblock patching keys listed in preserve_template_models."""
    s: set[str] = set()
    mr = manifest_row or {}

    def nz(key: str) -> str:
        return str(mr.get(key) or "").strip()

    if args.model_profile or args.checkpoint_profile:
        s.update({"checkpoint", "ckpt_name", "model_name"})
    if args.vae_profile:
        s.update({"vae", "vae_name"})
    if args.segmentation_profile:
        s.add("segmentation_model")
    if args.vlm_profile:
        s.add("vlm_model")
    if args.tagger_profile:
        s.add("tagger_model")

    if nz("ckpt_name") or nz("checkpoint") or nz("model_name"):
        s.update({"checkpoint", "ckpt_name", "model_name"})
    if nz("vae_name"):
        s.update({"vae", "vae_name"})
    if nz("control_net_name"):
        s.update({"control_net_name", "controlnet_name", "controlnet_model"})
    if nz("clip_name"):
        s.update({"clip_name", "clip_vision_name", "clip_vision_model"})
    if nz("ipadapter_file"):
        s.update({"ipadapter_file", "ipadapter_model", "ipadapter_name"})
    if nz("upscale_model_name") or nz("upscale_model"):
        s.update({"upscale_model_name", "upscale_model"})
    if nz("lora_name"):
        s.update({"lora_name", "lora_1_name", "lora_strength_model", "lora_strength_clip"})
    if nz("model_profile"):
        s.update({"checkpoint", "ckpt_name", "model_name"})

    return frozenset(s)


def _invalid_enum_hits_explicit(explicit: frozenset[str], preflight: dict[str, Any]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for e in preflight.get("errors", []):
        if e.get("code") != "invalid_enum_value":
            continue
        inm = str(e.get("input_name") or "")
        if inm in explicit:
            hits.append(e)
            continue
        for ex in explicit:
            if ex.replace("_", "") == inm.replace("_", ""):
                hits.append(e)
                break
    return hits


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or execute ComfyUI batch generation tasks.")
    parser.add_argument("--task-config", default="configs/generation/firefly_wallpaper.yaml")
    parser.add_argument("--tasks", default="", help="generation_tasks.csv from scripts/build_tasks.py")
    parser.add_argument("--prompt-sheet", default="")
    parser.add_argument("--manifest", default="")
    parser.add_argument("--max-items", type=int, default=0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--comfy-url", default="")
    parser.add_argument("--model-profile", default="")
    parser.add_argument("--checkpoint-profile", default="")
    parser.add_argument("--vae-profile", default="")
    parser.add_argument("--segmentation-profile", default="")
    parser.add_argument("--vlm-profile", default="")
    parser.add_argument("--tagger-profile", default="")
    parser.add_argument("--download-outputs", action="store_true")
    parser.add_argument("--timeout-sec", type=int, default=600)
    parser.add_argument("--comfy-input-dir", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--debug-comfy", action="store_true", help="Always write per-task preflight reports; keep verbose submit artifacts.")
    parser.add_argument("--preflight-comfy", action="store_true", help="Abort before /prompt when preflight reports errors.")
    parser.add_argument("--preserve-template-models", action="store_true", default=True)
    parser.add_argument("--no-preserve-template-models", dest="preserve_template_models", action="store_false")
    args = parser.parse_args()

    config = load_generation_config(args.task_config)
    comfy_url = args.comfy_url or config.comfy_url
    runtime = WorkflowRuntime()
    run_id = make_run_id(config.name)
    run_manager = RunManager()
    run_dir = run_manager.run_dir(run_id)

    if args.tasks:
        task_rows = read_manifest_rows(args.tasks)
        manifest_rows = task_rows
        prompt_rows = task_rows
    else:
        manifest_rows = read_manifest_rows(args.manifest)
        prompt_rows = load_prompt_sheet(args.prompt_sheet) if args.prompt_sheet and Path(args.prompt_sheet).exists() else []
    pairs = pair_rows(manifest_rows, prompt_rows)
    if args.max_items:
        pairs = pairs[: args.max_items]

    comfy_req_timeout = min(240, max(60, args.timeout_sec // 3))
    client = ComfyClient(comfy_url, timeout=comfy_req_timeout)

    tasks: list[dict[str, Any]] = []
    batch_failed_nodes: list[str] = []
    batch_failed_reasons: list[str] = []
    last_preflight_path = ""
    last_payload_path = ""
    last_error_path = ""

    for index, (manifest_row, prompt_row) in enumerate(pairs):
        cli_overrides = {
            "model_profile": args.model_profile or args.checkpoint_profile,
            "vae_profile": args.vae_profile,
            "segmentation_profile": args.segmentation_profile,
            "vlm_profile": args.vlm_profile,
            "tagger_profile": args.tagger_profile,
        }
        executing = args.execute and not args.dry_run
        explicit_model = collect_explicit_model_patch_fields(args, manifest_row)
        built = runtime.build_from_config(
            args.task_config,
            prompt_row,
            manifest_row,
            cli_overrides=cli_overrides,
            run_id=run_id,
            comfy_input_dir=args.comfy_input_dir or None,
            comfy_url=comfy_url,
            dry_run=(args.dry_run or not args.execute),
            preserve_template_models=bool(args.preserve_template_models),
            explicit_model_patch_fields=explicit_model,
            comfy_client=client if executing else None,
        )
        workflow = built["workflow"]
        workflow_path = write_workflow(run_dir / f"task_{index:03d}.workflow.json", workflow)
        prompt_id = ""
        output_images: list[dict[str, Any]] = []
        preflight_report: dict[str, Any] | None = None
        preflight_path_str = ""
        comfy_payload_rel = ""
        comfy_error_rel = ""

        wf_prefix = f"task_{index:03d}"

        if executing:
            resync = resync_load_images_from_patched_fields(
                workflow,
                client,
                built.get("patched_fields") or {},
                preferred_subfolder_prefix=f"aigc2d/{run_id}",
            )
            if resync.get("warnings"):
                built.setdefault("patch_warnings", []).extend([f"load_image_resync:{w}" for w in resync["warnings"]])

            preflight_report = preflight_workflow_against_comfy(workflow, client)
            write_report = bool(args.debug_comfy or args.preflight_comfy or not preflight_report.get("ok", True))
            if write_report:
                pf_name = f"{wf_prefix}_comfy_preflight_report.json"
                write_json(run_dir / pf_name, preflight_report)
                preflight_path_str = str((run_dir / pf_name).resolve())
                last_preflight_path = preflight_path_str

            if explicit_model:
                bad_enum = _invalid_enum_hits_explicit(explicit_model, preflight_report)
                if bad_enum:
                    for e in bad_enum:
                        print("Explicit model patch failed object_info:", e)
                    raise RuntimeError(
                        "Model override rejected by ComfyUI object_info. "
                        f"Inspect {preflight_path_str}"
                    )

            if args.preflight_comfy and not preflight_report.get("ok", True):
                print("\n=== ComfyUI preflight failed ===")
                print(preflight_report.get("summary"))
                for err in preflight_report.get("errors", [])[:60]:
                    print(err)
                raise RuntimeError(f"ComfyUI preflight failed, see {preflight_path_str}")

        if executing:
            try:
                prompt_id = client.submit_prompt(workflow, debug_dir=run_dir, file_prefix=wf_prefix)
                comfy_payload_rel = f"{wf_prefix}_comfy_submit_payload.json"
                last_payload_path = str((run_dir / comfy_payload_rel).resolve())
            except RuntimeError:
                comfy_payload_rel = f"{wf_prefix}_comfy_submit_payload.json"
                comfy_error_rel = f"{wf_prefix}_comfy_submit_error.json"
                last_payload_path = str((run_dir / comfy_payload_rel).resolve())
                last_error_path = str((run_dir / comfy_error_rel).resolve())
                print("\nComfyUI /prompt submit failed.")
                print(f"Status / details printed above.")
                print(f"Payload saved to:\n{(run_dir / comfy_payload_rel).resolve()}")
                print(f"Error saved to:\n{(run_dir / comfy_error_rel).resolve()}")
                if preflight_path_str:
                    print(f"Preflight report:\n{preflight_path_str}")
                raise

            history = client.poll_history(prompt_id, timeout_sec=args.timeout_sec)
            output_images = client.fetch_output_images(history)

            if args.download_outputs:
                downloaded = []
                for image in output_images:
                    filename = image.get("filename", "")
                    saved = client.download_image(
                        filename=filename,
                        subfolder=image.get("subfolder", ""),
                        type_=image.get("type", "output"),
                        save_path=run_dir / "outputs" / filename,
                    )
                    item = dict(image)
                    item["path"] = str(saved)
                    downloaded.append(item)
                output_images = downloaded

        if preflight_report and not preflight_report.get("ok", True):
            for e in preflight_report.get("errors", []):
                nid = str(e.get("node_id") or "")
                if nid:
                    batch_failed_nodes.append(nid)
                batch_failed_reasons.append(f'{e.get("code")}:{e}')

        snapshot = runtime_snapshot(built["generation_config"], built["resolved_models"], built["values"])
        task_payload = {
            "index": index,
            "workflow_path": str(workflow_path),
            "workflow_id": (built.get("active_workflow") or {}).get("workflow_id", config.workflow),
            "active_workflow": built.get("active_workflow", {}),
            "workflow_template_path": str(built.get("workflow_template_path", "")),
            "patch_warnings": built.get("patch_warnings", []),
            "patched_fields": built.get("patched_fields", {}),
            "skipped_fields": built.get("skipped_fields", {}),
            "skipped_model_patch_fields": built.get("skipped_model_patch_fields", []),
            "preserved_template_model_fields": built.get("preserved_template_model_fields", []),
            "explicit_model_patch_fields_used": built.get("explicit_model_patch_fields_used", []),
            "explicit_model_overrides_requested": sorted(explicit_model),
            "preserve_template_models": built.get("preserve_template_models"),
            "copied_uploaded_image_names": built.get("copied_uploaded_image_names", {}),
            "raw_asset": manifest_row.get("raw_asset") or manifest_row.get("init_image") or "",
            "style_asset": manifest_row.get("style_asset") or "",
            "prompt_row": prompt_row,
            "manifest_row": manifest_row,
            "comfy_prompt_id": prompt_id,
            "output_images": output_images,
            "comfy_preflight_report_path": preflight_path_str,
            "comfy_submit_payload_path": str((run_dir / comfy_payload_rel).resolve()) if comfy_payload_rel else "",
            "comfy_submit_error_path": str((run_dir / comfy_error_rel).resolve()) if comfy_error_rel else "",
            "preflight_summary": preflight_report.get("summary") if isinstance(preflight_report, dict) else None,
            **snapshot,
        }
        tasks.append(task_payload)

    failed_node_ids = sorted({nid for nid in batch_failed_nodes if nid})
    batch_summary_aggregate = {
        "comfy_submit_payload_paths": [t.get("comfy_submit_payload_path", "") for t in tasks],
        "comfy_submit_error_paths": [t.get("comfy_submit_error_path", "") for t in tasks if t.get("comfy_submit_error_path")],
        "preflight_report_paths": [t.get("comfy_preflight_report_path", "") for t in tasks if t.get("comfy_preflight_report_path")],
        "failed_node_ids": failed_node_ids,
        "failed_reasons": batch_failed_reasons[:200],
    }
    write_json(run_dir / "batch_comfy_audit.json", batch_summary_aggregate)

    summary_path = run_manager.write_batch_summary(run_id, tasks)
    sum_data = load_json(summary_path)
    sum_data["comfy_audit"] = batch_summary_aggregate
    write_json(summary_path, sum_data)
    first = tasks[0] if tasks else {}
    workflow_template_path = first.get("workflow_template_path", "")
    if not workflow_template_path and config.workflow not in {"active", "active_workflow", ""}:
        workflow_template_path = str(runtime.workflow_template_path(config.workflow))
    run_manager.write_run_manifest(
        run_id,
        {
            "task_type": config.task_type,
            "workflow_name": config.workflow,
            "active_workflow": first.get("active_workflow", {}),
            "workflow_id": (first.get("active_workflow") or {}).get("workflow_id", config.workflow),
            "workflow_type": (first.get("active_workflow") or {}).get("workflow_type", ""),
            "registry_path": (first.get("active_workflow") or {}).get("metadata_path", ""),
            "source_registered_workflow_path": (first.get("active_workflow") or {}).get("workflow_json_path", ""),
            "generation_config_path": args.task_config,
            "workflow_template_path": str(workflow_template_path),
            "prompt_row": first.get("prompt_row", {}),
            "original_task_row": first.get("manifest_row", {}),
            "resolved_positive_prompt": (first.get("resolved_params") or {}).get("positive_prompt", ""),
            "resolved_negative_prompt": (first.get("resolved_params") or {}).get("negative_prompt", ""),
            "final_positive_prompt": (first.get("resolved_params") or {}).get("final_positive_prompt", ""),
            "final_negative_prompt": (first.get("resolved_params") or {}).get("final_negative_prompt", ""),
            "resolved_models": first.get("resolved_models", {}),
            "resolved_params": first.get("resolved_params", {}),
            "patched_fields": first.get("patched_fields", {}),
            "skipped_fields": first.get("skipped_fields", {}),
            "skipped_model_patch_fields": first.get("skipped_model_patch_fields", []),
            "preserved_template_model_fields": first.get("preserved_template_model_fields", []),
            "explicit_model_patch_fields_used": first.get("explicit_model_patch_fields_used", []),
            "explicit_model_overrides_requested": first.get("explicit_model_overrides_requested", []),
            "preserve_template_models": getattr(args, "preserve_template_models", True),
            "warnings": [warning for item in tasks for warning in item.get("patch_warnings", [])],
            "copied_uploaded_image_names": first.get("copied_uploaded_image_names", {}),
            "dry_run_image_upload": bool(args.dry_run or not args.execute),
            "comfy_url": comfy_url,
            "comfy_prompt_id": first.get("comfy_prompt_id", ""),
            "comfy_submit_payload_path": last_payload_path or first.get("comfy_submit_payload_path", ""),
            "comfy_submit_error_path": last_error_path,
            "preflight_report_path": last_preflight_path or first.get("comfy_preflight_report_path", ""),
            "preflight_report_paths": batch_summary_aggregate["preflight_report_paths"],
            "comfy_audit_path": str((run_dir / "batch_comfy_audit.json").resolve()),
            "failed_node_ids": failed_node_ids,
            "failed_reasons": batch_summary_aggregate["failed_reasons"],
            "debug_comfy": bool(args.debug_comfy),
            "preflight_comfy": bool(args.preflight_comfy),
            "source_manifest_path": args.manifest,
            "source_prompt_sheet_path": args.prompt_sheet,
            "source_tasks_path": args.tasks,
            "input_reference_images": [
                (item.get("resolved_params") or {}).get("reference_image", "")
                for item in tasks
                if (item.get("resolved_params") or {}).get("reference_image")
            ],
            "output_images": [image for item in tasks for image in item.get("output_images", [])],
            "scoring_summary": aggregate_score_records([]),
            "notes": "dry-run" if not args.execute or args.dry_run else "executed via ComfyUI API",
        },
    )
    output_path = args.output or str(run_dir / "tasks.json")
    write_json(output_path, {"run_id": run_id, "tasks": tasks, "summary_path": str(summary_path)})
    print(f"run_id: {run_id}")
    print(f"patched tasks json: {Path(output_path).resolve()}")
    print(f"batch summary: {Path(summary_path).resolve()}")
    print(f"run manifest: {(run_dir / 'run_manifest.json').resolve()}")
    print(f"patched workflows dir: {run_dir.resolve()}")
    if args.download_outputs:
        print(f"download outputs dir: {(run_dir / 'outputs').resolve()}")
    print(f"execute: {bool(args.execute and not args.dry_run)}")
    if not args.execute or args.dry_run:
        print("next execute:")
        suffix = f"--tasks {args.tasks}" if args.tasks else f"--prompt-sheet {args.prompt_sheet} --manifest {args.manifest}"
        print(f"python scripts/batch_generate_stub.py {suffix} --execute --download-outputs")


if __name__ == "__main__":
    main()
