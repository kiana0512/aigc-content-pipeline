#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aigc2d.comfy_client import ComfyClient
from aigc2d.comfy_preflight import (
    preflight_workflow_against_comfy,
    resync_load_images_from_patched_fields,
)
from aigc2d.config import write_json


def load_workflow_dict(path: str | Path):
    workflow_path = Path(path)
    txt = workflow_path.read_text(encoding="utf-8")
    blob = json.loads(txt)
    if isinstance(blob, dict) and isinstance(blob.get("prompt"), dict):
        return blob["prompt"], blob
    if isinstance(blob, dict):
        sample = next((v for v in blob.values() if isinstance(v, dict) and "class_type" in v), None)
        if sample is not None:
            return blob, blob
    raise ValueError("Unrecognized workflow JSON (need API graph dict or {\"prompt\": graph})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug ComfyUI workflow /preflight /submit standalone.")
    parser.add_argument("--workflow-json", required=True)
    parser.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--run-id", default="debug_run")
    parser.add_argument(
        "--patched-fields-json",
        default="",
        help='Path to patched_fields JSON (same shape as batch task) for resync uploads.',
    )
    parser.add_argument("--out-dir", default="", help="Debug artefacts dir (defaults to workflow dir).")
    args = parser.parse_args()

    wf_path = Path(args.workflow_json).resolve()
    out_dir = Path(args.out_dir) if args.out_dir else wf_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    workflow, _blob = load_workflow_dict(wf_path)
    stem = "workflow_debug"

    client = ComfyClient(args.comfy_url, timeout=min(240, args.timeout_sec))

    patched_fields_debug: dict = {}
    if args.patched_fields_json.strip():
        p = Path(args.patched_fields_json)
        patched_fields_debug = json.loads(p.read_text(encoding="utf-8"))

    if args.preflight:
        rs = resync_load_images_from_patched_fields(
            workflow,
            client,
            patched_fields_debug,
            preferred_subfolder_prefix=f"aigc2d/{args.run_id}",
        )
        if rs.get("warnings"):
            print("resync warnings:", rs["warnings"])

        pref = preflight_workflow_against_comfy(workflow, client)
        pref_path = out_dir / "debug_preflight_report.json"
        write_json(pref_path, pref)
        print(f"wrote preflight report: {pref_path}")
        print("summary:", pref.get("summary"))
        if not pref.get("ok"):
            print("preflight ERRORS:")
            for e in pref.get("errors", [])[:80]:
                print(e)

    if args.submit:
        try:
            pid = client.submit_prompt(workflow, debug_dir=out_dir, file_prefix=stem)
            print(f"prompt_id: {pid}")
            print(f"saved submit payload/error under: {out_dir}")
        except RuntimeError:
            raise SystemExit(1)
    elif not args.preflight:
        print("Use --preflight and/or --submit")


if __name__ == "__main__":
    main()
