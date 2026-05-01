from __future__ import annotations

import time
from typing import Any

from .base import ProviderContext, provider_payload


class SkipTaggerProvider:
    """Real-mode tagger bypass: emits empty tags (not mock) when WD14 weights are absent or intentionally disabled."""

    provider_name = "TaggerSkipped"

    def __init__(self, context: ProviderContext | None = None, reason: str | None = None) -> None:
        self.context = context or ProviderContext()
        self.reason = reason or "tagger disabled via analysis_profiles (tagger.provider: none)"

    def tag(self, image_path: str) -> dict[str, Any]:
        start = time.perf_counter()
        payload = provider_payload(
            mock=False,
            provider_name=self.provider_name,
            model_path="",
            device=self.context.device,
            start=start,
            results={"tags": []},
            tags=[],
            general_tags=[],
            character_tags=[],
            rating_tags=[],
            warnings=[self.reason],
        )
        payload["skipped_for"] = str(image_path)
        return payload

    def unload_from_device(self) -> None:
        return
