from __future__ import annotations

import argparse
import json
from pathlib import Path

import scripts.run_batch_generation as batch_script


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_batch_submit_submits_all_items(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "results" / "runs" / "submit_all_case"
    patched_dir = run_dir / "patched_workflows"

    workflow1 = _write_json(
        patched_dir / "item_0001_patched_workflow.json",
        {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "prompt 1"}}},
    )
    workflow2 = _write_json(
        patched_dir / "item_0002_patched_workflow.json",
        {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "prompt 2"}}},
    )

    manifest = {
        "items": [
            {
                "id": "1",
                "item_id": "1",
                "item_index": 1,
                "positive_prompt": "prompt 1",
                "filename_prefix": "prefix_1",
                "patched_workflow_path": str(workflow1.as_posix()),
            },
            {
                "id": "2",
                "item_id": "2",
                "item_index": 2,
                "positive_prompt": "prompt 2",
                "filename_prefix": "prefix_2",
                "patched_workflow_path": str(workflow2.as_posix()),
            },
        ]
    }

    args = argparse.Namespace(
        workflow_json="",
        mapping_mode="manual_map",
        node_map="",
        comfyui_url="",
        client_id="",
        run_name="submit_all_case",
    )
    config = {
        "runtime": {"seed": 1},
        "generation": {
            "width": 512,
            "height": 512,
            "batch_size": 1,
            "num_inference_steps": 20,
            "guidance_scale": 7.0,
            "sampler": "euler",
            "scheduler": "normal",
            "filename_prefix": "demo",
        },
        "comfyui": {"base_url": "http://127.0.0.1:8000"},
    }

    calls: list[dict] = []

    class FakeClient:
        def __init__(self, base_url: str) -> None:
            self.base_url = base_url

        def submit_prompt(self, prompt_graph: dict, client_id: str | None = None) -> dict:
            calls.append(prompt_graph)
            return {"prompt_id": f"pid_{len(calls)}"}

    monkeypatch.setattr(batch_script, "ComfyUIClient", FakeClient)

    batch_script._patch_workflows_common(  # noqa: SLF001
        args=args,
        config=config,
        manifest=manifest,
        run_dir=run_dir,
        submit=True,
        force_auto_mode=False,
    )

    assert len(calls) == 2
    submit_log = json.loads((run_dir / "comfyui_submit_results.json").read_text(encoding="utf-8"))
    assert submit_log["total_items"] == 2
    assert submit_log["submitted_items"] == 2
    assert submit_log["failed_items"] == 0
    assert len(submit_log["results"]) == 2
    assert submit_log["results"][0]["success"] is True
    assert submit_log["results"][1]["success"] is True
