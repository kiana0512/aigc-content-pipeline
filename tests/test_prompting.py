import pytest

from aigc2d.prompt_builder import MissingPromptVariable, PromptBuilder, render_template


def test_render_template_replaces_variables():
    assert render_template("hello {name}", {"name": "Luna"}) == "hello Luna"


def test_render_template_requires_variables():
    with pytest.raises(MissingPromptVariable):
        render_template("hello {name}", {})


def test_prompt_builder_layers_description_tags_and_negative_prompt():
    prompt = PromptBuilder(
        style_presets={"anime_game_asset": "clean anime style"},
        negative_presets={"anime_default": "bad anatomy"},
    ).build(
        user_prompt="March 7th",
        vlm_description={"appearance": "pink hair", "outfit": "blue coat"},
        tags=["hsr", "bow"],
        style_preset="anime_game_asset",
        quality_tokens=["best quality"],
        negative_prompt_preset="anime_default",
    )
    assert "March 7th" in prompt.positive_prompt
    assert "pink hair" in prompt.positive_prompt
    assert "hsr" in prompt.positive_prompt
    assert prompt.negative_prompt == "bad anatomy"
    assert prompt.layers["subject"] == "March 7th"
