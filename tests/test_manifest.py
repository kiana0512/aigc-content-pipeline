from aigc2d.manifest import create_run_manifest, load_run_manifest, sample_task, save_run_manifest


def test_run_manifest_roundtrip(tmp_path):
    task = sample_task()
    manifest = create_run_manifest(
        run_id="run_test",
        task=task,
        output_images=["out.png"],
        notes="demo",
    )
    path = save_run_manifest(manifest, root=tmp_path)
    loaded = load_run_manifest(path)
    assert loaded.run_id == "run_test"
    assert loaded.prompts[0].positive_prompt == task.prompt.positive_prompt
    assert loaded.output_images == ["out.png"]
    assert loaded.generation_params["steps"] == task.steps
