from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import PROJECT_ROOT, load_yaml
from ..tagger import MockTaggerProvider as LegacyMockTaggerProvider
from ..vlm import MockVLMProvider as LegacyMockVLMProvider
from .base import ProviderContext, ProviderError, provider_payload
from .birefnet_provider import BiRefNetProvider
from .grounding_dino_provider import GroundingDINOProvider
from .sam_provider import ExternalSam3Provider
from .skip_tagger_provider import SkipTaggerProvider
from .vlm_provider import LocalVLMProvider
from .wd14_provider import WD14TaggerProvider


@dataclass
class AnalysisProviders:
    segmentation: Any
    matting: Any
    tagger: Any
    vlm: Any
    provider: str
    device: str
    strict_real: bool
    detector: Any | None = None
    enable_detector: bool = False


def create_analysis_providers(
    provider: str = "real",
    device: str = "cuda",
    strict_real: bool = True,
    config_path: str | Path = PROJECT_ROOT / "configs" / "models" / "analysis_profiles.yaml",
    enable_detector: bool | None = None,
) -> AnalysisProviders:
    config = load_yaml(config_path)
    if provider == "mock":
        return AnalysisProviders(
            segmentation=MockSegmentationProvider(device=device),
            matting=MockMattingProvider(device=device),
            tagger=MockTaggerAdapter(device=device),
            vlm=MockVLMAdapter(device=device),
            provider="mock",
            device=device,
            strict_real=False,
            detector=MockDetectionProvider(device=device) if enable_detector else None,
            enable_detector=bool(enable_detector),
        )
    if provider != "real":
        raise ValueError(f"Unsupported analysis provider: {provider}")
    context = ProviderContext(device=device, strict_real=strict_real)
    detector_enabled = bool(_cfg(config, "analysis", "enable_detector", False) if enable_detector is None else enable_detector)
    try:
        segmentation = _create_segmentation_provider(
            config=config,
            device=device,
            strict_real=strict_real,
            min_mask_area_ratio=float(_cfg(config, "image_artifacts", "min_mask_area_ratio", 0.03)),
            max_mask_area_ratio=float(_cfg(config, "image_artifacts", "max_mask_area_ratio", 0.90)),
        )
        matting = BiRefNetProvider(
            model_root=_project_path(_cfg(config, "matting", "model_root", "weights/segmentation/BiRefNet")),
            context=context,
        )
        tagger_choice = str(_cfg(config, "tagger", "provider", "wd14")).strip().lower()
        tagger_force_cpu = bool(_cfg(config, "analysis", "tagger_force_cpu", False))
        if tagger_choice in ("none", "disabled", "skip", "off"):
            tagger_impl: Any = SkipTaggerProvider(
                context=context,
                reason="tagger.provider is none/disabled/skip/off in configs/models/analysis_profiles.yaml",
            )
        else:
            tagger_impl = WD14TaggerProvider(
                model_root=_project_path(_cfg(config, "tagger", "model_root", "weights/tagger/wd14_tagger_with_embeddings")),
                general_threshold=float(_cfg(config, "tagger", "general_threshold", 0.35)),
                character_threshold=float(_cfg(config, "tagger", "character_threshold", 0.50)),
                context=context,
                force_cpu_providers=tagger_force_cpu,
            )
        return AnalysisProviders(
            segmentation=segmentation,
            matting=matting,
            tagger=tagger_impl,
            vlm=LocalVLMProvider(
                provider_name="Qwen2.5-VL-7B-Instruct" if _cfg(config, "vlm", "provider", "qwen2_5_vl") == "qwen2_5_vl" else "Florence-2",
                model_root=_project_path(_cfg(config, "vlm", "model_root", "weights/vlm/Qwen2.5-VL-7B-Instruct")),
                fallback_provider=str(_cfg(config, "vlm", "fallback_provider", "Florence-2-large-PromptGen-v2.0")),
                fallback_model_root=_project_path(_cfg(config, "vlm", "fallback_model_root", "weights/vlm/Florence-2-large-PromptGen-v2.0")),
                allow_fallback=bool(_cfg(config, "vlm", "allow_fallback", False)),
                max_new_tokens=int(_cfg(config, "vlm", "max_new_tokens", 512)),
                min_pixels=_cfg_optional_int(config, "vlm", "min_pixels"),
                max_pixels=_cfg_optional_int(config, "vlm", "max_pixels"),
                attn_implementation=str(_cfg(config, "vlm", "attn_implementation", "sdpa")),
                context=context,
            ),
            provider="real",
            device=device,
            strict_real=strict_real,
            detector=GroundingDINOProvider(
                model_root=_project_path(_cfg(config, "detector", "model_root", "weights/detector/GroundingDINO")),
                config_file=_cfg(config, "detector", "config_file", "configuration.json"),
                checkpoint_file=_cfg(config, "detector", "checkpoint_file", "groundingdino_swinT_ogc.pth"),
                box_threshold=float(_cfg(config, "detector", "box_threshold", 0.30)),
                text_threshold=float(_cfg(config, "detector", "text_threshold", 0.25)),
                context=context,
            )
            if detector_enabled
            else None,
            enable_detector=detector_enabled,
        )
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError("provider_factory", f"failed to initialize real providers: {exc}") from exc


def _cfg(config: dict[str, Any], section: str, key: str, default: Any) -> Any:
    return (config.get(section) or {}).get(key, default)


