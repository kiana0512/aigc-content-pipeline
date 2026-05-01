from aigc2d.prompt_bundle import build_prompt_bundle, load_prompt_bundle, save_prompt_bundle


def test_prompt_bundle_roundtrip(tmp_path):
    bundle = build_prompt_bundle(
        "firefly",
        [
            {
                "image_path": "ref.png",
                "tags": {"tags": [{"tag": "firefly", "score": 0.9}, {"tag": "wallpaper", "score": 0.8}]},
                "caption": {"summary": "firefly character", "appearance": {"hair": "silver hair", "eyes": "teal eyes", "outfit": "sci-fi suit"}},
                "analysis_path": "analysis.json",
                "providers": {"vlm": "test_vlm", "tagger": "test_tagger"},
            }
        ],
        negative_prompt="low quality",
    )
    path = save_prompt_bundle(bundle, tmp_path / "bundle.json")
    loaded = load_prompt_bundle(path)
    assert "firefly" in loaded.positive_prompt
    assert "teal eyes" in loaded.prompt_sections["identity"]
    assert "wallpaper" in loaded.tags_used
    assert loaded.provider_summary["vlm"] == "test_vlm"


def test_prompt_bundle_prioritizes_screenshot_cues():
    bundle = build_prompt_bundle(
        "firefly",
        [
            {
                "image_path": "screen.png",
                "source_type": "screenshot",
                "role": "raw",
                "tags": {"tags": [{"tag": "battle", "score": 0.9}]},
                "caption": {
                    "summary": "combat screenshot",
                    "appearance": {"hair": "silver hair", "eyes": "teal eyes", "outfit": "sci-fi armor"},
                    "pose": "mid-air attack pose",
                    "action": "swinging a weapon",
                    "camera_angle": "low angle",
                    "composition": "dynamic diagonal framing",
                    "background": "glowing battlefield",
                    "scene": "ruined sci-fi city",
                    "effects_lighting": "green energy trails",
                    "combat_atmosphere": "intense battle mood",
                },
                "analysis_path": "screen_analysis.json",
            }
        ],
        negative_prompt="low quality",
    )
    assert "swinging a weapon" in bundle.screenshot_cues["action"]
    assert "low angle" in bundle.positive_sections["composition"]
    assert "glowing battlefield" in bundle.positive_sections["background"]
    assert "game ui" in bundle.final_negative_prompt
