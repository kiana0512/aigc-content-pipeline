from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, load_yaml


@dataclass
class ResolvedModels:
    checkpoint: str = ""
    vae: str = ""
    segmentation: str = ""
    detector: str = ""
    vlm: str = ""
    tagger: str = ""
    clip_vision: str = ""
    ipadapter: str = ""
    controlnet: str = ""
    upscaler: str = ""
    loras: list[dict[str, Any]] = field(default_factory=list)
    video_model: str = ""
    storage_roots: dict[str, str] = field(default_factory=dict)


def _load_all_model_yaml(config_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(config_dir) if config_dir else PROJECT_ROOT / "configs" / "models"
    merged: dict[str, Any] = {}
    if root.is_file():
        return load_yaml(root)
    if not root.exists():
        root = PROJECT_ROOT / "configs"
    for path in sorted(root.rglob("*.yaml")):
        data = load_yaml(path)
        for key, value in data.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
    return merged


class ModelProfileResolver:
    def __init__(self, config_dir: str | Path | None = None) -> None:
        self.data = _load_all_model_yaml(config_dir)
        self.storage_roots = self.data.get("storage_roots", {})

    def resolve_path(self, profile: dict[str, Any], path_field: str = "relative_path") -> str:
        root_key = profile.get("root_key", "")
        relative = profile.get(path_field, "") or profile.get("path", "")
        if not relative:
            return profile.get("local_name", "") or profile.get("name", "")
        root = self.storage_roots.get(root_key, "")
        return str(Path(root) / relative) if root else str(relative)

    def get_profile(self, section: str, name: str) -> dict[str, Any]:
        if not name:
            return {}
        profiles = self.data.get(section, {})
        if name not in profiles:
            raise KeyError(f"Unknown model profile: {section}.{name}")
        return profiles[name] or {}

    def resolve(
        self,
        model_profile: str,
        vae_profile: str = "",
        controlnet_profile: str = "",
        ipadapter_profile: str = "",
        upscale_model: str = "",
        segmentation_profile: str = "",
        detector_profile: str = "",
        vlm_profile: str = "",
        tagger_profile: str = "",
        lora_profiles: list[str] | None = None,
        lora_weights: dict[str, float] | None = None,
        lora_trigger_words: dict[str, list[str]] | None = None,
    ) -> ResolvedModels:
        model = self.get_profile("checkpoints", model_profile) or self.get_profile("models", model_profile)
        vae = self.get_profile("vae", vae_profile) if vae_profile else {}
        controlnet = self.get_profile("controlnet", controlnet_profile) if controlnet_profile else {}
        ipadapter = self.get_profile("ipadapter", ipadapter_profile) if ipadapter_profile else {}
        upscaler = self.get_profile("upscalers", upscale_model) if upscale_model else {}
        segmentation = self.get_profile("segmentation", segmentation_profile) if segmentation_profile else {}
        detector = self.get_profile("detectors", detector_profile) if detector_profile else {}
        vlm = self.get_profile("vlm", vlm_profile) if vlm_profile else {}
        tagger = self.get_profile("tagger", tagger_profile) if tagger_profile else {}
        loras = []
        for name in lora_profiles or []:
            profile = self.get_profile("lora", name)
            loras.append(
                {
                    "profile": name,
                    "path": self.resolve_path(profile),
                    "weight": (lora_weights or {}).get(name, profile.get("weight", 1.0)),
                    "trigger_words": (lora_trigger_words or {}).get(name, profile.get("trigger_words", [])),
                }
            )
        return ResolvedModels(
            checkpoint=model.get("checkpoint") or self.resolve_path(model) or model.get("local_name") or "",
            vae=vae.get("vae") or self.resolve_path(vae) or model.get("vae") or "",
            segmentation=self.resolve_path(segmentation),
            detector=self.resolve_path(detector),
            vlm=self.resolve_path(vlm),
            tagger=self.resolve_path(tagger),
            clip_vision=ipadapter.get("clip_vision") or ipadapter.get("clip_vision_name") or "",
            ipadapter=ipadapter.get("ipadapter") or self.resolve_path(ipadapter) or ipadapter.get("name") or "",
            controlnet=controlnet.get("controlnet") or self.resolve_path(controlnet) or controlnet.get("name") or "",
            upscaler=upscaler.get("upscaler") or self.resolve_path(upscaler) or upscaler.get("name") or "",
            loras=loras or model.get("loras", []),
            video_model=model.get("video_model", ""),
            storage_roots=dict(self.storage_roots),
        )
