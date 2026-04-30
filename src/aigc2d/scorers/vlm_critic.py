from __future__ import annotations

from aigc2d.vlm import MockVLMProvider, VLMProvider


class MockVLMCritic:
    def __init__(self, provider: VLMProvider | None = None) -> None:
        self.provider = provider or MockVLMProvider()

    def score(self, image_path: str, prompt: str = "") -> float:
        critique = self.provider.critique(image_path, prompt=prompt)
        return float(critique.get("score", 0.0))
