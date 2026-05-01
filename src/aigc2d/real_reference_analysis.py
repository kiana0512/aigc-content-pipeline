from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .config import load_json, load_yaml, write_json
from .image_artifacts import (
    apply_mask_to_alpha,
    crop_by_box,
    crop_by_mask,
    make_canny,
    make_depth_if_available,
    make_face_crop,
    make_face_crop_from_mask_heuristic,
    make_halfbody_crop,
    make_halfbody_crop_from_mask,
    make_lineart_basic,
    resize_square_1024,
    validate_mask_area,
)
from .prompt_bundle import build_prompt_bundle, save_prompt_bundle
from .providers import AnalysisProviders, ProviderError, create_analysis_providers
from .reference_pack import (
    image_file_digest,
    make_workspace_slug,
    prepare_assets_for_duplicate_byte_dedup,
    scan_reference_pack,
)


class RealReferenceAnalyzer:
    def __init__(
        self,
        providers: AnalysisProviders | None = None,
        provider: str = "real",
        device: str = "cuda",
        strict_real: bool = True,
        enable_detector: bool | None = None,
    ) -> None:
        self.providers = providers or create_analysis_providers(provider=provider, device=device, strict_real=strict_real, enable_detector=enable_detector)
        self.provider = self.providers.provider
        self.device = self.providers.device
        self.strict_real = self.providers.strict_real
        profile = load_yaml(Path(__file__).resolve().parents[2] / "configs" / "models" / "analysis_profiles.yaml")
        self.artifact_config = profile.get("image_artifacts", {})
        analysis_cfg = profile.get("analysis") or {}
        self.unload_models_between_assets = bool(
            analysis_cfg.get("unload_models_between_assets", device == "cuda"),
        )
        self.dedupe_duplicate_images = bool(analysis_cfg.get("dedupe_duplicate_images", True))
        if self.provider == "real" and not self.strict_real:
            raise ProviderError("RealReferenceAnalyzer", "real provider must run in strict_real mode unless explicitly configured otherwise")

    def analyze_pack(
        self,
        pack_dir: str | Path,
        negative_prompt: str = "low quality, bad anatomy, blurry, watermark, text",
        *,
        skip_existing: bool = False,
        max_assets: int | None = None,
        rel_path_filter: str | None = None,
    ) -> dict[str, Any]:
        pack = scan_reference_pack(pack_dir)
        processed = pack.root / "processed"
        analyses: list[dict[str, Any]] = []
        raw_count = 0
        style_count = 0
        assets = list(pack.assets)
        if rel_path_filter and rel_path_filter.strip():
            sub = rel_path_filter.strip().lower()
            assets = [a for a in assets if sub in a.rel_path.replace("\\", "/").lower()]
        if max_assets is not None:
            assets = assets[: max(0, int(max_assets))]
        if self.dedupe_duplicate_images:
            assets = prepare_assets_for_duplicate_byte_dedup(assets)
        canon_dir_by_digest: dict[str, Path] = {}
        canon_asset_by_digest: dict[str, Any] = {}
        for asset in assets:
            workspace_id = asset.workspace_id or make_workspace_slug(asset.rel_path)
            print(f"source: {asset.rel_path}")
            print(f"stem: {asset.path.stem}")
            print(f"workspace_id: {workspace_id}")
            print(f"role: {asset.role}")
            is_style = asset.role == "style"
            asset_dir = processed / ("style" if is_style else "raw") / workspace_id
            asset_dir.mkdir(parents=True, exist_ok=True)
            write_json(
                asset_dir / "source.json",
                {
                    "stem": asset.path.stem,
                    "workspace_id": workspace_id,
                    "path": str(asset.path),
                    "rel_path": asset.rel_path,
                    "category": asset.category,
                    "role": asset.role,
                    "source_type": asset.source_type,
                    "mock": self.provider == "mock",
                },
            )
            analysis_path = asset_dir / "analysis.json"
            digest_val = ""
            duplicate_clone = False
            canon_dir: Path | None = None
            canon_ref: Any = None
            if self.dedupe_duplicate_images and not is_style:
                try:
                    digest_val = image_file_digest(asset.path)
                except OSError:
                    digest_val = ""
                if digest_val and digest_val in canon_dir_by_digest:
                    duplicate_clone = True
                    canon_dir = canon_dir_by_digest[digest_val]
                    canon_ref = canon_asset_by_digest[digest_val]

            analysis: dict[str, Any] | None = None
            if duplicate_clone and canon_dir is not None and canon_ref is not None:
                print(f"duplicate image bytes — cloning analysis from {canon_ref.rel_path} -> {asset.rel_path}")
                analysis = self._clone_subject_outputs_from_canonical(canon_ref, canon_dir, asset, workspace_id, asset_dir)
            elif skip_existing and analysis_path.is_file():
                try:
                    cached = load_json(analysis_path)
                    if str((cached.get("caption") or {}).get("summary") or "").strip():
                        analysis = cached
                except Exception:
                    pass
            if analysis is None:
                analysis = self._analyze_style_asset(asset.path, asset.role, asset_dir) if is_style else self._analyze_subject_asset(
                    asset.path, asset.role, asset_dir
                )
            analysis.update(
                {
                    "mock": self.provider == "mock",
                    "provider_name": "RealReferenceAnalyzer" if self.provider == "real" else "MockReferenceAnalyzer",
                    "model_path": "multiple",
                    "device": self.device,
                    "runtime_ms": 0,
                    "image_path": str(asset.path),
                    "asset_id": asset.path.stem,
                    "workspace_id": workspace_id,
                    "reference_pack_id": pack.pack_id,
                    "category": asset.category,
                    "role": asset.role,
                    "source_type": asset.source_type,
                    "analysis_path": str(asset_dir / "analysis.json"),
                    "asset_dir": str(asset_dir),
                }
            )
            if self.provider == "real" and analysis.get("mock"):
                raise ProviderError("RealReferenceAnalyzer", f"real mode attempted to write mock analysis for {asset.path}")
            write_json(asset_dir / "analysis.json", analysis)
            write_json(processed / "analysis" / f"{workspace_id}.json", analysis)
            caption = analysis.get("caption", {})
            tags = analysis.get("tags", {})
            write_json(asset_dir / "caption.json", caption)
            write_json(asset_dir / "tags.json", tags)
            write_json(processed / "caption" / f"{workspace_id}.json", caption)
            write_json(processed / "tags" / f"{workspace_id}.json", tags)
            if is_style:
                self._mirror_style_hub_assets(processed, workspace_id, asset_dir)
            else:
                self._mirror_subject_hub_assets(processed, workspace_id, asset_dir)
            bundle = build_prompt_bundle(pack.pack_id.replace("_v1", ""), [analysis], negative_prompt)
            save_prompt_bundle(bundle, asset_dir / "prompt_bundle.json")
            if is_style:
                style_count += 1
                write_json(asset_dir / "style_palette.json", self._style_palette(caption))
            else:
                raw_count += 1
            analyses.append(analysis)
            if self.dedupe_duplicate_images and not is_style and digest_val and not duplicate_clone:
                canon_dir_by_digest[digest_val] = asset_dir
                canon_asset_by_digest[digest_val] = asset
        bundle = build_prompt_bundle(pack.pack_id.replace("_v1", ""), analyses, negative_prompt)
        bundle_path = save_prompt_bundle(bundle, processed / "prompt_bundle" / "prompt_bundle.json")
        pack_summary = {
            "pack_id": pack.pack_id,
            "asset_count": len(assets),
            "pack_scanned_assets": len(pack.assets),
            "raw_count": raw_count,
            "style_count": style_count,
            "processed_dir": str(processed),
            "mock": self.provider == "mock",
            "providers": self._provider_names(),
            "dedupe_duplicate_images": self.dedupe_duplicate_images,
        }
        write_json(pack.root / "pack_summary.json", pack_summary)
        return {
            "reference_pack": pack,
            "analyses": analyses,
            "prompt_bundle": bundle,
            "prompt_bundle_path": bundle_path,
            "pack_summary": pack_summary,
        }

    def _rewrite_path_strings_nested(self, value: Any, pairs: list[tuple[str, str]]) -> Any:
        if not pairs:
            return value
        if isinstance(value, str):
            out = value
            for src, dst in pairs:
                if src and src in out:
                    out = out.replace(src, dst)
            return out
        if isinstance(value, list):
            return [self._rewrite_path_strings_nested(x, pairs) for x in value]
        if isinstance(value, dict):
            return {k: self._rewrite_path_strings_nested(v, pairs) for k, v in value.items()}
        return value

    def _clone_subject_outputs_from_canonical(
        self,
        canon_asset: Any,
        canon_dir: Path,
        target_asset: Any,
        target_workspace_id: str,
        target_dir: Path,
    ) -> dict[str, Any]:
        for fp in canon_dir.iterdir():
            if fp.name == "source.json":
                continue
            if fp.is_file():
                shutil.copy2(fp, target_dir / fp.name)
        canon_wid = str(canon_asset.workspace_id)
        pairs: list[tuple[str, str]] = [
            (str(canon_dir.resolve()), str(target_dir.resolve())),
            (str(canon_dir), str(target_dir)),
            (str(Path(canon_asset.path).resolve()), str(Path(target_asset.path).resolve())),
            (str(canon_asset.path), str(target_asset.path)),
            (canon_asset.rel_path.replace("\\", "/"), target_asset.rel_path.replace("\\", "/")),
            (canon_wid, target_workspace_id),
        ]
        pairs = [(a, b) for a, b in pairs if a and a != b]
        pairs.sort(key=lambda t: len(t[0]), reverse=True)
        payload = load_json(target_dir / "analysis.json")
        payload = self._rewrite_path_strings_nested(payload, pairs)
        payload["duplicate_of"] = {
            "workspace_id": canon_wid,
            "rel_path": canon_asset.rel_path,
            "path": str(canon_asset.path),
            "asset_dir": str(canon_dir),
        }
        warns = payload.setdefault("warnings", [])
        if isinstance(warns, list):
            warns.append(f"analysis_cloned_from:{canon_asset.rel_path}")
        return payload

    def _release_matting_gpu(self) -> None:
        if not self.unload_models_between_assets:
            return
        fn = getattr(self.providers.matting, "unload_from_device", None)
        if callable(fn):
            fn()

    def _release_tagger_session(self) -> None:
        if not self.unload_models_between_assets:
            return
        fn = getattr(self.providers.tagger, "unload_from_device", None)
        if callable(fn):
            fn()

    def _release_vlm_gpu(self) -> None:
        if not self.unload_models_between_assets:
            return
        fn = getattr(self.providers.vlm, "unload_from_device", None)
        if callable(fn):
            fn()

    def _analyze_subject_asset(self, image_path: Path, role: str, asset_dir: Path) -> dict[str, Any]:
        prompts = self._segmentation_prompts(role)
        detections: list[dict[str, Any]] = []
        detection: dict[str, Any] | None = None
        if self.providers.enable_detector and self.providers.detector:
            print("running detector...")
            detection = self.providers.detector.detect(str(image_path), prompts)
            write_json(asset_dir / "detection.json", detection)
            detections = detection.get("detections") or detection.get("results", {}).get("detections", [])
        print("running segmentation...")
        self._set_output_dir(self.providers.segmentation, asset_dir)
        segmentation = self.providers.segmentation.segment(str(image_path), asset_dir, prompts)
        write_json(asset_dir / "segmentation.json", segmentation)
        print("running matting...")
        self._set_output_dir(self.providers.matting, asset_dir)
        matting = self.providers.matting.remove_background(str(image_path))
        write_json(asset_dir / "matting.json", matting)
        print("writing artifacts...")
        artifacts, quality_checks, artifact_warnings = self._write_subject_artifacts(image_path, asset_dir, segmentation, detections, matting)
        self._release_matting_gpu()
        print("running tagger...")
        tags = self.providers.tagger.tag(str(image_path))
        self._release_tagger_session()
        print("running vlm...")
        caption = self.providers.vlm.describe(
            str(image_path),
            role=self._vlm_role(role, image_path),
            raw_reply_path=asset_dir / "vlm_reply_raw.txt",
        )
        self._release_vlm_gpu()
        if self.provider == "real":
            self._assert_real_provider_outputs([segmentation, matting, tags, caption])
            if detection:
                self._assert_real_provider_outputs([detection])
        return {
            "providers": self._provider_names(),
            "artifacts": artifacts,
            "detections": detections,
            "segmentation": segmentation,
            "matting": matting,
            "tags": tags,
            "caption": caption,
            "quality_checks": quality_checks,
            "warnings": [
                *artifact_warnings,
                *((detection or {}).get("warnings", [])),
                *segmentation.get("warnings", []),
                *matting.get("warnings", []),
                *tags.get("warnings", []),
                *caption.get("warnings", []),
            ],
        }

    def _analyze_style_asset(self, image_path: Path, role: str, asset_dir: Path) -> dict[str, Any]:
        print("running tagger...")
        tags = self.providers.tagger.tag(str(image_path))
        self._release_tagger_session()
        print("running vlm...")
        caption = self.providers.vlm.describe(
            str(image_path),
            role=self._vlm_role(role, image_path),
            raw_reply_path=asset_dir / "vlm_reply_raw.txt",
        )
        self._release_vlm_gpu()
        print("writing artifacts...")
        canny = make_canny(image_path, asset_dir / "control_canny.png", self._int_cfg("canny_low", 80), self._int_cfg("canny_high", 160))
        lineart = make_lineart_basic(image_path, asset_dir / "control_lineart.png")
        if self.provider == "real":
            self._assert_real_provider_outputs([tags, caption])
        return {
            "providers": self._provider_names(include_vision=False),
            "artifacts": {"control_canny": str(canny), "control_lineart": str(lineart)},
            "detections": [],
            "tags": tags,
            "caption": caption,
            "quality_checks": {},
            "warnings": [*tags.get("warnings", []), *caption.get("warnings", [])],
        }

    def _write_subject_artifacts(
        self,
        image_path: Path,
        asset_dir: Path,
        segmentation: dict[str, Any],
        detections: list[dict[str, Any]],
        matting: dict[str, Any],
    ) -> tuple[dict[str, str], dict[str, Any], list[str]]:
        masks = segmentation.get("masks") or segmentation.get("results", {}).get("masks", {})
        subject = masks.get("subject") or {}
        subject_mask = subject.get("mask_path")
        if not subject_mask:
            raise ProviderError("RealReferenceAnalyzer", "segmentation did not return subject.mask_path")
        subject_mask_path = Path(subject_mask)
        final_subject_mask = asset_dir / "subject_mask.png"
        if subject_mask_path.resolve() != final_subject_mask.resolve():
            shutil.copy2(subject_mask_path, final_subject_mask)
        check = validate_mask_area(final_subject_mask, self._float_cfg("min_mask_area_ratio", 0.03), self._float_cfg("max_mask_area_ratio", 0.90))
        if check["errors"]:
            raise ProviderError("RealReferenceAnalyzer", f"subject mask invalid: {check['errors']}")
        artifacts = {
            "subject_mask": str(final_subject_mask),
            "subject_alpha": str(apply_mask_to_alpha(image_path, final_subject_mask, asset_dir / "subject_alpha.png")),
            "subject_crop_tight": str(crop_by_mask(image_path, final_subject_mask, asset_dir / "subject_crop_tight.png")),
            "subject_crop_pad": str(crop_by_mask(image_path, final_subject_mask, asset_dir / "subject_crop_pad.png", self._float_cfg("crop_pad_ratio", 0.18))),
        }
        warnings = list(check["warnings"])
        artifacts["subject_square_1024"] = str(resize_square_1024(artifacts["subject_crop_pad"], asset_dir / "subject_square_1024.png", self._int_cfg("square_size", 1024)))
        subject_box = subject.get("source_box") or self._first_box(detections)
        if subject_box:
            artifacts["halfbody_crop"] = str(make_halfbody_crop(image_path, subject_box, asset_dir / "halfbody_crop.png"))
        else:
            artifacts["halfbody_crop"] = str(make_halfbody_crop_from_mask(image_path, final_subject_mask, asset_dir / "halfbody_crop.png"))
        face_box = self._find_box(detections, ["face", "head"])
        if face_box:
            artifacts["face_crop"] = str(make_face_crop(image_path, face_box, asset_dir / "face_crop.png"))
            face_crop_mode = "detector"
        else:
            heuristic_face = make_face_crop_from_mask_heuristic(image_path, final_subject_mask, asset_dir / "face_crop.png")
            face_crop_mode = "heuristic" if heuristic_face else "unavailable"
            if heuristic_face:
                artifacts["face_crop"] = str(heuristic_face)
            else:
                warnings.append("face_crop skipped: subject mask too small for heuristic face region")
        mecha_box = self._find_box(detections, ["mecha", "armor", "weapon", "mechanical"])
        if mecha_box:
            artifacts["mecha_crop"] = str(crop_by_box(image_path, mecha_box, asset_dir / "mecha_crop.png", pad_ratio=0.18))
        artifacts["control_canny"] = str(make_canny(image_path, asset_dir / "control_canny.png", self._int_cfg("canny_low", 80), self._int_cfg("canny_high", 160)))
        artifacts["control_lineart"] = str(make_lineart_basic(image_path, asset_dir / "control_lineart.png"))
        depth = make_depth_if_available(image_path, asset_dir / "control_depth.png")
        if depth:
            artifacts["control_depth"] = str(depth)
        else:
            warnings.append("control_depth.png skipped: no real depth provider configured")
        alpha_path = matting.get("alpha_path") or matting.get("results", {}).get("alpha_path")
        if alpha_path:
            alpha_src = Path(alpha_path).resolve()
            alpha_dst = (asset_dir / "birefnet_alpha.png").resolve()
            duplicate = alpha_src == alpha_dst
            if not duplicate:
                try:
                    duplicate = alpha_src.exists() and alpha_dst.exists() and alpha_src.samefile(alpha_dst)
                except OSError:
                    duplicate = False
            if not duplicate:
                shutil.copy2(alpha_src, alpha_dst)
        quality_checks = {
            "mask_area_ratio": check["area_ratio"],
            "face_crop_found": "face_crop" in artifacts,
            "face_crop_mode": face_crop_mode,
            "subject_crop_valid": Path(artifacts["subject_crop_tight"]).exists(),
        }
        return artifacts, quality_checks, warnings

    def _style_palette(self, caption: dict[str, Any]) -> dict[str, Any]:
        style = caption.get("style", {})
        return {
            "mock": self.provider == "mock",
            "provider_name": caption.get("provider_name", ""),
            "model_path": caption.get("model_path", ""),
            "device": caption.get("device", self.device),
            "runtime_ms": caption.get("runtime_ms", 0),
            "dominant_colors": style.get("color_palette", []),
            "style_keywords": caption.get("keywords", []),
            "warnings": caption.get("warnings", []),
        }

    def _hub_copy(self, src: Path, dest_dir: Path) -> None:
        """Copy artifact into processed/{hub}/<workspace_id>/ when not already the same file."""
        if not src.is_file():
            return
        dest_dir.mkdir(parents=True, exist_ok=True)
        dst = dest_dir / src.name
        if src.resolve() == dst.resolve():
            return
        try:
            if dst.exists() and src.samefile(dst):
                return
        except OSError:
            pass
        shutil.copy2(src, dst)

    def _mirror_subject_hub_assets(self, processed: Path, workspace_id: str, asset_dir: Path) -> None:
        """Expose masks / alpha / crops under processed/masks|alpha|crops for tooling that expects column folders."""
        masks = processed / "masks" / workspace_id
        alpha = processed / "alpha" / workspace_id
        crops = processed / "crops" / workspace_id
        for rel, dest in (
            ("subject_mask.png", masks),
            ("birefnet_mask.png", masks),
            ("subject_alpha.png", alpha),
            ("birefnet_alpha.png", alpha),
        ):
            self._hub_copy(asset_dir / rel, dest)
        crop_names = (
            "face_crop.png",
            "halfbody_crop.png",
            "subject_crop_tight.png",
            "subject_crop_pad.png",
            "subject_square_1024.png",
            "mecha_crop.png",
            "control_canny.png",
            "control_lineart.png",
            "control_depth.png",
        )
        for name in crop_names:
            self._hub_copy(asset_dir / name, crops)

    def _mirror_style_hub_assets(self, processed: Path, workspace_id: str, asset_dir: Path) -> None:
        crops = processed / "crops" / workspace_id
        for name in ("control_canny.png", "control_lineart.png"):
            self._hub_copy(asset_dir / name, crops)

    def _provider_names(self, include_vision: bool = True) -> dict[str, str]:
        names = {
            "tagger": getattr(self.providers.tagger, "provider_name", ""),
            "vlm": getattr(self.providers.vlm, "provider_name", ""),
        }
        if include_vision:
            names.update(
                {
                    "detector": getattr(self.providers.detector, "provider_name", ""),
                    "segmentation": getattr(self.providers.segmentation, "provider_name", ""),
                    "matting": getattr(self.providers.matting, "provider_name", ""),
                }
            )
            if not self.providers.enable_detector:
                names["detector"] = "disabled"
        return names

    def _set_output_dir(self, provider: Any, output_dir: Path) -> None:
        if hasattr(provider, "output_dir"):
            provider.output_dir = output_dir

    def _assert_real_provider_outputs(self, payloads: list[dict[str, Any]]) -> None:
        for payload in payloads:
            if payload.get("mock") is not False:
                raise ProviderError("RealReferenceAnalyzer", f"provider returned mock payload in real mode: {payload.get('provider_name')}")

    def _first_box(self, detections: list[dict[str, Any]]) -> list[float]:
        return detections[0].get("box_xyxy", []) if detections else []

    def _find_box(self, detections: list[dict[str, Any]], labels: list[str]) -> list[float]:
        for item in detections:
            label = str(item.get("label", "")).lower()
            if any(token in label for token in labels):
                return item.get("box_xyxy", [])
        return []

    def _float_cfg(self, key: str, default: float) -> float:
        return float(self.artifact_config.get(key, default))

    def _int_cfg(self, key: str, default: int) -> int:
        return int(self.artifact_config.get(key, default))

    def _segmentation_prompts(self, role: str) -> list[str]:
        if role in {"init", "raw", "identity"}:
            return ["main subject", "anime character", "person"]
        if role == "mecha":
            return ["mechanical armor", "weapon", "mecha"]
        return ["main subject", "person", "anime character"]

    def _vlm_role(self, role: str, image_path: Path) -> str:
        normalized = str(image_path).replace("\\", "/").lower()
        if "screenshots" in normalized or "screenshot" in normalized or "/screen" in normalized:
            return "screenshot"
        if "official" in normalized:
            return "official"
        if "fanart" in normalized:
            return "fanart"
        return role
