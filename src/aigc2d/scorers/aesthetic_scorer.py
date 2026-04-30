from __future__ import annotations


class MockAestheticScorer:
    def score(self, image_path: str) -> float:
        return 0.76 if image_path else 0.0
