from __future__ import annotations

from pathlib import Path
from typing import Any

from .real_reference_analysis import RealReferenceAnalyzer


class ReferenceAnalyzer:
    def __init__(
        self,
        provider: str = "real",
        device: str = "cuda",
        strict_real: bool = True,
        providers: Any | None = None,
        enable_detector: bool | None = None,
    ) -> None:
        self.impl = RealReferenceAnalyzer(
            providers=providers,
            provider=provider,
            device=device,
            strict_real=strict_real,
            enable_detector=enable_detector,
        )

    def analyze(self, image_path: str | Path, prompt: str | None = None) -> dict[str, Any]:
        raise NotImplementedError("Single-image analysis now runs through analyze_pack so artifacts and provider contracts stay consistent.")

    def analyze_pack(
        self,
        pack_dir: str | Path,
        negative_prompt: str = "low quality, bad anatomy, blurry, watermark, text",
        *,
        skip_existing: bool = False,
        max_assets: int | None = None,
        rel_path_filter: str | None = None,
    ) -> dict[str, Any]:
        return self.impl.analyze_pack(
            pack_dir,
            negative_prompt=negative_prompt,
            skip_existing=skip_existing,
            max_assets=max_assets,
            rel_path_filter=rel_path_filter,
        )
