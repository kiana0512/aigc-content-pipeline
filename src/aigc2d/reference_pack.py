from __future__ import annotations

import csv
import hashlib
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
    "init",
    "identity",
    "face",
    "mecha",
    "composition",
    "background",
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


def image_file_digest(path: Path) -> str:
    """SHA256 of raw file bytes — same image reused in official/init/identity dedup."""
    resolved = Path(path).expanduser().resolve(strict=False)
    h = hashlib.sha256()
    with resolved.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_preference_key(asset: "ReferenceAsset") -> tuple[int, str]:
    """Lower rank = preferred canonical slot when multiple paths share identical bytes."""
    rp = asset.rel_path.replace("\\", "/").lower()
    if rp.startswith("selected/init/") or "/selected/init/" in rp:
        return (0, asset.rel_path)
    if rp.startswith("selected/identity/") or "/selected/identity/" in rp:
        return (1, asset.rel_path)
    if rp.startswith("raw/official/") or "/raw/official/" in rp:
        return (2, asset.rel_path)
    if rp.startswith("official/") or "/official/" in rp:
        return (3, asset.rel_path)
    return (100, asset.rel_path)


def prepare_assets_for_duplicate_byte_dedup(assets: list[ReferenceAsset]) -> list[ReferenceAsset]:
    """Reorder only non-style assets: group by file digest, canonical path first; style slots keep original list positions."""
    orig = list(assets)
    non_style = [a for a in orig if a.role != "style"]
    if not non_style:
        return orig

    groups: dict[str, list[ReferenceAsset]] = {}
    for a in non_style:
        try:
            d = image_file_digest(a.path)
        except OSError:
            d = f"__missing__{id(a)}"
        groups.setdefault(d, []).append(a)

    canon_by_digest: dict[str, ReferenceAsset] = {}
    for d, grp in groups.items():
        canon_by_digest[d] = min(grp, key=canonical_preference_key)

    digest_keys = sorted(groups.keys(), key=lambda dg: (-canon_by_digest[dg].priority, canon_by_digest[dg].rel_path))
    ordered_non_style: list[ReferenceAsset] = []
    for d in digest_keys:
        grp = groups[d]
        canon = canon_by_digest[d]
        tails = sorted([x for x in grp if x is not canon], key=lambda z: (-z.priority, z.rel_path))
        ordered_non_style.extend([canon, *tails])

    it = iter(ordered_non_style)
    out: list[ReferenceAsset] = []
    for a in orig:
        if a.role == "style":
            out.append(a)
        else:
            out.append(next(it))
    return out


def make_workspace_slug(rel_path_posix: str) -> str:
    """Stable id for processed/ subfolders: encodes parent path + filename to avoid stem collisions."""
    norm = Path(str(rel_path_posix).replace("\\", "/"))
    slug = "__".join([*norm.parts[:-1], norm.name]).lower() if norm.parts else norm.name.lower()
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in slug)
    while "__" in safe:
        safe = safe.replace("__", "_")
    safe = safe.strip("._")[:200] or "asset"
    return safe


@dataclass
class ReferenceAsset:
    path: Path
    category: str
    role: str
    asset_id: str = ""
    workspace_id: str = ""
    pack_id: str = ""
    rel_path: str = ""
    source_type: str = "unknown"
    priority: int = 0
    filename: str = ""
    notes: str = ""


@dataclass
class ReferencePack:
    pack_id: str
    root: Path
    assets: list[ReferenceAsset] = field(default_factory=list)

    def by_role(self, role: str) -> list[Path]:
        return [asset.path for asset in self.assets if asset.role == role]

    def assets_by_role(self, role: str) -> list[ReferenceAsset]:
        return [asset for asset in self.assets if asset.role == role]

    @property
    def init_image(self) -> str:
        images = self.by_role("init") or self.by_role("identity") or self.by_role("raw")
        return str(images[0]) if images else ""


def ensure_reference_pack_dirs(pack_dir: str | Path) -> Path:
    root = Path(pack_dir)
    for category in [*REFERENCE_CATEGORIES, *PROCESSED_CATEGORIES]:
        (root / category).mkdir(parents=True, exist_ok=True)
    return root


