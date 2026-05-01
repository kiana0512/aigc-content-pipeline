import json

from aigc2d.providers.vlm_provider import (
    LocalVLMProvider,
    _json_candidate_slices,
)


def test_json_candidate_slices_fenced_and_nested():
    raw = """Here is JSON:
```json
{"summary": "ok", "nested": {"x": 1}}
```
"""
    frags = _json_candidate_slices(raw)
    assert frags
    data = json.loads(frags[0])
    assert data["summary"] == "ok"


def test_coerce_caption_fills_summary_from_keywords():
    p = LocalVLMProvider.__new__(LocalVLMProvider)
    text = '{"keywords": ["red hair", "blue eyes"], "appearance": {}}'
    out = LocalVLMProvider._coerce_structured_caption(p, text, "raw")
    assert out is not None
    assert "red hair" in out["summary"]


def test_coerce_merges_flat_appearance_style_keys():
    p = LocalVLMProvider.__new__(LocalVLMProvider)
    text = (
        '{"summary": "x", '
        '"appearance_hair": "long", '
        '"appearance_eyes": "blue", '
        '"style_medium": "digital", '
        '"keywords": []}'
    )
    out = LocalVLMProvider._coerce_structured_caption(p, text, "init")
    assert out is not None
    assert out["appearance"]["hair"] == "long"
    assert out["appearance"]["eyes"] == "blue"
    assert out["style"]["medium"] == "digital"
    assert "appearance_hair" not in out
