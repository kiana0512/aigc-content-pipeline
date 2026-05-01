import importlib.util
from pathlib import Path


def load_build_tasks_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "build_tasks.py"
    spec = importlib.util.spec_from_file_location("build_tasks", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_build_tasks_topk(tmp_path):
    build_tasks = load_build_tasks_module()
    raw = tmp_path / "raw" / "firefly.png"
    style1 = tmp_path / "style" / "style1.png"
    style2 = tmp_path / "style" / "style2.png"
    raw.parent.mkdir(parents=True)
    style1.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    style1.write_bytes(b"style")
    style2.write_bytes(b"style")
    (tmp_path / "processed" / "prompt_bundle").mkdir(parents=True)
    (tmp_path / "processed" / "prompt_bundle" / "prompt_bundle.json").write_text(
        '{"positive_prompt":"p","negative_prompt":"n","prompt_sections":{},"source_refs_used":[],"source_analysis_used":[],"tags_used":[],"style_preset_used":"x","notes":""}',
        encoding="utf-8",
    )
    rows = build_tasks.build_generation_tasks(tmp_path, mode="topk_style_per_init", topk=1)
    assert len(rows) == 1
    assert rows[0]["init_image"] == str(raw)
    assert rows[0]["style_asset"] == str(style1)
    assert rows[0]["positive_prompt"] == "p"


def test_build_tasks_single_init_all_styles_with_fallbacks(tmp_path):
    build_tasks = load_build_tasks_module()
    init = tmp_path / "selected" / "init" / "firefly.png"
    style1 = tmp_path / "style" / "style1.png"
    style2 = tmp_path / "style" / "style2.png"
    init.parent.mkdir(parents=True)
    style1.parent.mkdir(parents=True)
    init.write_bytes(b"raw")
    style1.write_bytes(b"style")
    style2.write_bytes(b"style")

    rows = build_tasks.build_generation_tasks(tmp_path, mode="single_init_all_styles")
    assert len(rows) == 2
    assert rows[0]["init_image"] == str(init)
    assert rows[0]["identity_ref_image"] == str(init)
    assert rows[0]["face_ref_image"] == str(init)
    assert rows[0]["style_ref_image"] == str(style1)


def test_build_tasks_uses_screenshots_for_composition_and_background(tmp_path):
    build_tasks = load_build_tasks_module()
    init = tmp_path / "selected" / "init" / "init.png"
    official = tmp_path / "raw" / "official" / "official.png"
    screenshot = tmp_path / "raw" / "screenshots" / "screen.png"
    style = tmp_path / "style" / "style.png"
    for path in [init, official, screenshot, style]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"image")

    rows = build_tasks.build_generation_tasks(tmp_path, mode="single_init_all_styles")
    assert rows[0]["identity_ref_image"] == str(official)
    assert rows[0]["composition_ref_image"] == str(screenshot)
    assert rows[0]["background_ref_image"] == str(screenshot)
