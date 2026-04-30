from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import load_yaml


@dataclass
class GenerationConfig:
    name: str
    task_type: str
    workflow: str
    model_profile: str
    vae_profile: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 28
    cfg: float = 5.0
    sampler: str = "euler"
    scheduler: str = "normal"
    denoise: float = 1.0
    seed_policy: str = "fixed"
    seed: int = 42
    output_subdir: str = "default"
    prompt_preset: str = "wallpaper_firefly"
    negative_preset: str = "anime_default"
    reference_image: str = ""
    upscale_model: str = ""
    enable_ipadapter: bool = False
    enable_controlnet: bool = False
    enable_lora: bool = False
    controlnet_profile: str = ""
    ipadapter_profile: str = ""
    lora_profiles: list[str] = field(default_factory=list)
    lora_weights: dict[str, float] = field(default_factory=dict)
    lora_trigger_words: dict[str, list[str]] = field(default_factory=dict)
    lora_apply_order: list[str] = field(default_factory=list)
    segmentation_profile: str = "sam3_1"
    detector_profile: str = "mock_detector"
    vlm_profile: str = "mock_vlm"
    tagger_profile: str = "mock_tagger"
    scoring_profile: str = "wallpaper_default"
    base_resolution: list[int] = field(default_factory=lambda: [1536, 864])
    upscale_ratio: float = 2.5
    final_target_resolution: list[int] = field(default_factory=lambda: [3840, 2160])
    comfy_url: str = "http://127.0.0.1:8188"
    extra: dict[str, Any] = field(default_factory=dict)


def load_generation_config(path: str | Path) -> GenerationConfig:
    data = load_yaml(path)
    known = GenerationConfig.__dataclass_fields__
    payload = {key: value for key, value in data.items() if key in known}
    extra = {key: value for key, value in data.items() if key not in known}
    config = GenerationConfig(**payload)
    config.extra = extra
    return config


def apply_overrides(config: GenerationConfig, *overrides: dict[str, Any] | None) -> GenerationConfig:
    data = {key: getattr(config, key) for key in GenerationConfig.__dataclass_fields__ if key != "extra"}
    extra = dict(config.extra)
    for override in overrides:
        if not override:
            continue
        for key, value in override.items():
            if value in (None, ""):
                continue
            if key in data:
                data[key] = value
            else:
                extra[key] = value
    updated = GenerationConfig(**data)
    updated.extra = extra
    return updated
