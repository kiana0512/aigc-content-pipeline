from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aigc2d.prompt_bundle import load_prompt_bundle
from aigc2d.reference_pack import ReferenceAsset, scan_reference_pack


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
        "identity_ref_image",
        "face_ref_image",
        "mecha_ref_image",
        "composition_ref_image",
        "background_ref_image",
        "style_ref_image",
        "prompt_bundle",
        "positive_prompt",
        "negative_prompt",
        "user_positive_append",
        "user_negative_append",
        "workflow_id",
        "generation_profile",
        "model_profile",
        "vae_profile",
        "controlnet_profile",
        "ipadapter_profile",
        "upscale_model",
        "seed",
        "steps",
        "cfg",
        "sampler",
        "sampler_name",
        "scheduler",
        "denoise",
        "output_prefix",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def build_generation_tasks(pack_dir: str | Path, mode: str = "single_init_all_styles", topk: int = 3) -> list[dict[str, Any]]:
    pack = scan_reference_pack(pack_dir)
    manifest_rows = read_csv(pack.root / "manifest.csv")
    manifest = manifest_rows[0] if manifest_rows else {}
    if mode == "manual":
        rows = read_csv(pack.root / "generation_tasks.csv") or manifest_rows
        return [complete_manual_row(row, pack, manifest) for row in rows]
    init_assets = select_assets(pack.assets, "init") or select_assets(pack.assets, "identity") or select_assets(pack.assets, "raw")
    style_assets = select_assets(pack.assets, "style")
    if not style_assets:
        style_assets = [ReferenceAsset(path=Path(path), category="style", role="style") for path in split_refs(manifest.get("style_refs", ""))]
    prompt_bundle_path = pack.root / "processed" / "prompt_bundle" / "prompt_bundle.json"
    positive = ""
    negative = ""
    if prompt_bundle_path.exists():
        bundle = load_prompt_bundle(prompt_bundle_path)
        positive = bundle.positive_prompt
        negative = bundle.negative_prompt
    rows: list[dict[str, Any]] = []
    if mode == "single_init_all_styles":
        selected_inits = init_assets[:1] or [ReferenceAsset(path=Path(manifest.get("init_image", "")), category="init", role="init")]
        selected_styles = style_assets
    elif mode == "topk_style_per_init":
        selected_inits = init_assets or [ReferenceAsset(path=Path(manifest.get("init_image", "")), category="init", role="init")]
        selected_styles = style_assets[:topk]
    elif mode == "cartesian":
        selected_inits = init_assets or [ReferenceAsset(path=Path(manifest.get("init_image", "")), category="init", role="init")]
        selected_styles = style_assets
    else:
        selected_inits = init_assets[:1]
        selected_styles = style_assets[:topk]
    if not selected_styles:
        selected_styles = [ReferenceAsset(path=Path(""), category="style", role="style", notes="No style image found.")]
        print("WARNING: no style images found; style_ref_image will be empty.")
    role_defaults = role_default_images(pack.assets, selected_inits[0].path if selected_inits else Path(""))
    for raw_index, raw_asset in enumerate(selected_inits):
        raw = raw_asset.path
        if not selected_styles:
            selected_styles = [ReferenceAsset(path=Path(""), category="style", role="style")]
        for style_index, style_asset in enumerate(selected_styles):
            style = style_asset.path
            rows.append(
                {
                    "task_id": f"{pack.pack_id}_{raw_index:03d}_{style_index:03d}",
                    "character_id": manifest.get("character_id", pack.pack_id.replace("_v1", "")),
                    "task_type": manifest.get("task_type", "img2img_ipadapter_controlnet"),
                    "reference_pack_id": pack.pack_id,
                    "init_image": str(raw),
                    "identity_ref_image": manifest.get("identity_ref_image") or role_defaults["identity_ref_image"],
                    "face_ref_image": manifest.get("face_ref_image") or role_defaults["face_ref_image"],
                    "mecha_ref_image": manifest.get("mecha_ref_image") or role_defaults["mecha_ref_image"],
                    "composition_ref_image": manifest.get("composition_ref_image") or role_defaults["composition_ref_image"],
                    "background_ref_image": manifest.get("background_ref_image") or role_defaults["background_ref_image"],
                    "style_ref_image": str(style) if str(style) else "",
                    "raw_asset": str(raw),
                    "style_asset": str(style),
                    "style_refs": str(style) if str(style) else "",
                    "identity_refs": manifest.get("identity_refs") or role_defaults["identity_ref_image"],
                    "face_refs": manifest.get("face_refs") or role_defaults["face_ref_image"],
                    "mecha_refs": manifest.get("mecha_refs") or role_defaults["mecha_ref_image"],
                    "composition_refs": manifest.get("composition_refs") or role_defaults["composition_ref_image"],
                    "background_refs": manifest.get("background_refs") or role_defaults["background_ref_image"],
                    "prompt_bundle": str(prompt_bundle_path) if prompt_bundle_path.exists() else "",
                    "positive_prompt": positive,
                    "negative_prompt": negative,
                    "user_positive_append": manifest.get("user_positive_append", ""),
                    "user_negative_append": manifest.get("user_negative_append", ""),
                    "workflow_id": manifest.get("workflow_id", ""),
                    "generation_profile": manifest.get("generation_profile", "firefly_wallpaper"),
                    "model_profile": manifest.get("model_profile", ""),
                    "vae_profile": manifest.get("vae_profile", ""),
                    "controlnet_profile": manifest.get("controlnet_profile", ""),
                    "ipadapter_profile": manifest.get("ipadapter_profile", ""),
                    "upscale_model": manifest.get("upscale_model", ""),
                    "seed": manifest.get("seed", ""),
                    "steps": manifest.get("steps", ""),
                    "cfg": manifest.get("cfg", ""),
                    "sampler": manifest.get("sampler", ""),
                    "sampler_name": manifest.get("sampler_name", ""),
                    "scheduler": manifest.get("scheduler", ""),
                    "denoise": manifest.get("denoise", ""),
                    "output_prefix": manifest.get("output_prefix", ""),
                    "notes": f"mode={mode}; topk={topk}",
                }
            )
    return rows


