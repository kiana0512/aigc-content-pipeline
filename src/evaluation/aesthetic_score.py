from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _load_image_bgr(path: str | Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Failed to read image: {path}")
    return image


def _clamp_score(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    return max(min_value, min(max_value, value))


def compute_aesthetic_features(image_bgr: np.ndarray) -> dict[str, float]:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)

    brightness = float(gray.mean())
    contrast = float(gray.std())

    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    sharpness_score = _clamp_score(lap_var / 8.0)

    saturation = float(hsv[:, :, 1].mean())
    brightness_score = _clamp_score(100.0 - abs(brightness - 140.0) * 0.7)
    contrast_score = _clamp_score(contrast * 1.8)
    saturation_score = _clamp_score(saturation * 0.8)

    aesthetic_score = round(
        0.30 * brightness_score
        + 0.25 * contrast_score
        + 0.25 * sharpness_score
        + 0.20 * saturation_score,
        4,
    )

    return {
        "brightness_mean": round(brightness, 4),
        "contrast_std": round(contrast, 4),
        "sharpness_laplacian_var": round(lap_var, 4),
        "saturation_mean": round(saturation, 4),
        "brightness_score": round(brightness_score, 4),
        "contrast_score": round(contrast_score, 4),
        "sharpness_score": round(sharpness_score, 4),
        "saturation_score": round(saturation_score, 4),
        "aesthetic_score": aesthetic_score,
    }


def score_single_image_aesthetics(path: str | Path) -> dict:
    path = Path(path)
    image = _load_image_bgr(path)
    features = compute_aesthetic_features(image)
    features["path"] = str(path.as_posix())
    return features


def score_directory_aesthetics(input_dir: str | Path) -> list[dict]:
    input_dir = Path(input_dir)
    rows: list[dict] = []

    for path in sorted(input_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        rows.append(score_single_image_aesthetics(path))

    return rows