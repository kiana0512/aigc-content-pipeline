from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def canny_edge_map(
    image_bgr: np.ndarray,
    threshold1: int = 100,
    threshold2: int = 200,
    blur_kernel: int = 3,
) -> np.ndarray:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    if blur_kernel and blur_kernel > 1:
        if blur_kernel % 2 == 0:
            blur_kernel += 1
        gray = cv2.GaussianBlur(gray, (blur_kernel, blur_kernel), 0)

    edges = cv2.Canny(gray, threshold1=threshold1, threshold2=threshold2)
    return edges


def process_single_edge_image(
    input_path: str | Path,
    output_path: str | Path,
    threshold1: int = 100,
    threshold2: int = 200,
    blur_kernel: int = 3,
) -> None:
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    image = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Failed to read image: {input_path}")

    edges = canny_edge_map(
        image_bgr=image,
        threshold1=threshold1,
        threshold2=threshold2,
        blur_kernel=blur_kernel,
    )

    success = cv2.imwrite(str(output_path), edges)
    if not success:
        raise IOError(f"Failed to write edge image: {output_path}")


def process_edge_directory(
    input_dir: str | Path,
    output_dir: str | Path,
    threshold1: int = 100,
    threshold2: int = 200,
    blur_kernel: int = 3,
) -> list[Path]:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written_paths: list[Path] = []

    for input_path in sorted(input_dir.rglob("*")):
        if not input_path.is_file() or input_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        output_name = f"{input_path.stem}_edge.png"
        output_path = output_dir / output_name

        process_single_edge_image(
            input_path=input_path,
            output_path=output_path,
            threshold1=threshold1,
            threshold2=threshold2,
            blur_kernel=blur_kernel,
        )
        written_paths.append(output_path)

    return written_paths