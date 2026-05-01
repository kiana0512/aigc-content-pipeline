from aigc2d.config import write_json
from aigc2d.workflow_inspector import inspect_workflow
from aigc2d.workflow_registry import WorkflowRegistry


def test_workflow_import_and_set_active(tmp_path):
    workflow_json = tmp_path / "workflow.json"
    write_json(
        workflow_json,
        {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "{{checkpoint}}"}},
            "2": {"class_type": "KSampler", "inputs": {"seed": "{{seed}}"}},
        },
    )
    registry = WorkflowRegistry(
        registry_dir=tmp_path / "registry",
        active_path=tmp_path / "active.yaml",
        workflow_dir=tmp_path / "workflows",
    )
    metadata = registry.import_workflow(workflow_json, "demo_workflow", set_active=True)
    active = registry.get_active()
    info = inspect_workflow(metadata)
    assert active is not None
    assert active.workflow_id == "demo_workflow"
    assert "checkpoint" in info["placeholders"]


def test_workflow_import_generates_auto_registry(tmp_path):
    workflow_json = tmp_path / "workflow.json"
    write_json(
        workflow_json,
        {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "p"}},
            "2": {"class_type": "KSampler", "inputs": {"positive": ["1", 0], "seed": 1}},
            "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0], "filename_prefix": "out"}},
        },
    )
    registry = WorkflowRegistry(
        registry_dir=tmp_path / "registry",
        active_path=tmp_path / "active.yaml",
        workflow_dir=tmp_path / "registered",
    )
    metadata = registry.import_workflow(workflow_json, "auto_workflow", set_active=True)
    assert metadata.patch_contract["node_inputs"]["positive_prompt"]["node_id"] == "1"
    assert metadata.patch_contract["node_inputs"]["seed"]["node_id"] == "2"
    assert registry.metadata_path("auto_workflow").exists()
