from __future__ import annotations

import argparse
import json
from pathlib import Path

import scripts.run_batch_generation as batch_script


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_submit_prefers_existing_patched_workflow(tmp_path: Path, monkeypatch) -> None:
    original_workflow = {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "original prompt A"}},
    }
    patched_workflow = {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "patched prompt B"}},
    }

    workflow_path = _write_json(tmp_path / "workflow.json", original_workflow)
    run_dir = tmp_path / "results" / "runs" / "submit_case"
    run_dir.mkdir(parents=True, exist_ok=True)
    patched_path = _write_json(run_dir / "patched_workflow.json", patched_workflow)
    _write_json(
        run_dir / "patched_workflow_index.json",
        {
            "items": [
                {
                    "item_id": "1",
                    "subject": "demo",
                    "patched_workflow": str(patched_path.as_posix()),
                }
            ]
        },
    )

    config = {
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
        "runtime": {"seed": 1},
        "comfyui": {
            "workflow_json": str(workflow_path.as_posix()),
            "base_url": "http://127.0.0.1:8000",
            "mapping_mode": "manual_map",
            "node_map": "",
        },
    }
    manifest = {"items": [{"id": "1", "subject": "demo"}]}
    args = argparse.Namespace(
        workflow_json="",
        mapping_mode="manual_map",
        node_map="",
        comfyui_url="",
        client_id="",
        run_name="submit_case",
    )

    captured_prompt_graph: dict = {}

    class FakeClient:
        def __init__(self, base_url: str) -> None:
            self.base_url = base_url

        def submit_prompt(self, prompt_graph: dict, client_id: str | None = None) -> dict:
            captured_prompt_graph.update(prompt_graph)
            return {"prompt_id": "fake_prompt_id"}

    def _unexpected_patch(*args, **kwargs):  # pragma: no cover - defensive assertion
        raise AssertionError("submit should not repatch when patched workflow already exists")

    monkeypatch.setattr(batch_script, "ComfyUIClient", FakeClient)
    monkeypatch.setattr(batch_script, "patch_workflow_with_report", _unexpected_patch)

    batch_script._patch_workflows_common(  # noqa: SLF001
        args=args,
        config=config,
        manifest=manifest,
        run_dir=run_dir,
        submit=True,
        force_auto_mode=False,
    )

    assert captured_prompt_graph["1"]["inputs"]["text"] == "patched prompt B"
    submit_log = json.loads((run_dir / "comfyui_submit_results.json").read_text(encoding="utf-8"))
    assert submit_log["used_existing_patched_workflows"] is True
    assert submit_log["results"][0]["prompt_id"] == "fake_prompt_id"
    assert submit_log["results"][0]["success"] is True
