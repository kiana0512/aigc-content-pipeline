from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aigc2d.reference_pack import build_manifest_rows, scan_reference_pack, write_manifest_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an editable manifest.csv from a reference pack.")
    parser.add_argument("--pack", default="data/reference_packs/firefly_v1")
    parser.add_argument("--output", default="")
    parser.add_argument("--generation-profile", default="firefly_wallpaper")
    args = parser.parse_args()
    pack = scan_reference_pack(args.pack)
    output = args.output or str(pack.root / "manifest.csv")
    path = write_manifest_csv(output, build_manifest_rows(pack, generation_profile=args.generation_profile))
    print(f"manifest: {path}")


if __name__ == "__main__":
    main()
