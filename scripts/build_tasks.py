from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aigc2d.prompt_bundle import load_prompt_bundle
from aigc2d.reference_pack import IMAGE_EXTS, scan_reference_pack


def split_refs(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split("|") if item.strip()]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "task_id",
        "character_id",
        "task_type",
        "reference_pack_id",
        "init_image",
        "raw_asset",
        "style_asset",
        "style_refs",
        "prompt_bundle",
        "positive_prompt",
        "negative_prompt",
        "workflow_id",
        "generation_profile",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def build_generation_tasks(pack_dir: str | Path, mode: str = "topk_style_per_raw", topk: int = 3) -> list[dict[str, Any]]:
    pack = scan_reference_pack(pack_dir)
    manifest_rows = read_csv(pack.root / "manifest.csv")
    manifest = manifest_rows[0] if manifest_rows else {}
    raw_assets = pack.by_role("raw") or pack.by_role("official") or pack.by_role("init")
    style_assets = pack.by_role("style")
    if not style_assets:
        style_assets = [Path(path) for path in split_refs(manifest.get("style_refs", ""))]
    prompt_bundle_path = pack.root / "processed" / "prompt_bundle" / "prompt_bundle.json"
    positive = ""
    negative = ""
    if prompt_bundle_path.exists():
        bundle = load_prompt_bundle(prompt_bundle_path)
        positive = bundle.positive_prompt
        negative = bundle.negative_prompt
    rows: list[dict[str, Any]] = []
    for raw_index, raw in enumerate(raw_assets or [Path(manifest.get("init_image", ""))]):
        selected_styles = style_assets
        if mode == "topk_style_per_raw":
            selected_styles = style_assets[:topk]
        if mode == "manual":
            selected_styles = [Path(path) for path in split_refs(manifest.get("style_refs", ""))][:topk]
        if not selected_styles:
            selected_styles = [Path("")]
        for style_index, style in enumerate(selected_styles):
            rows.append(
                {
                    "task_id": f"{pack.pack_id}_{raw_index:03d}_{style_index:03d}",
                    "character_id": manifest.get("character_id", pack.pack_id.replace("_v1", "")),
                    "task_type": manifest.get("task_type", "img2img_ipadapter_controlnet"),
                    "reference_pack_id": pack.pack_id,
                    "init_image": str(raw),
                    "raw_asset": str(raw),
                    "style_asset": str(style),
                    "style_refs": str(style) if str(style) else "",
                    "identity_refs": manifest.get("identity_refs", str(raw)),
                    "face_refs": manifest.get("face_refs", ""),
                    "mecha_refs": manifest.get("mecha_refs", ""),
                    "composition_refs": manifest.get("composition_refs", ""),
                    "background_refs": manifest.get("background_refs", ""),
                    "prompt_bundle": str(prompt_bundle_path) if prompt_bundle_path.exists() else "",
                    "positive_prompt": positive,
                    "negative_prompt": negative,
                    "workflow_id": manifest.get("workflow_id", ""),
                    "generation_profile": manifest.get("generation_profile", "firefly_wallpaper"),
                    "notes": f"mode={mode}; topk={topk}",
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build generation_tasks.csv from a reference pack.")
    parser.add_argument("--pack", default="data/reference_packs/firefly_v1")
    parser.add_argument("--mode", choices=["cartesian", "topk_style_per_raw", "manual"], default="topk_style_per_raw")
    parser.add_argument("--topk", type=int, default=3)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    rows = build_generation_tasks(args.pack, mode=args.mode, topk=args.topk)
    output = Path(args.output) if args.output else Path(args.pack) / "generation_tasks.csv"
    path = write_csv(output, rows)
    print(f"generated tasks: {len(rows)}")
    print(f"task file: {path.resolve()}")
    print("next dry-run:")
    print(f"python scripts/batch_generate_stub.py --tasks {path} --dry-run")
    print("execute after checking patched workflows:")
    print(f"python scripts/batch_generate_stub.py --tasks {path} --execute --download-outputs")


if __name__ == "__main__":
    main()
