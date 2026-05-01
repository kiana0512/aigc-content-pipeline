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


def test_workflow_runtime_patches_registry_node_inputs_and_images(tmp_path):
    image = tmp_path / "init.png"
    image.write_bytes(b"image")
    workflow_json = tmp_path / "api.json"
    write_json(
        workflow_json,
        {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "old positive"}},
            "2": {"class_type": "LoadImage", "inputs": {"image": "old.png"}},
            "3": {"class_type": "VAEEncode", "inputs": {"pixels": ["2", 0]}},
            "4": {"class_type": "KSampler", "inputs": {"positive": ["1", 0], "latent_image": ["3", 0], "seed": 1, "steps": 10, "cfg": 4, "sampler_name": "euler", "scheduler": "normal", "denoise": 1}},
            "5": {"class_type": "SaveImage", "inputs": {"images": ["4", 0], "filename_prefix": "old"}},
        },
    )
    registry = WorkflowRegistry(
        registry_dir=tmp_path / "registry",
        active_path=tmp_path / "active.yaml",
        workflow_dir=tmp_path / "registered",
    )
    registry.import_workflow(workflow_json, "patchable", set_active=True)
    built = WorkflowRuntime(workflow_registry=registry).build_from_config(
        "configs/generation/firefly_wallpaper.yaml",
        prompt_row={"positive_prompt": "new prompt", "init_image": str(image), "seed": "123", "output_prefix": "run/out"},
        run_id="run1",
        comfy_input_dir=tmp_path / "comfy_input",
        dry_run=True,
    )

    workflow = built["workflow"]
    assert workflow["1"]["inputs"]["text"] == "new prompt"
    assert workflow["2"]["inputs"]["image"].startswith("aigc2d/run1/")
    assert workflow["4"]["inputs"]["seed"] == "123"
    assert workflow["5"]["inputs"]["filename_prefix"] == "run/out"
    assert built["patched_fields"]["init_image"]["node_id"] == "2"
    assert built["copied_uploaded_image_names"]["init_image"].startswith("aigc2d/run1/")
