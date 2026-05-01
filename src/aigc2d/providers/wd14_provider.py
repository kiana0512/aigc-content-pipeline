from __future__ import annotations

import csv
import gc
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .base import ProviderContext, ProviderError, provider_payload, require_path


def _find_wd_onnx(root: Path) -> Path | None:
    preferred = ("model.onnx", "wd14.onnx", "wd14-tag.onnx")
    for name in preferred:
        cand = root / name
        if cand.is_file():
            return cand
        nested = sorted(root.rglob(name))
        if nested:
            return nested[0]
    root_onnx = sorted(root.glob("*.onnx"))
    if root_onnx:
        return root_onnx[0]
    all_onnx = sorted(root.rglob("*.onnx"))
    return all_onnx[0] if all_onnx else None


def _tag_csv_sort_key(path: Path) -> tuple[int, int, str]:
    """Prefer SmilingWolf-style tag tables; deprioritize training/inventory CSVs in the same tree."""
    name = path.name.lower()
    depth = len(path.parts)
    if name == "tags_info.csv":
        return (0, depth, str(path))
    if name in ("tags.csv", "selected_tags.csv", "tag_list.csv", "labels.csv"):
        return (1, depth, str(path))
    if "tag" in name and "experiment" not in name:
        return (2, depth, str(path))
    if name.startswith("inv_") or "experiment" in name:
        return (9, depth, str(path))
    return (5, depth, str(path))


def _find_wd_tags_csv(root: Path) -> Path | None:
    preferred = ("tags_info.csv", "tags.csv", "selected_tags.csv", "tag_list.csv", "labels.csv")
    for name in preferred:
        cand = root / name
        if cand.is_file():
            return cand
    for name in preferred:
        nested = sorted(root.rglob(name))
        if nested:
            return nested[0]
    root_csv = sorted(root.glob("*.csv"), key=_tag_csv_sort_key)
    if root_csv:
        return root_csv[0]
    all_csv = sorted(root.rglob("*.csv"), key=_tag_csv_sort_key)
    return all_csv[0] if all_csv else None


class WD14TaggerProvider:
    provider_name = "WD14Tagger"

    def __init__(
        self,
        model_root: str | Path = "weights/tagger/wd14_tagger_with_embeddings",
        general_threshold: float = 0.35,
        character_threshold: float = 0.50,
        context: ProviderContext | None = None,
        force_cpu_providers: bool = False,
    ) -> None:
        self.context = context or ProviderContext()
        self.model_root = require_path(self.provider_name, model_root)
        self.general_threshold = general_threshold
        self.character_threshold = character_threshold
        self.force_cpu_providers = bool(force_cpu_providers)
        self._session: Any = None
        self._tags: list[dict[str, str]] = []

    def tag(self, image_path: str) -> dict[str, Any]:
        start = time.perf_counter()
        self._ensure_loaded()
        probabilities = self._predict(image_path)
        tags, general_tags, character_tags, rating_tags = self._format_tags(probabilities)
        if not tags:
            raise ProviderError(self.provider_name, f"no tags above threshold for {image_path}")
        return provider_payload(
            mock=False,
            provider_name=self.provider_name,
            model_path=self.model_root,
            device=self.context.device,
            start=start,
            results={"tags": tags},
            tags=tags,
            general_tags=general_tags,
            character_tags=character_tags,
            rating_tags=rating_tags,
        )

    def _ensure_loaded(self) -> None:
        if self._session is not None:
            return
        try:
            import onnxruntime as ort
        except Exception as exc:
            raise ProviderError(self.provider_name, f"missing dependency onnxruntime: {exc}") from exc
        model_path = _find_wd_onnx(self.model_root)
        tag_path = _find_wd_tags_csv(self.model_root)
        if model_path is None or tag_path is None:
            raise ProviderError(
                self.provider_name,
                f"missing WD14 ONNX (.onnx) or tag CSV in {self.model_root} (searched recursively). "
                "Place a WD Tagger export there (for example ONNX + CSV from Hugging Face WD tagger releases), "
                "or set tagger.provider to none in configs/models/analysis_profiles.yaml to skip tagging in strict_real.",
            )
        if self.force_cpu_providers:
            providers = ["CPUExecutionProvider"]
        else:
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if self.context.device == "cuda" else ["CPUExecutionProvider"]
        try:
            self._session = ort.InferenceSession(str(model_path), providers=providers)
            self._tags = self._read_tags(tag_path)
        except Exception as exc:
            raise ProviderError(self.provider_name, f"failed to load WD14 model from {self.model_root}: {exc}") from exc

    def _predict(self, image_path: str) -> np.ndarray:
        image = Image.open(image_path).convert("RGB")
        input_meta = self._session.get_inputs()[0]
        _, height, width, _ = input_meta.shape
        size = int(height or 448)
        image = image.resize((size, size), Image.Resampling.LANCZOS)
        array = np.asarray(image).astype(np.float32)
        array = array[:, :, ::-1]
        array = np.expand_dims(array, 0)
        try:
            output = self._session.run(None, {input_meta.name: array})[0][0]
        except Exception as exc:
            raise ProviderError(self.provider_name, f"inference failed for {image_path}: {exc}") from exc
        return output

    def _format_tags(self, probabilities: np.ndarray) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        general: list[dict[str, Any]] = []
        character: list[dict[str, Any]] = []
        rating: list[dict[str, Any]] = []
        for index, meta in enumerate(self._tags[: len(probabilities)]):
            score = float(probabilities[index])
            category = meta.get("category", "")
            item = {"tag": meta["name"], "score": score}
            if category == "9":
                rating.append(item)
            elif category == "4":
                if score >= self.character_threshold:
                    character.append(item)
            elif score >= self.general_threshold:
                general.append(item)
        key = lambda item: item["score"]
        general.sort(key=key, reverse=True)
        character.sort(key=key, reverse=True)
        rating.sort(key=key, reverse=True)
        return [*general, *character], general, character, rating

    def _read_tags(self, path: Path) -> list[dict[str, str]]:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            raise ProviderError(self.provider_name, f"empty tag csv: {path}")
        return [{"name": row.get("name") or row.get("tag") or "", "category": str(row.get("category", ""))} for row in rows]

    def unload_from_device(self) -> None:
        """Drop ONNX session so VRAM can be reclaimed before loading VLM."""
        self._session = None
        gc.collect()
        try:
            import torch

            if self.context.device == "cuda":
                torch.cuda.empty_cache()
        except Exception:
            pass
