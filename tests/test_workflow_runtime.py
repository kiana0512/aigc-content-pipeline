from aigc2d.config import write_json
from aigc2d.workflow_registry import WorkflowRegistry
from aigc2d.workflow_runtime import WorkflowRuntime, replace_placeholders


def make_runtime_with_active_workflow(tmp_path):
    workflow_json = tmp_path / "active_api.json"
    write_json(
        workflow_json,
        {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "{{checkpoint}}"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{positive_prompt}}"}},
            "3": {"class_type": "KSampler", "inputs": {"steps": "{{steps}}", "seed": "{{seed}}"}},
        },
    )
    registry = WorkflowRegistry(
        registry_dir=tmp_path / "registry",
        active_path=tmp_path / "active.yaml",
        workflow_dir=tmp_path / "workflows",
    )
    registry.import_workflow(workflow_json, "test_active", set_active=True)
    return WorkflowRuntime(workflow_registry=registry)


def test_replace_placeholders_preserves_types():
    patched = replace_placeholders({"width": "{{width}}", "text": "hello {{name}}"}, {"width": 1024, "name": "Firefly"})
    assert patched["width"] == 1024
    assert patched["text"] == "hello Firefly"


def test_workflow_runtime_builds_submit_ready_prompt(tmp_path):
    built = make_runtime_with_active_workflow(tmp_path).build_from_config(
        "configs/generation/firefly_wallpaper.yaml",
        prompt_row={
            "positive_prompt": "Firefly 4K wallpaper",
            "negative_prompt": "low quality",
            "reference_image": "firefly.png",
        },
    )
    workflow = built["workflow"]
    values = built["values"]
    assert values["checkpoint"]
    assert values["reference_image"] == "firefly.png"
    assert workflow["1"]["inputs"]["ckpt_name"] == values["checkpoint"]
    assert workflow["3"]["inputs"]["steps"] == 32


def test_workflow_runtime_supports_multi_inputs_and_prompt_bundle(tmp_path):
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        '{"positive_prompt":"bundle prompt","negative_prompt":"bundle negative","prompt_sections":{},"source_refs_used":[],"source_analysis_used":[],"tags_used":[],"style_preset_used":"x","notes":""}',
        encoding="utf-8",
    )
    built = make_runtime_with_active_workflow(tmp_path).build_from_config(
        "configs/generation/firefly_wallpaper.yaml",
        prompt_row={"prompt_bundle": str(bundle)},
        manifest_item={
            "init_image": "init.png",
            "identity_refs": "id1.png|id2.png",
            "face_refs": "face.png",
            "character_mask": "mask.png",
        },
    )
    values = built["values"]
    assert values["positive_prompt"] == "bundle prompt"
    assert values["identity_ref_images"] == ["id1.png", "id2.png"]
    assert values["identity_ref_images_first"] == "id1.png"
    assert values["character_mask"] == "mask.png"
    assert values["prompt_bundle"]["negative_prompt"] == "bundle negative"
