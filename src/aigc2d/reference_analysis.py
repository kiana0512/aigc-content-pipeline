from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .config import write_json
from .prompt_bundle import PromptBundle, build_prompt_bundle, save_prompt_bundle
from .reference_pack import ReferencePack, scan_reference_pack
from .segmentation import MockSegmentationProvider, SegmentationProvider
from .tagger import MockTaggerProvider, TaggerProvider
from .vlm import MockVLMProvider, VLMProvider


class ReferenceAnalyzer:
    def __init__(
        self,
        vlm_provider: VLMProvider | None = None,
        tagger_provider: TaggerProvider | None = None,
        segmentation_provider: SegmentationProvider | None = None,
    ) -> None:
        self.vlm_provider = vlm_provider or MockVLMProvider()
        self.tagger_provider = tagger_provider or MockTaggerProvider()
        self.segmentation_provider = segmentation_provider or MockSegmentationProvider()

    def analyze(self, image_path: str | Path, prompt: str | None = None) -> dict[str, Any]:
        path = str(image_path)
        description = self.vlm_provider.structured_describe(path)
        critique = self.vlm_provider.critique(path, prompt=prompt)
        tags = self.tagger_provider.tag(path)
        structured_tags = self.tagger_provider.structured_tags(path)
        return {
            "image_path": path,
            "caption": self.vlm_provider.caption(path),
            "description": description,
            "critique": critique,
            "tags": tags,
            "structured_tags": structured_tags,
            "prompt_hints": {
                "appearance": description.get("appearance", ""),
                "outfit": description.get("outfit", ""),
                "pose": description.get("pose", ""),
                "background": description.get("background", ""),
                "keywords": description.get("keywords", []),
            },
        }

    def analyze_pack(
        self,
        pack_dir: str | Path,
        negative_prompt: str = "low quality, bad anatomy, blurry, watermark, text",
    ) -> dict[str, Any]:
        pack = scan_reference_pack(pack_dir)
        processed = pack.root / "processed"
        analyses: list[dict[str, Any]] = []
        raw_count = 0
        style_count = 0
        for asset in pack.assets:
            asset_id = asset.path.stem
            is_style = asset.role == "style"
            asset_dir = processed / ("style" if is_style else "raw") / asset_id
            asset_dir.mkdir(parents=True, exist_ok=True)
            segmentation = {} if is_style else self.segmentation_provider.segment(asset.path, processed)
            analysis = self.analyze(asset.path)
            analysis.update(
                {
                    "reference_pack_id": pack.pack_id,
                    "category": asset.category,
                    "role": asset.role,
                    "segmentation": segmentation,
                    "mock": True,
                }
            )
            stem = asset_id
            caption_path = asset_dir / "caption.json"
            tags_path = asset_dir / "tags.json"
            analysis_path = asset_dir / "analysis.json"
            write_json(asset_dir / "source.json", {"asset_id": asset_id, "path": str(asset.path), "category": asset.category, "role": asset.role})
            write_json(caption_path, {"image_path": str(asset.path), "caption": analysis["caption"]})
            write_json(tags_path, {"image_path": str(asset.path), "tags": analysis["tags"], "structured_tags": analysis["structured_tags"]})
            write_json(analysis_path, analysis)
            write_json(processed / "caption" / f"{stem}.json", {"image_path": str(asset.path), "caption": analysis["caption"]})
            write_json(processed / "tags" / f"{stem}.json", {"image_path": str(asset.path), "tags": analysis["tags"], "structured_tags": analysis["structured_tags"]})
            write_json(processed / "analysis" / f"{stem}.json", analysis)
            if is_style:
                style_count += 1
                write_json(asset_dir / "style_palette.json", self._mock_palette(analysis))
                bundle = build_prompt_bundle(f"{pack.pack_id}_style", [analysis], negative_prompt)
                save_prompt_bundle(bundle, asset_dir / "prompt_bundle.json")
            else:
                raw_count += 1
                self._write_raw_artifacts(asset.path, asset_dir, segmentation)
                bundle = build_prompt_bundle(pack.pack_id.replace("_v1", ""), [analysis], negative_prompt)
                save_prompt_bundle(bundle, asset_dir / "prompt_bundle.json")
                write_json(asset_dir / "detection.json", {"provider": "mock_detector", "boxes": [], "mock": True})
            analysis["analysis_path"] = str(analysis_path)
            analysis["asset_dir"] = str(asset_dir)
            analyses.append(analysis)
        bundle = build_prompt_bundle(pack.pack_id.replace("_v1", ""), analyses, negative_prompt)
        bundle_path = save_prompt_bundle(bundle, processed / "prompt_bundle" / "prompt_bundle.json")
        pack_summary = {
            "pack_id": pack.pack_id,
            "asset_count": len(pack.assets),
            "raw_count": raw_count,
            "style_count": style_count,
            "processed_dir": str(processed),
            "mock_providers": ["segmentation", "detector", "vlm", "tagger"],
        }
        write_json(pack.root / "pack_summary.json", pack_summary)
        return {
            "reference_pack": pack,
            "analyses": analyses,
            "prompt_bundle": bundle,
            "prompt_bundle_path": bundle_path,
            "pack_summary": pack_summary,
        }

    def _write_raw_artifacts(self, source: Path, asset_dir: Path, segmentation: dict[str, str]) -> None:
        copies = {
            "subject_mask.png": segmentation.get("mask"),
            "subject_alpha.png": segmentation.get("alpha"),
            "subject_crop_tight.png": segmentation.get("crop"),
            "subject_crop_pad.png": segmentation.get("crop"),
            "subject_square_1024.png": segmentation.get("crop"),
            "halfbody_crop.png": segmentation.get("crop"),
            "face_crop.png": segmentation.get("crop"),
            "control_depth.png": segmentation.get("mask"),
            "control_canny.png": segmentation.get("mask"),
            "control_lineart.png": segmentation.get("mask"),
            "control_pose.png": segmentation.get("mask"),
        }
        for name, candidate in copies.items():
            target = asset_dir / name
            src = Path(candidate) if candidate else source
            if src.exists():
                shutil.copy2(src, target)
            else:
                target.write_bytes(b"")

    def _mock_palette(self, analysis: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider": "mock_palette",
            "dominant_colors": ["teal", "white", "dark navy"],
            "style_keywords": analysis.get("tags", []),
            "mock": True,
        }
