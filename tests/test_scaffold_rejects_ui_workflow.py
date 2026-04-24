from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import scripts.run_batch_generation as batch_script


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_scaffold_rejects_ui_workflow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    workflow_path = tmp_path / "workflows" / "comfyui" / "ui_like_workflow.json"
    _write_json(
        workflow_path,
        {
            "last_node_id": 3,
            "last_link_id": 2,
            "nodes": [{"id": 1, "type": "CLIPTextEncode"}],
            "links": [],
        },
    )

    args = argparse.Namespace(
        workflow_json=str(workflow_path.as_posix()),
        slug="ui_case",
        force=False,
        validate=False,
        submit_after_validate=False,
        config="",
        mode="scaffold_workflow",
    )
    with pytest.raises(
        ValueError,
        match="This looks like a ComfyUI UI workflow, not API workflow. Please use Export\\(API\\).",
    ):
        batch_script.run_scaffold_workflow(args)

    assert not (tmp_path / "configs" / "ui_case_api.yaml").exists()
