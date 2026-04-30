from __future__ import annotations


class WallpaperScorer:
    def score(self, image_path: str, width: int = 3840, height: int = 2160) -> float:
        if not image_path:
            return 0.0
        ratio = width / max(height, 1)
        return 0.82 if 1.6 <= ratio <= 1.9 else 0.65
