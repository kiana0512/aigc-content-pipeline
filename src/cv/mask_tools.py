from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def alpha_to_mask(image_bgra: np.ndarray, threshold: int = 1) -> np.ndarray:
    if image_bgra.shape[-1] < 4:
        raise ValueError("Input image does not contain an alpha channel.")
    alpha = image_bgra[:, :, 3]
    mask = np.where(alpha >= threshold, 255, 0).astype(np.uint8)
    return mask


def brightness_to_mask(
    image_bgr: np.ndarray,
    threshold: int = 240,
    invert: bool = False,
) -> np.ndarray:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    flag = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
    _, mask = cv2.threshold(gray, threshold, 255, flag)
    return mask


def process_mask_directory(
    input_dir: str | Path,
    output_dir: str | Path,
    mode: str = "brightness",
    threshold: int = 240,
    invert: bool = False,
) -> list[Path]:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written_paths: list[Path] = []

    for input_path in sorted(input_dir.rglob("*")):
        if not input_path.is_file() or input_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        if mode == "alpha":
            image = cv2.imread(str(input_path), cv2.IMREAD_UNCHANGED)
            if image is None:
                raise ValueError(f"Failed to read image: {input_path}")
            if image.ndim != 3 or image.shape[-1] < 4:
                raise ValueError(f"Alpha mode requires 4-channel image: {input_path}")
            mask = alpha_to_mask(image_bgra=image, threshold=threshold)
        else:
            image = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f"Failed to read image: {input_path}")
            mask = brightness_to_mask(
                image_bgr=image,
                threshold=threshold,
                invert=invert,
            )

        output_path = output_dir / f"{input_path.stem}_mask.png"
        success = cv2.imwrite(str(output_path), mask)
        if not success:
            raise IOError(f"Failed to write mask image: {output_path}")

        written_paths.append(output_path)

    return written_paths