from __future__ import annotations

from string import Formatter
from typing import Any

from .schemas import PromptSpec
from .vlm import VLMDescription


class MissingPromptVariable(ValueError):
    pass


DEFAULT_STYLE_PRESETS = {
    "anime_game_asset": "anime game character art, clean lineart, polished 2D illustration",
    "key_visual": "cinematic anime key visual, strong focal point, promotional illustration",
}


def render_template(template: str, variables: dict[str, Any]) -> str:
    required = [name for _, name, _, _ in Formatter().parse(template) if name]
    missing = [name for name in required if name not in variables or variables[name] in (None, "")]
    if missing:
        raise MissingPromptVariable(f"Missing prompt variables: {', '.join(missing)}")
    return template.format(**variables)


def _join(parts: list[str]) -> str:
    return ", ".join(part.strip() for part in parts if part and part.strip())


class PromptBuilder:
    def __init__(
        self,
        style_presets: dict[str, str] | None = None,
        negative_presets: dict[str, str] | None = None,
    ) -> None:
        self.style_presets = style_presets or DEFAULT_STYLE_PRESETS
        self.negative_presets = negative_presets or {}

    def build(
        self,
        user_prompt: str,
        vlm_description: VLMDescription | dict[str, Any] | None = None,
        tags: list[str] | None = None,
        style_preset: str = "anime_game_asset",
        quality_tokens: list[str] | None = None,
        negative_prompt_preset: str | None = None,
    ) -> PromptSpec:
        desc = dict(vlm_description or {})
        tag_text = ", ".join(tags or [])
        layers = {
            "subject": user_prompt,
            "appearance": str(desc.get("appearance", "")),
            "outfit": str(desc.get("outfit", "")),
            "pose": str(desc.get("pose", "")),
            "background": str(desc.get("background", "")),
            "style": self.style_presets.get(style_preset, style_preset),
            "quality": _join(quality_tokens or []),
        }
        positive = _join([*layers.values(), tag_text])
        negative = self.negative_presets.get(
            negative_prompt_preset or "",
            negative_prompt_preset or "",
        )
        return PromptSpec(
            positive_prompt=positive,
            negative_prompt=negative,
            layers=layers,
            metadata={
                "style_preset": style_preset,
                "tags": tags or [],
                "vlm_description": desc,
            },
        )
