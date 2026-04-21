from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORT_MAP = {
    "compute_aesthetic_features": ("aesthetic_score", "compute_aesthetic_features"),
    "score_single_image_aesthetics": (
        "aesthetic_score",
        "score_single_image_aesthetics",
    ),
    "score_directory_aesthetics": ("aesthetic_score", "score_directory_aesthetics"),
    "pairwise_histogram_consistency": (
        "consistency_score",
        "pairwise_histogram_consistency",
    ),
    "directory_consistency_report": (
        "consistency_score",
        "directory_consistency_report",
    ),
    "build_markdown_report": ("report_builder", "build_markdown_report"),
    "save_markdown_report": ("report_builder", "save_markdown_report"),
}

__all__ = list(_EXPORT_MAP.keys())


def __getattr__(name: str) -> Any:
    if name not in _EXPORT_MAP:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(f".{module_name}", __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
