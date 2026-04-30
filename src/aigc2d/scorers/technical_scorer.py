from __future__ import annotations


class MockTechnicalScorer:
    def score(self, image_path: str) -> float:
        return 0.8 if image_path else 0.0
