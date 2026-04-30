from __future__ import annotations

from pathlib import Path
from typing import Protocol, TypedDict


class VLMDescription(TypedDict, total=False):
    summary: str
    appearance: str
    outfit: str
    pose: str
    composition: str
    background: str
    style: str
    keywords: list[str]


class VLMProvider(Protocol):
    def caption(self, image_path: str) -> str:
        ...

    def critique(self, image_path: str, prompt: str | None = None) -> dict[str, object]:
        ...

    def structured_describe(self, image_path: str) -> VLMDescription:
        ...

    def describe(self, image_path: str) -> VLMDescription:
        ...


class MockVLMProvider:
    def caption(self, image_path: str) -> str:
        return self.structured_describe(image_path)["summary"]

    def critique(self, image_path: str, prompt: str | None = None) -> dict[str, object]:
        return {
            "score": 0.72,
            "strengths": ["clear character focus", "wallpaper-friendly composition"],
            "issues": ["mock critique; replace with real VLM provider"],
            "prompt": prompt or "",
        }

    def structured_describe(self, image_path: str) -> VLMDescription:
        stem = Path(image_path).stem.replace("_", " ")
        return {
            "summary": f"Reference image for {stem}, prepared for high-aesthetic 4K wallpaper generation",
            "appearance": "Firefly-like sci-fi anime heroine, clear facial features",
            "outfit": "white and teal futuristic combat outfit with luminous accents",
            "pose": "heroic standing pose, elegant and calm",
            "composition": "single character centered with wide wallpaper negative space",
            "background": "soft cinematic sci-fi glow, starry abstract particles",
            "style": "polished 2D anime illustration, premium game key visual",
            "keywords": ["Firefly", "anime", "sci-fi", "4K wallpaper", "teal glow"],
        }

    def describe(self, image_path: str) -> VLMDescription:
        return self.structured_describe(image_path)
