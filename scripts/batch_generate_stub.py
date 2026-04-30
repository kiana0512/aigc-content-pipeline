from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aigc2d.comfy_client import ComfyClient
from aigc2d.config import write_json
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
    parser.add_argument("--output", default="")
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

    tasks: list[dict[str, Any]] = []
    client = ComfyClient(comfy_url)
    for index, (manifest_row, prompt_row) in enumerate(pairs):
        cli_overrides = {
            "model_profile": args.model_profile or args.checkpoint_profile,
            "vae_profile": args.vae_profile,
            "segmentation_profile": args.segmentation_profile,
            "vlm_profile": args.vlm_profile,
            "tagger_profile": args.tagger_profile,
        }
        built = runtime.build_from_config(args.task_config, prompt_row, manifest_row, cli_overrides=cli_overrides)
        workflow = built["workflow"]
        workflow_path = write_workflow(run_dir / f"task_{index:03d}.workflow.json", workflow)
        prompt_id = ""
        output_images: list[dict[str, Any]] = []
        if args.execute and not args.dry_run:
            prompt_id = client.submit_prompt(workflow)
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
        snapshot = runtime_snapshot(built["generation_config"], built["resolved_models"], built["values"])
        task_payload = {
            "index": index,
            "workflow_path": str(workflow_path),
            "workflow_id": (built.get("active_workflow") or {}).get("workflow_id", config.workflow),
            "active_workflow": built.get("active_workflow", {}),
            "workflow_template_path": str(built.get("workflow_template_path", "")),
            "patch_warnings": built.get("patch_warnings", []),
            "raw_asset": manifest_row.get("raw_asset") or manifest_row.get("init_image") or "",
            "style_asset": manifest_row.get("style_asset") or "",
            "prompt_row": prompt_row,
            "manifest_row": manifest_row,
            "comfy_prompt_id": prompt_id,
            "output_images": output_images,
            **snapshot,
        }
        tasks.append(task_payload)

    summary_path = run_manager.write_batch_summary(run_id, tasks)
    first = tasks[0] if tasks else {}
    run_manager.write_run_manifest(
        run_id,
        {
            "task_type": config.task_type,
            "workflow_name": config.workflow,
            "active_workflow": first.get("active_workflow", {}),
            "generation_config_path": args.task_config,
            "workflow_template_path": str(first.get("workflow_template_path", runtime.workflow_template_path(config.workflow))),
            "prompt_row": first.get("prompt_row", {}),
            "resolved_positive_prompt": (first.get("resolved_params") or {}).get("positive_prompt", ""),
            "resolved_negative_prompt": (first.get("resolved_params") or {}).get("negative_prompt", ""),
            "resolved_models": first.get("resolved_models", {}),
            "resolved_params": first.get("resolved_params", {}),
            "comfy_url": comfy_url,
            "comfy_prompt_id": first.get("comfy_prompt_id", ""),
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
