from __future__ import annotations

import itertools
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _load_image_bgr(path: str | Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Failed to read image: {path}")
    return image


def _color_histogram(image_bgr: np.ndarray, bins: tuple[int, int, int] = (8, 8, 8)) -> np.ndarray:
    hist = cv2.calcHist([image_bgr], [0, 1, 2], None, bins, [0, 256, 0, 256, 0, 256])
    hist = cv2.normalize(hist, hist).flatten()
    return hist


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def pairwise_histogram_consistency(
    image_paths: list[str | Path],
    max_pairs: int = 200,
) -> float:
    paths = [Path(p) for p in image_paths]
    if len(paths) < 2:
        return 100.0

    hists = [_color_histogram(_load_image_bgr(path)) for path in paths]
    pairs = list(itertools.combinations(range(len(hists)), 2))
    pairs = pairs[:max_pairs]

    scores = []
    for i, j in pairs:
        scores.append(_cosine_similarity(hists[i], hists[j]))

    if not scores:
        return 0.0

    return round(float(np.mean(scores) * 100.0), 4)


def _resolution_consistency(image_paths: list[str | Path]) -> float:
    if not image_paths:
        return 0.0

    counter = Counter()
    for path in image_paths:
        with Image.open(path) as img:
            counter[f"{img.width}x{img.height}"] += 1

    most_common_count = counter.most_common(1)[0][1]
    return round(most_common_count / len(image_paths) * 100.0, 4)


def directory_consistency_report(input_dir: str | Path) -> dict:
    input_dir = Path(input_dir)
    image_paths = [
        path
        for path in sorted(input_dir.rglob("*"))
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]

    return {
        "input_dir": str(input_dir.as_posix()),
        "num_images": len(image_paths),
        "histogram_consistency_score": pairwise_histogram_consistency(image_paths),
        "resolution_consistency_score": _resolution_consistency(image_paths),
        "sample_files": [str(path.as_posix()) for path in image_paths[:10]],
    }