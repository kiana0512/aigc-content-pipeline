from aigc2d.prompt_bundle import build_prompt_bundle, load_prompt_bundle, save_prompt_bundle


def test_prompt_bundle_roundtrip(tmp_path):
    bundle = build_prompt_bundle(
        "firefly",
        [
            {
                "image_path": "ref.png",
                "tags": ["firefly", "wallpaper"],
                "description": {"appearance": "teal eyes", "outfit": "sci-fi suit"},
                "analysis_path": "analysis.json",
            }
        ],
        negative_prompt="low quality",
    )
    path = save_prompt_bundle(bundle, tmp_path / "bundle.json")
    loaded = load_prompt_bundle(path)
    assert "firefly" in loaded.positive_prompt
    assert loaded.prompt_sections["identity"] == "teal eyes"
    assert "wallpaper" in loaded.tags_used
