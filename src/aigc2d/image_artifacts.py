from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageOps


def load_image_rgb(path: str | Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def save_mask(mask: Any, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    array = np.asarray(mask)
    if array.dtype != np.uint8:
        array = (array > 0).astype(np.uint8) * 255
    Image.fromarray(array).convert("L").save(target)
    return target


def apply_mask_to_alpha(image_path: str | Path, mask_path: str | Path, output_path: str | Path) -> Path:
    image = Image.open(image_path).convert("RGBA")
    mask = Image.open(mask_path).convert("L").resize(image.size)
    image.putalpha(mask)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return target


def mask_bbox(mask_path: str | Path) -> tuple[int, int, int, int]:
    mask = np.asarray(Image.open(mask_path).convert("L"))
    ys, xs = np.where(mask > 0)
    if len(xs) == 0 or len(ys) == 0:
        raise ValueError(f"Mask has no foreground pixels: {mask_path}")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def crop_by_mask(image_path: str | Path, mask_path: str | Path, output_path: str | Path, pad_ratio: float = 0.0) -> Path:
    image = load_image_rgb(image_path)
    box = _pad_box(mask_bbox(mask_path), image.size, pad_ratio)
    return _save_crop(image, box, output_path)


def crop_by_box(image_path: str | Path, box_xyxy: list[float] | tuple[float, float, float, float], output_path: str | Path, pad_ratio: float = 0.0) -> Path:
    image = load_image_rgb(image_path)
    box = tuple(int(round(v)) for v in box_xyxy)
    return _save_crop(image, _pad_box(box, image.size, pad_ratio), output_path)


def pad_to_square(image: Image.Image, fill: tuple[int, int, int] = (0, 0, 0)) -> Image.Image:
    width, height = image.size
    size = max(width, height)
    output = Image.new(image.mode, (size, size), fill)
    output.paste(image, ((size - width) // 2, (size - height) // 2))
    return output


def resize_square_1024(image_path: str | Path, output_path: str | Path, size: int = 1024) -> Path:
    image = load_image_rgb(image_path)
    output = pad_to_square(image).resize((size, size), Image.Resampling.LANCZOS)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    output.save(target)
    return target


def make_halfbody_crop(image_path: str | Path, subject_box: list[float] | tuple[float, float, float, float], output_path: str | Path) -> Path:
    x1, y1, x2, y2 = [int(round(v)) for v in subject_box]
    half_box = (x1, y1, x2, y1 + max(1, int((y2 - y1) * 0.62)))
    return crop_by_box(image_path, half_box, output_path, pad_ratio=0.08)


def make_face_crop(image_path: str | Path, face_box: list[float] | tuple[float, float, float, float], output_path: str | Path) -> Path:
    return crop_by_box(image_path, face_box, output_path, pad_ratio=0.35)


def make_halfbody_crop_from_mask(image_path: str | Path, mask_path: str | Path, output_path: str | Path) -> Path:
    x1, y1, x2, y2 = mask_bbox(mask_path)
    height = y2 - y1
    box = (x1, y1, x2, y1 + max(1, int(height * 0.70)))
    return crop_by_box(image_path, box, output_path, pad_ratio=0.08)


def make_face_crop_from_mask_heuristic(
    image_path: str | Path,
    mask_path: str | Path,
    output_path: str | Path,
    min_subject_size: int = 64,
) -> Path | None:
    x1, y1, x2, y2 = mask_bbox(mask_path)
    width = x2 - x1
    height = y2 - y1
    if width < min_subject_size or height < min_subject_size:
        return None
    face_width = int(width * 0.58)
    face_height = int(height * 0.38)
    center_x = x1 + width // 2
    face_x1 = center_x - face_width // 2
    face_x2 = center_x + face_width // 2
    face_y1 = y1 + int(height * 0.04)
    face_y2 = face_y1 + face_height
    return crop_by_box(image_path, (face_x1, face_y1, face_x2, face_y2), output_path, pad_ratio=0.12)


def make_canny(image_path: str | Path, output_path: str | Path, low: int = 80, high: int = 160) -> Path:
    cv2 = _try_import_cv2()
    if cv2 is not None:
        image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"Cannot read image for Canny: {image_path}")
        edges = cv2.Canny(image, low, high)
        return save_mask(edges, output_path)
    image = Image.open(image_path).convert("L")
    edges = ImageOps.autocontrast(image.filter(ImageFilter.FIND_EDGES))
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    edges.save(target)
    return target


def make_lineart_basic(image_path: str | Path, output_path: str | Path) -> Path:
    image = Image.open(image_path).convert("L")
    edges = image.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.autocontrast(edges)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    edges.save(target)
    return target


def make_depth_if_available(image_path: str | Path, output_path: str | Path) -> Path | None:
    return None


def validate_mask_area(mask_path: str | Path, min_ratio: float = 0.03, max_ratio: float = 0.90) -> dict[str, Any]:
    mask = np.asarray(Image.open(mask_path).convert("L"))
    area_ratio = float((mask > 0).sum() / mask.size)
    warnings: list[str] = []
    errors: list[str] = []
    if area_ratio <= 0:
        errors.append("mask area is zero")
    if area_ratio < min_ratio:
        warnings.append(f"mask area ratio too small: {area_ratio:.4f}")
    if area_ratio > max_ratio:
        warnings.append(f"mask area ratio too large: {area_ratio:.4f}")
    return {"area_ratio": area_ratio, "warnings": warnings, "errors": errors}


def _save_crop(image: Image.Image, box: tuple[int, int, int, int], output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.crop(box).save(target)
    return target


def _pad_box(box: tuple[int, int, int, int], image_size: tuple[int, int], pad_ratio: float) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    width, height = x2 - x1, y2 - y1
    pad = int(max(width, height) * pad_ratio)
    image_width, image_height = image_size
    return max(0, x1 - pad), max(0, y1 - pad), min(image_width, x2 + pad), min(image_height, y2 + pad)


def _try_import_cv2() -> Any:
    try:
        import cv2
    except Exception:
        return None
    return cv2
