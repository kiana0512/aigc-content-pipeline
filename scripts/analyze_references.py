from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aigc2d.config import PROJECT_ROOT, load_yaml
from aigc2d.prompting import write_prompt_sheet
from aigc2d.providers import ProviderError
from aigc2d.reference_analysis import ReferenceAnalyzer
from aigc2d.reference_pack import build_manifest_rows, scan_reference_pack, write_manifest_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a reference pack and write processed artifacts.")
    parser.add_argument("--pack", default="data/reference_packs/firefly_v1")
    parser.add_argument("--manifest-output", default="")
    parser.add_argument("--prompt-sheet-output", default="")
    parser.add_argument("--negative-prompt", default="low quality, worst quality, bad anatomy, blurry, watermark, text")
    parser.add_argument("--provider", choices=["real", "mock"], default="real")
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--strict-real", action="store_true", default=True)
    parser.add_argument("--enable-detector", action="store_true", help="Optional extension: enable GroundingDINO before segmentation.")
    parser.add_argument("--skip-existing", action="store_true", help="Skip assets that already have analysis.json with a non-empty caption summary.")
    parser.add_argument("--max-assets", type=int, default=0, metavar="N", help="Process at most N assets (priority order); 0 means all.")
    parser.add_argument("--rel-path-filter", default="", metavar="SUBSTR", help="Only process assets whose rel_path contains this substring (case-insensitive).")
    args = parser.parse_args()

    if args.provider == "mock":
        print("WARNING: running MOCK analysis. No real model inference will be performed.")
        strict_real = False
    else:
        strict_real = bool(args.strict_real)
        tagger_cfg = str((load_yaml(PROJECT_ROOT / "configs/models/analysis_profiles.yaml").get("tagger") or {}).get("provider", "wd14")).lower()
        if tagger_cfg in ("none", "disabled", "skip", "off"):
            tagger_line = f"skipped (tagger.provider={tagger_cfg})"
        else:
            tagger_line = "WD14 ONNX + CSV (see configs/models/analysis_profiles.yaml)"
        print("Real analysis enabled:")
        print(f"- detector: {'GroundingDINO' if args.enable_detector else 'disabled'}")
        print("- segmentation: SAM3 external (conda env sam3; build_sam3_image_model when sam3_backend: image)")
        print("- matting: BiRefNet")
        print(f"- tagger: {tagger_line}")
        print("- vlm: Qwen2.5-VL or Florence")
        print("- screenshots emphasis: enabled")
        print(f"- device: {args.device}")
        print(f"- strict_real: {strict_real}")
        prof = load_yaml(PROJECT_ROOT / "configs/models/analysis_profiles.yaml")
        ac = prof.get("analysis") or {}
        if ac.get("unload_models_between_assets", True) and args.device == "cuda":
            print("- VRAM: unload_models_between_assets enabled (see analysis_profiles.yaml)")
        if ac.get("tagger_force_cpu") and args.provider == "real":
            print("- VRAM: WD14 tagger forced to CPU execution (tagger_force_cpu)")
        if ac.get("dedupe_duplicate_images", True) and args.provider == "real":
            print("- dedupe: same file bytes analyzed once, other paths clone (dedupe_duplicate_images)")
    pack = scan_reference_pack(args.pack)
    try:
        result = ReferenceAnalyzer(provider=args.provider, device=args.device, strict_real=strict_real, enable_detector=args.enable_detector).analyze_pack(
            pack.root,
            negative_prompt=args.negative_prompt,
            skip_existing=bool(args.skip_existing),
            max_assets=None if args.max_assets <= 0 else int(args.max_assets),
            rel_path_filter=(args.rel_path_filter or "").strip() or None,
        )
    except ProviderError as exc:
        raise SystemExit(f"Reference analysis failed: {exc}") from exc
    manifest_path = args.manifest_output or str(pack.root / "manifest.csv")
    prompt_sheet_path = args.prompt_sheet_output or str(pack.root / "prompt_sheet.csv")
    write_manifest_csv(manifest_path, build_manifest_rows(pack))
    bundle = result["prompt_bundle"]
    write_prompt_sheet(
        prompt_sheet_path,
        [
            {
                "id": f"{pack.pack_id}_prompt_001",
                "positive_prompt": bundle.positive_prompt,
                "negative_prompt": bundle.negative_prompt,
                "reference_image": pack.init_image,
                "prompt_bundle": str(result["prompt_bundle_path"]),
                "notes": "Auto-generated from reference analysis; edit manually if needed.",
            }
        ],
    )
    print(f"pack: {pack.pack_id}")
    print(f"assets (this run): {result['pack_summary']['asset_count']}  (scanned in pack: {result['pack_summary'].get('pack_scanned_assets', len(pack.assets))})")
    print(f"raw assets: {result['pack_summary']['raw_count']}")
    print(f"style assets: {result['pack_summary']['style_count']}")
    print(f"processed: {(pack.root / 'processed').resolve()}")
    print(f"manifest: {Path(manifest_path).resolve()}")
    print(f"prompt_sheet: {Path(prompt_sheet_path).resolve()}")
    print(f"prompt_bundle: {Path(result['prompt_bundle_path']).resolve()}")
    print("")
    print("下一步（链路顺序）:")
    print(f"  1. 按需人工检查编辑: {(pack.root / 'processed' / 'prompt_bundle' / 'prompt_bundle.json').resolve()}")
    print(f"  2. 根据 prompt_bundle/manifest 生成 Comfy/API 任务: python scripts/build_tasks.py --pack {pack.root}")
    print("  3. 在 ComfyUI/注册工作流目录中选用对应 workflow（见 workflows/comfyui），按任务表批量出图（或再接你们自己的 batch_generate 封装）")


if __name__ == "__main__":
    main()
