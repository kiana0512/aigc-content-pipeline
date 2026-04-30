from __future__ import annotations


class MockClipScorer:
    def score_text_image(self, prompt: str, image_path: str) -> float:
        return 0.72 if prompt and image_path else 0.0

    def score_reference_similarity(self, reference_image: str, output_image: str) -> float:
        return 0.68 if reference_image and output_image else 0.0
