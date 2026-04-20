from __future__ import annotations

from pathlib import Path

from PIL import Image

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def resize_with_padding(
    image: Image.Image,
    target_width: int,
    target_height: int,
    background_color: tuple[int, int, int] = (0, 0, 0),
) -> Image.Image:
    src_width, src_height = image.size
    scale = min(target_width / src_width, target_height / src_height)

    new_width = max(1, int(src_width * scale))
    new_height = max(1, int(src_height * scale))

    resized = image.resize((new_width, new_height), Image.LANCZOS)

    canvas = Image.new("RGB", (target_width, target_height), background_color)
    offset_x = (target_width - new_width) // 2
    offset_y = (target_height - new_height) // 2
    canvas.paste(resized.convert("RGB"), (offset_x, offset_y))
    return canvas


def resize_image_file(
    input_path: str | Path,
    output_path: str | Path,
    target_width: int,
    target_height: int,
    background_color: tuple[int, int, int] = (0, 0, 0),
) -> None:
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(input_path) as image:
        out = resize_with_padding(
            image=image,
            target_width=target_width,
            target_height=target_height,
            background_color=background_color,
        )
        out.save(output_path)


def batch_resize_and_pad(
    input_dir: str | Path,
    output_dir: str | Path,
    target_width: int,
    target_height: int,
    background_color: tuple[int, int, int] = (0, 0, 0),
) -> list[Path]:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written_paths: list[Path] = []

    for input_path in sorted(input_dir.rglob("*")):
        if not input_path.is_file() or input_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        output_path = output_dir / input_path.name
        resize_image_file(
            input_path=input_path,
            output_path=output_path,
            target_width=target_width,
            target_height=target_height,
            background_color=background_color,
        )
        written_paths.append(output_path)

    return written_paths