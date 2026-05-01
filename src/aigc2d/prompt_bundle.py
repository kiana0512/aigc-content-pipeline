from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


PROMPT_SECTIONS = [
    "subject",
    "identity",
    "face",
    "outfit",
    "mecha",
    "action",
    "composition",
    "background",
    "style",
    "quality",
    "wallpaper",
]


@dataclass
class PromptBundle:
    positive_prompt: str
    negative_prompt: str
    prompt_sections: dict[str, str] = field(default_factory=dict)
    source_refs_used: list[str] = field(default_factory=list)
    source_analysis_used: list[str] = field(default_factory=list)
    tags_used: list[str] = field(default_factory=list)
    provider_summary: dict[str, Any] = field(default_factory=dict)
    mock: bool = False
    provider_name: str = "PromptBundleBuilder"
    model_path: str = "analysis_outputs"
    device: str = ""
    runtime_ms: int = 0
    warnings: list[str] = field(default_factory=list)
    subject_core: dict[str, Any] = field(default_factory=dict)
    screenshot_cues: dict[str, Any] = field(default_factory=dict)
    style_cues: dict[str, Any] = field(default_factory=dict)
    composition_cues: dict[str, Any] = field(default_factory=dict)
    background_cues: dict[str, Any] = field(default_factory=dict)
    quality_cues: list[str] = field(default_factory=list)
    positive_sections: dict[str, str] = field(default_factory=dict)
    negative_sections: dict[str, str] = field(default_factory=dict)
    final_positive_prompt: str = ""
    final_negative_prompt: str = ""
    user_positive_append: str = ""
    user_negative_append: str = ""
    style_preset_used: str = "wallpaper_firefly"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_prompt_bundle(
    character_id: str,
    analyses: list[dict[str, Any]],
    negative_prompt: str,
    style_preset: str = "wallpaper_firefly",
    user_positive_append: str = "",
    user_negative_append: str = "",
) -> PromptBundle:
    tags: list[str] = []
    refs: list[str] = []
    analysis_paths: list[str] = []
    captions: list[tuple[dict[str, Any], dict[str, Any]]] = []
    providers: dict[str, Any] = {}
    mock = False
    for item in analyses:
        refs.append(str(item.get("image_path", "")))
        analysis_paths.append(str(item.get("analysis_path", "")))
        tag_payload = item.get("tags", {})
        tag_items = tag_payload.get("tags", tag_payload if isinstance(tag_payload, list) else [])
        for tag in tag_items:
            tags.append(str(tag.get("tag", tag) if isinstance(tag, dict) else tag))
        captions.append((item.get("caption", {}), item))
        providers.update(item.get("providers", {}))
        mock = mock or bool(item.get("mock", False))
    first = captions[0][0] if captions else {}
    appearance = first.get("appearance", {}) if isinstance(first.get("appearance", {}), dict) else {}
    style = first.get("style", {}) if isinstance(first.get("style", {}), dict) else {}
    screenshot_items = [(caption, item) for caption, item in captions if item.get("source_type") == "screenshot"]
    style_items = [(caption, item) for caption, item in captions if item.get("role") == "style"]
    composition_items = [(caption, item) for caption, item in captions if item.get("role") == "composition" or item.get("source_type") == "screenshot"]
    background_items = [(caption, item) for caption, item in captions if item.get("role") == "background" or item.get("source_type") == "screenshot"]
    tag_text = ", ".join(tags[:20])
    subject_core = {
        "summary": first.get("summary", ""),
        "hair": appearance.get("hair", ""),
        "eyes": appearance.get("eyes", ""),
        "face": appearance.get("face", ""),
        "outfit": appearance.get("outfit", ""),
        "accessories": appearance.get("accessories", ""),
        "weapon": appearance.get("weapon", ""),
        "mecha_parts": appearance.get("mecha", ""),
        "tags": tags[:30],
    }
    screenshot_cues = _merge_caption_fields(
        screenshot_items,
        ["pose", "action", "camera_angle", "composition", "background", "scene", "effects_lighting", "mood", "combat_atmosphere"],
    )
    style_cues = _merge_style_fields(style_items or captions)
    composition_cues = _merge_caption_fields(composition_items or captions, ["composition", "camera_angle", "pose", "action"])
    background_cues = _merge_caption_fields(background_items or captions, ["background", "scene", "effects_lighting", "mood"])
    quality_cues = ["high detail", "clean lineart", "high quality anime illustration", "cinematic composition", "wallpaper quality"]
    positive_sections = {
        "subject": ", ".join(_clean([character_id, subject_core["summary"], tag_text])),
        "identity": ", ".join(_clean([subject_core["hair"], subject_core["eyes"], subject_core["face"], subject_core["outfit"], subject_core["accessories"], subject_core["weapon"], subject_core["mecha_parts"]])),
        "pose_action": ", ".join(_clean([screenshot_cues.get("pose", ""), screenshot_cues.get("action", ""), screenshot_cues.get("combat_atmosphere", "")])),
        "composition": ", ".join(_clean([composition_cues.get("composition", ""), composition_cues.get("camera_angle", "")])),
        "background": ", ".join(_clean([background_cues.get("background", ""), background_cues.get("scene", ""), background_cues.get("effects_lighting", ""), background_cues.get("mood", "")])),
        "style": ", ".join(_clean([style_cues.get("lineart", ""), style_cues.get("shading", ""), style_cues.get("color_palette", ""), style_cues.get("lighting", ""), style_cues.get("brushwork", ""), style_cues.get("overall_aesthetic", "")])),
        "quality": ", ".join(quality_cues),
        "user_append": user_positive_append,
    }
    positive = ", ".join(str(value) for value in positive_sections.values() if value)
    screenshot_negative = "game ui, hud, subtitle, watermark, extra characters, cluttered background, blurry face, distorted anatomy, cropped head, cut off hands"
    negative_sections = {
        "general_negative": negative_prompt,
        "screenshot_negative": screenshot_negative,
        "user_negative_append": user_negative_append,
    }
    final_negative = ", ".join(_clean(negative_sections.values()))
    return PromptBundle(
        positive_prompt=positive,
        negative_prompt=final_negative,
        prompt_sections=positive_sections,
        source_refs_used=[ref for ref in refs if ref],
        source_analysis_used=[path for path in analysis_paths if path],
        tags_used=sorted(set(tags)),
        provider_summary=providers,
        mock=mock,
        device=str(next((item.get("device", "") for item in analyses if item.get("device")), "")),
        warnings=[warning for item in analyses for warning in item.get("warnings", [])],
        subject_core=subject_core,
        screenshot_cues=screenshot_cues,
        style_cues=style_cues,
        composition_cues=composition_cues,
        background_cues=background_cues,
        quality_cues=quality_cues,
        positive_sections=positive_sections,
        negative_sections=negative_sections,
        final_positive_prompt=positive,
        final_negative_prompt=final_negative,
        user_positive_append=user_positive_append,
        user_negative_append=user_negative_append,
        style_preset_used=style_preset,
        notes="Auto-generated from provider analysis; review and edit before large batch runs.",
    )