def _cfg_optional_int(config: dict[str, Any], section: str, key: str) -> int | None:
    raw = _cfg(config, section, key, None)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _create_segmentation_provider(
    config: dict[str, Any],
    device: str,
    strict_real: bool,
    min_mask_area_ratio: float,
    max_mask_area_ratio: float,
) -> Any:
    provider = str(_cfg(config, "segmentation", "provider", "external_sam3"))
    if provider in {"external_sam3", "sam3_1_external"}:
        prompts = _cfg(config, "segmentation", "prompts", ["person", "anime character", "main subject", "girl", "character"])
        return ExternalSam3Provider(
            conda_env=str(_cfg(config, "segmentation", "conda_env", "sam3")),
            python_exe=_cfg(config, "segmentation", "python_exe", None),
            cli_script=_cfg(config, "segmentation", "cli_script", "scripts/sam3_segment_cli.py"),
            sam3_repo_dir=_cfg(config, "segmentation", "sam3_repo_dir", ""),
            sam3_model_root=_cfg(config, "segmentation", "sam3_model_root", ""),
            sam3_config_path=_cfg(config, "segmentation", "sam3_config_path", ""),
            sam3_checkpoint_path=_cfg(config, "segmentation", "sam3_checkpoint_path", ""),
            offline=bool(_cfg(config, "segmentation", "offline", True)),
            device=str(_cfg(config, "segmentation", "device", device)),
            min_mask_area_ratio=float(_cfg(config, "segmentation", "min_mask_area_ratio", min_mask_area_ratio)),
            max_mask_area_ratio=float(_cfg(config, "segmentation", "max_mask_area_ratio", max_mask_area_ratio)),
            output_prob_thresh=float(_cfg(config, "segmentation", "output_prob_thresh", 0.2)),
            sam31_image_mode=bool(_cfg(config, "segmentation", "sam31_image_mode", True)),
            sam3_backend=str(_cfg(config, "segmentation", "sam3_backend", "auto")),
            timeout_sec=int(_cfg(config, "segmentation", "timeout_sec", 600)),
            strict_real=strict_real,
            prompts=[str(item) for item in prompts],
        )
    if provider in {"sam3_1_direct", "sam2"}:
        raise ProviderError(
            "provider_factory",
            f"segmentation.provider={provider} is not supported in the main llm environment. Use external_sam3.",
        )
    if provider == "birefnet_only":
        raise ProviderError("provider_factory", "birefnet_only segmentation is not implemented as a SAM replacement in strict-real mode.")
    raise ProviderError("provider_factory", f"Unknown segmentation provider: {provider}")


def _project_path(path: Any) -> Path:
    candidate = Path(str(path))
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


class MockDetectionProvider:
    provider_name = "MockDetectionProvider"

    def __init__(self, device: str = "cpu") -> None:
        self.device = device

    def detect(self, image_path: str, prompts: list[str]) -> dict[str, Any]:
        start = time.perf_counter()
        from PIL import Image

        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        detections = [
            {"label": "person", "box_xyxy": [width * 0.2, height * 0.05, width * 0.8, height * 0.95], "score": 0.9, "text_score": 0.9},
            {"label": "face", "box_xyxy": [width * 0.38, height * 0.08, width * 0.62, height * 0.32], "score": 0.8, "text_score": 0.8},
        ]
        return provider_payload(True, self.provider_name, "mock", self.device, start, {"detections": detections}, detections=detections)


class MockSegmentationProvider:
    provider_name = "MockSegmentationProvider"

    def __init__(self, device: str = "cpu") -> None:
        self.device = device

    def segment(self, image_path: str, out_dir: str | Path, prompts: list[str]) -> dict[str, Any]:
        start = time.perf_counter()
        from PIL import Image, ImageDraw

        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        mask = Image.new("L", image.size, 0)
        draw = ImageDraw.Draw(mask)
        box = [width * 0.2, height * 0.1, width * 0.8, height * 0.9]
        draw.rectangle([int(v) for v in box], fill=255)
        mask_path = Path(out_dir) / "subject_mask.png"
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        mask.save(mask_path)
        masks = {"subject": {"mask_path": str(mask_path), "area_ratio": 0.42, "source_mode": "auto_subject", "source_prompt": "main subject", "score": 0.9}}
        return provider_payload(True, self.provider_name, "mock", self.device, start, {"masks": masks}, masks=masks)


class MockMattingProvider:
    provider_name = "MockMattingProvider"

    def __init__(self, device: str = "cpu") -> None:
        self.device = device

    def remove_background(self, image_path: str) -> dict[str, Any]:
        start = time.perf_counter()
        return provider_payload(True, self.provider_name, "mock", self.device, start, {"alpha_path": ""}, alpha_path="")


class MockTaggerAdapter:
    provider_name = "MockTaggerProvider"

    def __init__(self, device: str = "cpu") -> None:
        self.device = device
        self.legacy = LegacyMockTaggerProvider()

    def tag(self, image_path: str) -> dict[str, Any]:
        start = time.perf_counter()
        tags = [{"tag": tag, "score": 1.0} for tag in self.legacy.tag(image_path)]
        return provider_payload(True, self.provider_name, "mock", self.device, start, {"tags": tags}, tags=tags, general_tags=tags, character_tags=[])


class MockVLMAdapter:
    provider_name = "MockVLMProvider"

    def __init__(self, device: str = "cpu") -> None:
        self.device = device
        self.legacy = LegacyMockVLMProvider()

    def describe(
        self,
        image_path: str,
        role: str = "raw",
        *,
        raw_reply_path: Path | None = None,
    ) -> dict[str, Any]:
        _ = raw_reply_path
        start = time.perf_counter()
        description = dict(self.legacy.structured_describe(image_path))
        description["appearance"] = {
            "hair": description.get("appearance", ""),
            "eyes": "",
            "face": "",
            "outfit": description.get("outfit", ""),
            "mecha": "",
        }
        description["warnings"] = ["mock provider"]
        return provider_payload(True, self.provider_name, "mock", self.device, start, description, **description)