def scan_reference_pack(pack_dir: str | Path) -> ReferencePack:
    root = ensure_reference_pack_dirs(pack_dir)
    assets: list[ReferenceAsset] = []
    seen_paths: set[Path] = set()
    for category in REFERENCE_CATEGORIES:
        dir_path = root / category
        if not dir_path.is_dir():
            continue
        role = infer_role(category)
        for path in sorted(dir_path.iterdir()):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
                continue
            rel_path = path.relative_to(root).as_posix()
            source_type = infer_source_type(rel_path)
            wid = make_workspace_slug(rel_path)
            seen_paths.add(path.resolve())
            assets.append(
                ReferenceAsset(
                    path=path,
                    category=category,
                    role=role,
                    asset_id=path.stem,
                    workspace_id=wid,
                    pack_id=root.name,
                    rel_path=rel_path,
                    source_type=source_type,
                    priority=infer_priority(role, source_type, rel_path),
                    filename=path.name,
                )
            )
    _append_raw_recursive(root, seen_paths, assets)
    assets.sort(key=lambda asset: (-asset.priority, asset.rel_path))
    return ReferencePack(pack_id=root.name, root=root, assets=assets)


def _append_raw_recursive(root: Path, seen_paths: set[Path], assets: list[ReferenceAsset]) -> None:
    """Pick up images under raw/ (any depth) missed by flat category folders (e.g. new subfolders)."""
    raw_root = root / "raw"
    if not raw_root.is_dir():
        return
    for path in sorted(raw_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
            continue
        resolved = path.resolve()
        if resolved in seen_paths:
            continue
        rel_path = path.relative_to(root).as_posix()
        category = str(Path(rel_path).parent.as_posix()).replace("\\", "/")
        role = infer_role(category)
        source_type = infer_source_type(rel_path)
        wid = make_workspace_slug(rel_path)
        seen_paths.add(resolved)
        assets.append(
            ReferenceAsset(
                path=path,
                category=category,
                role=role,
                asset_id=path.stem,
                workspace_id=wid,
                pack_id=root.name,
                rel_path=rel_path,
                source_type=source_type,
                priority=infer_priority(role, source_type, rel_path),
                filename=path.name,
            )
        )


def infer_role(category: str) -> str:
    normalized = category.replace("\\", "/").strip("/")
    parts = normalized.split("/")
    if parts[-1] in {"init", "identity", "face", "mecha", "composition", "background", "style"}:
        return parts[-1]
    return "raw"


def infer_source_type(path_text: str) -> str:
    lowered = path_text.lower()
    if "official" in lowered:
        return "official"
    if "fanart" in lowered:
        return "fanart"
    if "screenshots" in lowered or "screenshot" in lowered or "screen" in lowered:
        return "screenshot"
    if "/selected/" in f"/{lowered}" or lowered.startswith("selected/"):
        return "selected"
    return "unknown"


def infer_priority(role: str, source_type: str, rel_path: str) -> int:
    priority = 10
    if source_type == "selected":
        priority += 100
    if source_type == "official" and role in {"identity", "face", "mecha", "raw"}:
        priority += 60
    if role == "init":
        priority += 50
    if role == "identity":
        priority += 45
    if role == "face":
        priority += 40
    if role == "mecha":
        priority += 35
    if role == "style":
        priority += 30
    if role in {"composition", "background"}:
        priority += 25
    if source_type == "screenshot" and role in {"composition", "background", "raw"}:
        priority += 20
    if source_type == "screenshot" and role in {"identity", "face"}:
        priority -= 20
    if "selected/" in rel_path.replace("\\", "/").lower():
        priority += 20
    # Prefer raw/fanart and raw/screenshots earlier in the queue (GPU time) — official/init duplicate copies still dedup by bytes.
    rp = rel_path.replace("\\", "/").lower()
    if source_type == "fanart" and role == "raw" and "fanart" in rp:
        priority += 175
    if source_type == "screenshot" and role == "raw" and ("screenshots" in rp or "screenshot" in rp):
        priority += 175
    return priority


def build_manifest_rows(pack: ReferencePack, generation_profile: str = "firefly_wallpaper") -> list[dict[str, str]]:
    raw_refs = pack.by_role("raw") or pack.by_role("init")
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
