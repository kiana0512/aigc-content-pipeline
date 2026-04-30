from __future__ import annotations

from pathlib import Path
from typing import Protocol


class TaggerProvider(Protocol):
    def tag(self, image_path: str) -> list[str]:
        ...

    def structured_tags(self, image_path: str) -> dict[str, list[str]]:
        ...


class MockTaggerProvider:
    def tag(self, image_path: str) -> list[str]:
        stem_tags = [
            part.lower()
            for part in Path(image_path).stem.replace("-", "_").split("_")
            if part
        ]
        return [*stem_tags, "anime", "character_reference", "2d_game_asset"]

    def structured_tags(self, image_path: str) -> dict[str, list[str]]:
        tags = self.tag(image_path)
        return {
            "character": [tag for tag in tags if tag in {"firefly", "liuying", "流萤"}],
            "style": ["anime", "game key visual", "wallpaper"],
            "technical": ["clean lineart", "high detail", "4k"],
            "raw": tags,
        }
