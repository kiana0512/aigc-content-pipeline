from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path


REFERENCE_CATEGORIES = [
    "raw",
    "style",
    "raw/official",
    "raw/fanart",
    "raw/screenshots",
    "selected/init",
    "selected/identity",
    "selected/face",
    "selected/mecha",
    "selected/composition",
    "selected/style",
    "selected/background",
]
PROCESSED_CATEGORIES = [
    "processed/masks",
    "processed/crops",
    "processed/alpha",
    "processed/caption",
    "processed/tags",
    "processed/analysis",
    "processed/prompt_bundle",
]
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass
class ReferenceAsset:
    path: Path
    category: str
    role: str


@dataclass
class ReferencePack:
    pack_id: str
    root: Path
    assets: list[ReferenceAsset] = field(default_factory=list)

    def by_role(self, role: str) -> list[Path]:
        return [asset.path for asset in self.assets if asset.role == role]

    @property
    def init_image(self) -> str:
        images = self.by_role("init") or self.by_role("identity") or self.by_role("official")
        return str(images[0]) if images else ""


def ensure_reference_pack_dirs(pack_dir: str | Path) -> Path:
    root = Path(pack_dir)
    for category in [*REFERENCE_CATEGORIES, *PROCESSED_CATEGORIES]:
        (root / category).mkdir(parents=True, exist_ok=True)
    return root


def scan_reference_pack(pack_dir: str | Path) -> ReferencePack:
    root = ensure_reference_pack_dirs(pack_dir)
    assets: list[ReferenceAsset] = []
    for category in REFERENCE_CATEGORIES:
        role = category.split("/")[-1]
        if category == "raw":
            role = "raw"
        if category == "style":
            role = "style"
        for path in sorted((root / category).iterdir()):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
                assets.append(ReferenceAsset(path=path, category=category, role=role))
    return ReferencePack(pack_id=root.name, root=root, assets=assets)


def build_manifest_rows(pack: ReferencePack, generation_profile: str = "firefly_wallpaper") -> list[dict[str, str]]:
    raw_refs = pack.by_role("raw") or pack.by_role("official") or pack.by_role("init")
    style_refs = pack.by_role("style")
    row = {
        "task_id": f"{pack.pack_id}_wallpaper_001",
        "character_id": pack.pack_id.replace("_v1", ""),
        "task_type": "img2img_ipadapter_controlnet",
        "reference_pack_id": pack.pack_id,
        "init_image": str(raw_refs[0]) if raw_refs else pack.init_image,
        "raw_refs": "|".join(str(path) for path in raw_refs),
        "identity_refs": "|".join(str(path) for path in pack.by_role("identity") or raw_refs[:1]),
        "face_refs": "|".join(str(path) for path in pack.by_role("face")),
        "mecha_refs": "|".join(str(path) for path in pack.by_role("mecha")),
        "composition_refs": "|".join(str(path) for path in pack.by_role("composition")),
        "style_refs": "|".join(str(path) for path in style_refs),
        "background_refs": "|".join(str(path) for path in pack.by_role("background")),
        "generation_profile": generation_profile,
        "notes": "Auto-generated from reference pack; edit manually if needed.",
    }
    return [row]


def write_manifest_csv(path: str | Path, rows: list[dict[str, str]]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "task_id",
        "character_id",
        "task_type",
        "reference_pack_id",
        "init_image",
        "raw_refs",
        "identity_refs",
        "face_refs",
        "mecha_refs",
        "composition_refs",
        "style_refs",
        "background_refs",
        "generation_profile",
        "notes",
    ]
    with target.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return target
