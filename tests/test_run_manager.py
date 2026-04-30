from aigc2d.run_manager import RunManager


def test_run_manager_writes_run_manifest(tmp_path):
    manager = RunManager(tmp_path)
    path = manager.write_run_manifest("run_test", {"task_type": "img2img", "output_images": []})
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "run_test" in text
    assert "python_version" in text
