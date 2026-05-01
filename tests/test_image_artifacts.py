import numpy as np
from PIL import Image

from aigc2d.image_artifacts import apply_mask_to_alpha, crop_by_mask, make_canny, make_lineart_basic, resize_square_1024, save_mask, validate_mask_area


def test_image_artifacts_create_real_outputs(tmp_path):
    image = tmp_path / "image.png"
    Image.new("RGB", (64, 48), "white").save(image)
    mask = np.zeros((48, 64), dtype=np.uint8)
    mask[10:40, 20:50] = 255
    mask_path = save_mask(mask, tmp_path / "mask.png")

    alpha = apply_mask_to_alpha(image, mask_path, tmp_path / "alpha.png")
    crop = crop_by_mask(image, mask_path, tmp_path / "crop.png")
    square = resize_square_1024(crop, tmp_path / "square.png", size=128)
    canny = make_canny(image, tmp_path / "canny.png")
    lineart = make_lineart_basic(image, tmp_path / "lineart.png")
    check = validate_mask_area(mask_path)

    assert alpha.exists()
    assert crop.exists()
    assert Image.open(square).size == (128, 128)
    assert canny.exists()
    assert lineart.exists()
    assert check["area_ratio"] > 0