def select_assets(assets: list[ReferenceAsset], role: str) -> list[ReferenceAsset]:
    return [asset for asset in assets if asset.role == role]


def first_path(assets: list[ReferenceAsset], fallback: Path | str = "") -> str:
    return str(assets[0].path) if assets else str(fallback or "")


def role_default_images(assets: list[ReferenceAsset], init_image: Path) -> dict[str, str]:
    selected = lambda role: [asset for asset in assets if asset.role == role and asset.category.startswith("selected/")]
    role = lambda name: [asset for asset in assets if asset.role == name]
    screenshots = [asset for asset in assets if asset.source_type == "screenshot"]
    official = [asset for asset in assets if asset.source_type == "official"]
    fanart = [asset for asset in assets if asset.source_type == "fanart"]
    init_assets = selected("init") or role("init")
    return {
        "identity_ref_image": first_path(selected("identity") or official or screenshots or init_assets or fanart, init_image),
        "face_ref_image": first_path(selected("face") or role("face"), init_image),
        "mecha_ref_image": first_path(selected("mecha") or role("mecha"), init_image),
        "composition_ref_image": first_path(selected("composition") or role("composition") or screenshots or init_assets or official or fanart, init_image),
        "background_ref_image": first_path(selected("background") or role("background") or screenshots or official or fanart, ""),
    }


def complete_manual_row(row: dict[str, str], pack: Any, manifest: dict[str, str]) -> dict[str, Any]:
    defaults = role_default_images(pack.assets, Path(row.get("init_image") or manifest.get("init_image", "")))
    completed = dict(row)
    for key, value in defaults.items():
        completed.setdefault(key, value)
    completed.setdefault("reference_pack_id", pack.pack_id)
    completed.setdefault("workflow_id", manifest.get("workflow_id", ""))
    completed.setdefault("generation_profile", manifest.get("generation_profile", "firefly_wallpaper"))
    return completed


def main() -> None:
    parser = argparse.ArgumentParser(description="Build generation_tasks.csv from a reference pack.")
    parser.add_argument("--pack", default="data/reference_packs/firefly_v1")
    parser.add_argument("--mode", choices=["single_init_all_styles", "topk_style_per_init", "cartesian", "manual"], default="single_init_all_styles")
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
