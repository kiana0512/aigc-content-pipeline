from PIL import Image

from src.cv.resize_pad import resize_with_padding


def test_resize_with_padding_returns_target_size() -> None:
    image = Image.new("RGB", (400, 200), (255, 0, 0))
    output = resize_with_padding(
        image=image,
        target_width=256,
        target_height=256,
    )
    assert output.size == (256, 256)


def test_resize_with_padding_keeps_image_mode_rgb() -> None:
    image = Image.new("RGB", (100, 300), (0, 255, 0))
    output = resize_with_padding(
        image=image,
        target_width=512,
        target_height=512,
    )
    assert output.mode == "RGB"


def test_resize_with_padding_applies_background_color() -> None:
    image = Image.new("RGB", (100, 100), (255, 255, 255))
    output = resize_with_padding(
        image=image,
        target_width=200,
        target_height=300,
        background_color=(10, 20, 30),
    )

    top_left_pixel = output.getpixel((0, 0))
    assert top_left_pixel == (10, 20, 30)