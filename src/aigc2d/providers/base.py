from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class ProviderError(RuntimeError):
    def __init__(self, provider_name: str, message: str) -> None:
        super().__init__(f"{provider_name} provider failed: {message}")
        self.provider_name = provider_name


@dataclass
class ProviderContext:
    device: str = "cuda"
    strict_real: bool = True


class DetectionProvider(Protocol):
    def detect(self, image_path: str, prompts: list[str]) -> dict[str, Any]:
        ...


class SegmentationProvider(Protocol):
    def segment(self, image_path: str, boxes: list[dict[str, Any]], prompts: list[str]) -> dict[str, Any]:
        ...


class MattingProvider(Protocol):
    def remove_background(self, image_path: str) -> dict[str, Any]:
        ...


class TaggerProvider(Protocol):
    def tag(self, image_path: str) -> dict[str, Any]:
        ...


class VLMProvider(Protocol):
    def describe(
        self,
        image_path: str,
        role: str = "raw",
        *,
        raw_reply_path: Path | None = None,
    ) -> dict[str, Any]:
        ...


def require_path(provider_name: str, path: str | Path, kind: str = "model path") -> Path:
    candidate = Path(path)
    if not candidate.exists():
        raise ProviderError(provider_name, f"{kind} not found: {candidate}")
    return candidate


def require_import(provider_name: str, module_name: str) -> Any:
    try:
        return __import__(module_name)
    except Exception as exc:
        raise ProviderError(provider_name, f"missing dependency '{module_name}': {exc}") from exc


def runtime_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def provider_payload(
    mock: bool,
    provider_name: str,
    model_path: str | Path,
    device: str,
    start: float,
    results: Any,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "mock": mock,
        "provider_name": provider_name,
        "model_path": str(model_path),
        "device": device,
        "runtime_ms": runtime_ms(start),
        "results": results,
        "warnings": warnings or [],
        "errors": errors or [],
        **extra,
    }
