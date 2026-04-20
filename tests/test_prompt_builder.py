from src.generation.prompt_builder import (
    PromptItem,
    build_prompt_items,
    fill_prompt_template,
    sanitize_filename,
)


def test_sanitize_filename_basic() -> None:
    assert sanitize_filename("Fire Sword") == "fire_sword"
    assert sanitize_filename("Ice/Crystal") == "ice_crystal"
    assert sanitize_filename("Potion-Blue") == "potion_blue"


def test_fill_prompt_template_replaces_placeholders() -> None:
    template = "Create {subject} in {style} style with {attributes}."
    result = fill_prompt_template(
        template=template,
        subject="fire sword",
        style="fantasy game ui",
        attributes="glowing edges",
    )
    assert "fire sword" in result
    assert "fantasy game ui" in result
    assert "glowing edges" in result
    assert "{subject}" not in result
    assert "{style}" not in result
    assert "{attributes}" not in result


def test_fill_prompt_template_supports_character_subject() -> None:
    template = "Design {character_subject} with {style} rendering."
    result = fill_prompt_template(
        template=template,
        subject="mage girl",
        style="anime fantasy",
        attributes="unused",
    )
    assert "mage girl" in result
    assert "anime fantasy" in result


def test_build_prompt_items_count_and_content() -> None:
    subjects = ["fire sword", "ice crystal"]
    positive_template = "Create {subject} in {style} style with {attributes}."
    negative_template = "blurry, cluttered"

    items = build_prompt_items(
        subjects=subjects,
        positive_template=positive_template,
        negative_template=negative_template,
        style="fantasy game ui",
        attributes="clean silhouette",
    )

    assert len(items) == 2
    assert isinstance(items[0], PromptItem)

    first = items[0]
    assert first.id == 1
    assert first.subject == "fire sword"
    assert first.style == "fantasy game ui"
    assert first.attributes == "clean silhouette"
    assert "fire sword" in first.positive_prompt_text
    assert "fantasy game ui" in first.positive_prompt_text
    assert "clean silhouette" in first.positive_prompt_text
    assert first.negative_prompt_text == "blurry, cluttered"