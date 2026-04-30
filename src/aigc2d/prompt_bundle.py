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
    style_preset_used: str = "wallpaper_firefly"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_prompt_bundle(
    character_id: str,
    analyses: list[dict[str, Any]],
    negative_prompt: str,
    style_preset: str = "wallpaper_firefly",
) -> PromptBundle:
    tags: list[str] = []
    refs: list[str] = []
    analysis_paths: list[str] = []
    descriptions: list[dict[str, Any]] = []
    for item in analyses:
        refs.append(str(item.get("image_path", "")))
        analysis_paths.append(str(item.get("analysis_path", "")))
        tags.extend([str(tag) for tag in item.get("tags", [])])
        descriptions.append(item.get("description", {}))
    first = descriptions[0] if descriptions else {}
    sections = {
        "subject": f"{character_id}, high-aesthetic anime game character wallpaper",
        "identity": str(first.get("appearance", "consistent character identity")),
        "face": "clean face, expressive eyes, recognizable facial features",
        "outfit": str(first.get("outfit", "accurate outfit details")),
        "mecha": "sci-fi mecha details, luminous green accents",
        "composition": str(first.get("composition", "wide cinematic wallpaper composition")),
        "background": str(first.get("background", "cinematic sci-fi background")),
        "style": str(first.get("style", "polished 2D anime key visual")),
        "quality": "masterpiece, best quality, high detail, clean lineart",
        "wallpaper": "4K desktop wallpaper, wide aspect ratio, balanced negative space",
    }
    positive = ", ".join(value for value in sections.values() if value)
    return PromptBundle(
        positive_prompt=positive,
        negative_prompt=negative_prompt,
        prompt_sections=sections,
        source_refs_used=[ref for ref in refs if ref],
        source_analysis_used=[path for path in analysis_paths if path],
        tags_used=sorted(set(tags)),
        style_preset_used=style_preset,
        notes="Auto-generated; review and edit before large batch runs.",
    )


def save_prompt_bundle(bundle: PromptBundle, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def load_prompt_bundle(path: str | Path) -> PromptBundle:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return PromptBundle(**data)
