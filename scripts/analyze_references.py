from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aigc2d.prompting import write_prompt_sheet
from aigc2d.reference_analysis import ReferenceAnalyzer
from aigc2d.reference_pack import build_manifest_rows, scan_reference_pack, write_manifest_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a reference pack and write processed artifacts.")
    parser.add_argument("--pack", default="data/reference_packs/firefly_v1")
    parser.add_argument("--manifest-output", default="")
    parser.add_argument("--prompt-sheet-output", default="")
    parser.add_argument("--negative-prompt", default="low quality, worst quality, bad anatomy, blurry, watermark, text")
    args = parser.parse_args()

    pack = scan_reference_pack(args.pack)
    result = ReferenceAnalyzer().analyze_pack(pack.root, negative_prompt=args.negative_prompt)
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
    print(f"assets: {len(pack.assets)}")
    print(f"raw assets: {result['pack_summary']['raw_count']}")
    print(f"style assets: {result['pack_summary']['style_count']}")
    print(f"processed: {(pack.root / 'processed').resolve()}")
    print(f"manifest: {Path(manifest_path).resolve()}")
    print(f"prompt_sheet: {Path(prompt_sheet_path).resolve()}")
    print(f"prompt_bundle: {Path(result['prompt_bundle_path']).resolve()}")
    print("next step:")
    print(f"python scripts/build_tasks.py --pack {pack.root}")


if __name__ == "__main__":
    main()
