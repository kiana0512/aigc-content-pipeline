from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from PIL import Image

from .base import ProviderContext, ProviderError, provider_payload, require_path


class GroundingDINOProvider:
    provider_name = "GroundingDINO"

    def __init__(
        self,
        model_root: str | Path = "weights/detector/GroundingDINO",
        config_file: str = "configuration.json",
        checkpoint_file: str = "groundingdino_swinT_ogc.pth",
        box_threshold: float = 0.30,
        text_threshold: float = 0.25,
        context: ProviderContext | None = None,
    ) -> None:
        self.context = context or ProviderContext()
        self.model_root = require_path(self.provider_name, model_root)
        self.config_path = require_path(self.provider_name, self.model_root / config_file, "config_file")
        self.checkpoint_path = require_path(self.provider_name, self.model_root / checkpoint_file, "checkpoint_file")
        self.box_threshold = box_threshold
        self.text_threshold = text_threshold
        self._model: Any = None

    def detect(self, image_path: str, prompts: list[str]) -> dict[str, Any]:
        start = time.perf_counter()
        self._ensure_loaded()
        image = Image.open(image_path).convert("RGB")
        detections = self._predict(image_path, prompts)
        if not detections:
            raise ProviderError(self.provider_name, f"no detections returned for {image_path}")
        return provider_payload(
            mock=False,
            provider_name=self.provider_name,
            model_path=self.model_root,
            device=self.context.device,
            start=start,
            results={"detections": detections},
            image_path=str(image_path),
            detections=detections,
            image_size=list(image.size),
        )

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from groundingdino.util.inference import load_model
        except Exception as exc:
            raise ProviderError(
                self.provider_name,
                "GroundingDINO python package is not importable. Install the local GroundingDINO code/package; "
                f"model files are expected under {self.model_root}. Original error: {exc}",
            ) from exc
        try:
            self._model = load_model(str(self.config_path), str(self.checkpoint_path), device=self.context.device)
        except Exception as exc:
            raise ProviderError(self.provider_name, f"failed to load model from {self.model_root}: {exc}") from exc

    def _predict(self, image_path: str, prompts: list[str]) -> list[dict[str, Any]]:
        try:
            from groundingdino.util.inference import load_image, predict
        except Exception as exc:
            raise ProviderError(self.provider_name, f"missing inference dependencies: {exc}") from exc
        try:
            image_source, image = load_image(str(image_path))
            caption = " . ".join(prompts)
            boxes, logits, phrases = predict(
                model=self._model,
                image=image,
                caption=caption,
                box_threshold=self.box_threshold,
                text_threshold=self.text_threshold,
                device=self.context.device,
            )
        except Exception as exc:
            raise ProviderError(self.provider_name, f"inference failed for {image_path}: {exc}") from exc
        height, width = image_source.shape[:2]
        detections: list[dict[str, Any]] = []
        for box, score, phrase in zip(boxes, logits, phrases, strict=False):
            cx, cy, bw, bh = [float(v) for v in box.tolist()]
            x1 = max(0.0, (cx - bw / 2) * width)
            y1 = max(0.0, (cy - bh / 2) * height)
            x2 = min(float(width), (cx + bw / 2) * width)
            y2 = min(float(height), (cy + bh / 2) * height)
            detections.append(
                {
                    "label": str(phrase),
                    "box_xyxy": [x1, y1, x2, y2],
                    "score": float(score.item() if hasattr(score, "item") else score),
                    "text_score": float(score.item() if hasattr(score, "item") else score),
                }
            )
        return detections


def detection_prompts_for_role(role: str) -> list[str]:
    if role in {"init", "raw", "identity"}:
        return ["anime girl", "person", "face", "head", "hair", "upper body", "outfit", "dress", "mechanical armor", "weapon"]
    if role == "mecha":
        return ["mechanical armor", "mecha", "weapon", "sci-fi equipment", "metal parts"]
    if role == "face":
        return ["face", "eyes", "hair", "head"]
    return ["person", "main subject", "background", "sky", "building", "weapon", "action pose"]
