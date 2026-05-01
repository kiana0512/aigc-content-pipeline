from __future__ import annotations

import gc
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ..image_artifacts import apply_mask_to_alpha, save_mask, validate_mask_area
from .base import ProviderContext, ProviderError, provider_payload, require_path


class BiRefNetProvider:
    provider_name = "BiRefNet"

    def __init__(
        self,
        model_root: str | Path = "weights/segmentation/BiRefNet",
        context: ProviderContext | None = None,
        output_dir: str | Path | None = None,
    ) -> None:
        self.context = context or ProviderContext()
        self.model_root = require_path(self.provider_name, model_root)
        self.output_dir = Path(output_dir) if output_dir else None
        self._pipeline: Any = None

    def remove_background(self, image_path: str) -> dict[str, Any]:
        start = time.perf_counter()
        self._ensure_loaded()
        output_dir = self.output_dir or Path(image_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        mask_path = output_dir / "birefnet_mask.png"
        alpha_path = output_dir / "birefnet_alpha.png"
        mask = self._predict_mask(image_path)
        save_mask(mask, mask_path)
        check = validate_mask_area(mask_path)
        if check["errors"]:
            raise ProviderError(self.provider_name, f"matting mask invalid: {check['errors']}")
        apply_mask_to_alpha(image_path, mask_path, alpha_path)
        return provider_payload(
            mock=False,
            provider_name=self.provider_name,
            model_path=self.model_root,
            device=self.context.device,
            start=start,
            results={"alpha_path": str(alpha_path), "mask_path": str(mask_path), "area_ratio": check["area_ratio"]},
            alpha_path=str(alpha_path),
            mask_path=str(mask_path),
            warnings=check["warnings"],
        )

    def _ensure_loaded(self) -> None:
        if self._pipeline is not None:
            return
        try:
            from transformers import AutoModelForImageSegmentation
            import torch
        except Exception as exc:
            raise ProviderError(self.provider_name, f"missing dependency transformers/torch: {exc}") from exc
        try:
            model = AutoModelForImageSegmentation.from_pretrained(
                str(self.model_root),
                trust_remote_code=True,
                local_files_only=True,
            )
            model.to(self.context.device)
            model.eval()
            self._pipeline = (model, torch)
        except Exception as exc:
            raise ProviderError(self.provider_name, f"failed to load BiRefNet from {self.model_root}: {exc}") from exc

    def _predict_mask(self, image_path: str) -> np.ndarray:
        model, torch = self._pipeline
        try:
            from torchvision import transforms
        except Exception as exc:
            raise ProviderError(self.provider_name, f"missing torchvision transforms: {exc}") from exc
        image = Image.open(image_path).convert("RGB")
        original_size = image.size
        transform = transforms.Compose(
            [
                transforms.Resize((1024, 1024)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )
        tensor = transform(image).unsqueeze(0).to(self.context.device)
        param_dtype = next(model.parameters()).dtype
        tensor = tensor.to(dtype=param_dtype)
        try:
            with torch.no_grad():
                output = model(tensor)
            pred = output[-1].sigmoid().cpu()[0, 0].numpy() if isinstance(output, (list, tuple)) else output.sigmoid().cpu()[0, 0].numpy()
        except Exception as exc:
            raise ProviderError(self.provider_name, f"inference failed for {image_path}: {exc}") from exc
        mask = Image.fromarray((pred * 255).astype(np.uint8)).resize(original_size, Image.Resampling.BILINEAR)
        return np.asarray(mask)

    def unload_from_device(self) -> None:
        """Free GPU memory; next remove_background will reload from disk."""
        if self._pipeline is None:
            return
        model, torch_mod = self._pipeline
        self._pipeline = None
        try:
            del model
        except Exception:
            pass
        gc.collect()
        try:
            if self.context.device == "cuda" and torch_mod is not None and hasattr(torch_mod.cuda, "empty_cache"):
                torch_mod.cuda.empty_cache()
        except Exception:
            pass
