import sys
import importlib.util
from pathlib import Path

from aigc2d.generation_config import GenerationConfig
from aigc2d.model_profiles import ResolvedModels


def load_batch_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "batch_generate_stub.py"
    spec = importlib.util.spec_from_file_location("batch_generate_stub", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeRuntime:
    def build_from_config(self, *args, **kwargs):
        return {
            "workflow": {"1": {"class_type": "SaveImage", "inputs": {}}},
            "values": {"positive_prompt": "p", "negative_prompt": "n", "reference_image": "ref.png"},
            "generation_config": GenerationConfig(name="test", task_type="img2img", workflow="active_workflow", model_profile="animagine_xl"),
            "resolved_models": ResolvedModels(checkpoint="ckpt", vae="vae"),
            "workflow_template_path": "active.json",
            "active_workflow": {"workflow_id": "active_test"},
            "patch_warnings": [],
            "patched_fields": {},
            "skipped_fields": {},
            "skipped_model_patch_fields": [],
            "preserved_template_model_fields": [],
            "explicit_model_patch_fields_used": [],
            "preserve_template_models": False,
            "copied_uploaded_image_names": {},
        }

    def workflow_template_path(self, workflow):
        return "active.json"


def test_batch_generate_dry_run(tmp_path, monkeypatch):
    batch = load_batch_module()
    output = tmp_path / "tasks.json"
    monkeypatch.setattr(batch, "WorkflowRuntime", FakeRuntime)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "batch_generate_stub.py",
            "--dry-run",
            "--max-items",
            "1",
            "--output",
            str(output),
        ],
    )
    batch.main()
    assert output.exists()


def test_batch_generate_execute_with_fake_client(tmp_path, monkeypatch):
    batch = load_batch_module()
    output = tmp_path / "tasks.json"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_object_info(self):
            return {}

        def get_history(self, prompt_id):
            return {}

        def view_image_exists(self, *args, **kwargs):
            return True

        def submit_prompt(self, workflow, debug_dir=None, file_prefix="", **kwargs):
            return "prompt-1"

        def poll_history(self, prompt_id, timeout_sec=600):
            return {"outputs": {"1": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}

        def fetch_output_images(self, history):
            return history["outputs"]["1"]["images"]

    monkeypatch.setattr(batch, "ComfyClient", FakeClient)
    monkeypatch.setattr(batch, "WorkflowRuntime", FakeRuntime)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "batch_generate_stub.py",
            "--execute",
            "--max-items",
            "1",
            "--output",
            str(output),
        ],
    )
    batch.main()
    assert output.exists()
