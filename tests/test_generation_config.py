from aigc2d.generation_config import load_generation_config
from aigc2d.model_profiles import ModelProfileResolver


def test_load_generation_config():
    config = load_generation_config("configs/generation/firefly_wallpaper.yaml")
    assert config.task_type == "img2img_ipadapter_controlnet"
    assert config.enable_ipadapter is True
    assert config.final_target_resolution == [3840, 2160]


def test_model_profile_resolver():
    models = ModelProfileResolver().resolve(
        model_profile="animagine_xl",
        vae_profile="sdxl_vae",
        controlnet_profile="lineart_sdxl",
        ipadapter_profile="plus_sdxl",
        upscale_model="ultrasharp_4x",
        segmentation_profile="sam3_1",
        vlm_profile="mock_vlm",
        tagger_profile="mock_tagger",
        lora_profiles=["firefly_identity_reserved"],
        lora_weights={"firefly_identity_reserved": 0.8},
    )
    assert models.checkpoint
    assert models.vae
    assert models.controlnet
    assert models.ipadapter
    assert models.upscaler
    assert models.segmentation
    assert models.vlm
    assert models.tagger
    assert models.loras[0]["weight"] == 0.8
    assert models.storage_roots["python_weights_root"].startswith("F:/")