def save_prompt_bundle(bundle: PromptBundle, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _clean(values: Any) -> list[str]:
    return [str(value).strip() for value in values if str(value or "").strip()]


def _merge_caption_fields(items: list[tuple[dict[str, Any], dict[str, Any]]], fields: list[str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for field_name in fields:
        values = []
        for caption, _ in items:
            value = caption.get(field_name, "")
            if isinstance(value, dict):
                value = ", ".join(_clean(value.values()))
            values.extend(_clean([value]))
        merged[field_name] = ", ".join(dict.fromkeys(values))
    return merged


def _merge_style_fields(items: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, str]:
    fields = ["medium", "lineart", "shading", "color_palette", "lighting", "brushwork", "rendering", "overall_aesthetic"]
    merged: dict[str, str] = {}
    for field_name in fields:
        values = []
        for caption, _ in items:
            style = caption.get("style", {}) if isinstance(caption.get("style", {}), dict) else {}
            value = style.get(field_name, caption.get(field_name, ""))
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            values.extend(_clean([value]))
        merged[field_name] = ", ".join(dict.fromkeys(values))
    return merged


def load_prompt_bundle(path: str | Path) -> PromptBundle:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for key, value in {
        "provider_summary": {},
        "mock": False,
        "user_positive_append": "",
        "user_negative_append": "",
        "provider_name": "PromptBundleBuilder",
        "model_path": "analysis_outputs",
        "device": "",
        "runtime_ms": 0,
        "warnings": [],
        "subject_core": {},
        "screenshot_cues": {},
        "style_cues": {},
        "composition_cues": {},
        "background_cues": {},
        "quality_cues": [],
        "positive_sections": data.get("prompt_sections", {}),
        "negative_sections": {},
        "final_positive_prompt": data.get("positive_prompt", ""),
        "final_negative_prompt": data.get("negative_prompt", ""),
    }.items():
        data.setdefault(key, value)
    return PromptBundle(**data)
