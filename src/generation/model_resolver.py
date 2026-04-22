from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

MODEL_FILE_EXTENSIONS = {
    ".safetensors",
    ".ckpt",
    ".pt",
    ".pth",
    ".bin",
    ".onnx",
    ".gguf",
}

COMFYUI_MODEL_DIR_KEYS = [
    "checkpoints",
    "diffusion_models",
    "vae",
    "text_encoders",
    "clip_vision",
    "loras",
    "controlnet",
    "embeddings",
    "style_models",
    "upscale_models",
    "latent_upscale_models",
    "photomaker",
    "gligen",
    "hypernetworks",
    "audio_encoders",
    "diffusers",
    "vae_approx",
    "classifiers",
    "model_patches",
    "download_model_base",
]

MODEL_KIND_TO_DIR_KEYS: dict[str, list[str]] = {
    "checkpoint": ["checkpoints"],
    "unet": ["diffusion_models", "checkpoints"],
    "text_encoder": ["text_encoders", "checkpoints"],
    "vae": ["vae"],
    "lora": ["loras"],
    "controlnet": ["controlnet"],
    "clip_vision": ["clip_vision"],
    "embedding": ["embeddings"],
    "style_model": ["style_models"],
    "upscale": ["upscale_models", "latent_upscale_models"],
    "audio_encoder": ["audio_encoders"],
}


def scan_model_directories(
    comfyui_root: str | Path,
    model_dir_map: dict[str, str],
) -> dict[str, Any]:
    root = Path(comfyui_root)
    folder_index: dict[str, Any] = {}
    for dir_key in COMFYUI_MODEL_DIR_KEYS:
        configured = str(model_dir_map.get(dir_key, "")).strip()
        resolved_path = _resolve_model_dir_path(root, configured, dir_key)
        files = _scan_dir_files(resolved_path)
        folder_index[dir_key] = {
            "configured_path": configured,
            "resolved_path": str(resolved_path.as_posix()),
            "exists": resolved_path.exists(),
            "file_count": len(files),
            "files": files,
            "basename_index": _build_basename_index(files),
            "stem_index": _build_stem_index(files),
        }
    return {
        "comfyui_root": str(root.as_posix()),
        "folders": folder_index,
    }


def resolve_models_from_inspection(
    inspection_result: dict[str, Any],
    scanned_index: dict[str, Any],
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    detected_models = inspection_result.get("detected_model_files", [])
    policy_resolved = _normalize_resolution_policy(policy)
    resolved_models: list[dict[str, Any]] = []
    missing_models: list[dict[str, Any]] = []
    duplicate_candidates: list[dict[str, Any]] = []
    maybe_matched_candidates: list[dict[str, Any]] = []

    for model_item in detected_models:
        model_name = str(model_item.get("model_name", "")).strip()
        if not model_name:
            continue
        model_kind = str(model_item.get("model_kind", "")).strip()
        candidate_dirs = MODEL_KIND_TO_DIR_KEYS.get(model_kind, COMFYUI_MODEL_DIR_KEYS)

        match = _match_model_name(
            model_name=model_name,
            candidate_dirs=candidate_dirs,
            scanned_index=scanned_index,
            policy=policy_resolved,
        )

        entry = {
            "node_id": model_item.get("node_id"),
            "class_type": model_item.get("class_type"),
            "model_kind": model_kind,
            "requested_model_name": model_name,
            "candidate_dirs": candidate_dirs,
            "suggested_target_dir": candidate_dirs[0] if candidate_dirs else "",
        }
        if match["status"] == "resolved":
            resolved_models.append({**entry, **match})
        elif match["status"] == "ambiguous":
            duplicate_candidates.append({**entry, **match})
        elif match["status"] == "maybe":
            maybe_matched_candidates.append({**entry, **match})
            missing_models.append({**entry, **match})
        else:
            missing_models.append({**entry, **match})

    return {
        "resolved_models": resolved_models,
        "missing_models": missing_models,
        "duplicate_candidates": duplicate_candidates,
        "maybe_matched_candidates": maybe_matched_candidates,
        "summary": {
            "requested_model_count": len(detected_models),
            "resolved_count": len(resolved_models),
            "missing_count": len(missing_models),
            "duplicate_count": len(duplicate_candidates),
            "maybe_count": len(maybe_matched_candidates),
        },
    }


def build_model_resolution_report(
    inspection_result: dict[str, Any],
    comfyui_root: str | Path,
    model_dir_map: dict[str, str],
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scanned = scan_model_directories(comfyui_root=comfyui_root, model_dir_map=model_dir_map)
    resolved = resolve_models_from_inspection(
        inspection_result=inspection_result,
        scanned_index=scanned,
        policy=policy,
    )
    return {
        "inspection_summary": {
            "workflow_format": inspection_result.get("workflow_format"),
            "node_count": inspection_result.get("node_count", 0),
            "detected_model_reference_count": len(
                inspection_result.get("detected_model_files", [])
            ),
            "suggested_model_family": inspection_result.get("suggested_model_family", ""),
        },
        "scan": scanned,
        "policy": _normalize_resolution_policy(policy),
        "resolution": resolved,
    }


def save_model_resolution_report_json(report: dict[str, Any], output_path: str | Path) -> Path:
    import json

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _resolve_model_dir_path(root: Path, configured: str, dir_key: str) -> Path:
    if configured:
        configured_path = Path(configured)
        if configured_path.is_absolute():
            return configured_path
        normalized = configured.replace("\\", "/").strip("/")
        if normalized.startswith("ComfyUI/models/"):
            suffix = normalized.removeprefix("ComfyUI/models/")
            return root / "models" / suffix
        if normalized == "ComfyUI/models":
            return root / "models"
        return configured_path
    return root / "models" / dir_key


def _scan_dir_files(directory: Path) -> list[str]:
    if not directory.exists() or not directory.is_dir():
        return []
    files: list[str] = []
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in MODEL_FILE_EXTENSIONS:
            continue
        files.append(str(path.as_posix()))
    return sorted(files)


def _build_basename_index(files: list[str]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for file_path in files:
        key = Path(file_path).name.lower()
        index.setdefault(key, []).append(file_path)
    return index


def _build_stem_index(files: list[str]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for file_path in files:
        key = Path(file_path).stem.lower()
        index.setdefault(key, []).append(file_path)
    return index


def _match_model_name(
    model_name: str,
    candidate_dirs: list[str],
    scanned_index: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    model_basename = Path(model_name).name
    requested_lower = model_basename.lower()
    override_result = _resolve_path_override(model_name, model_basename, policy)
    if override_result is not None:
        return override_result

    alias_name, alias_applied = _resolve_alias_name(model_name, model_basename, policy)
    normalized_name = alias_name.lower() if bool(policy["case_insensitive"]) else alias_name
    normalized_stem = (
        Path(alias_name).stem.lower()
        if bool(policy["case_insensitive"])
        else Path(alias_name).stem
    )

    exact_candidates: list[str] = []
    stem_candidates: list[str] = []
    for dir_key in candidate_dirs:
        folder = scanned_index.get("folders", {}).get(dir_key, {})
        exact_candidates.extend(folder.get("basename_index", {}).get(normalized_name, []))
        if bool(policy["allow_stem_match"]):
            stem_candidates.extend(folder.get("stem_index", {}).get(normalized_stem, []))

    exact_candidates = sorted(set(exact_candidates))
    stem_candidates = sorted(set(stem_candidates))

    if len(exact_candidates) == 1:
        return {
            "status": "resolved",
            "match_type": "exact",
            "resolved_path": exact_candidates[0],
            "alias_applied": alias_applied,
        }
    if len(exact_candidates) > 1:
        return {
            "status": "ambiguous",
            "match_type": "exact",
            "candidates": exact_candidates,
            "alias_applied": alias_applied,
        }
    if len(stem_candidates) == 1:
        return {
            "status": "resolved",
            "match_type": "stem",
            "resolved_path": stem_candidates[0],
            "alias_applied": alias_applied,
        }
    if len(stem_candidates) > 1:
        return {
            "status": "ambiguous",
            "match_type": "stem",
            "candidates": stem_candidates,
            "alias_applied": alias_applied,
        }

    fuzzy_candidates = _find_fuzzy_candidates(
        requested_basename_lower=str(normalized_name),
        candidate_dirs=candidate_dirs,
        scanned_index=scanned_index,
        cutoff=float(policy["fuzzy_cutoff"]),
        enabled=bool(policy["allow_fuzzy_match"]),
    )
    if fuzzy_candidates:
        return {
            "status": "maybe",
            "match_type": "fuzzy",
            "candidates": fuzzy_candidates,
            "alias_applied": alias_applied,
        }

    return {
        "status": "missing",
        "match_type": "none",
        "candidates": [],
        "alias_applied": alias_applied,
        "requested_basename": requested_lower,
    }


def _find_fuzzy_candidates(
    requested_basename_lower: str,
    candidate_dirs: list[str],
    scanned_index: dict[str, Any],
    cutoff: float,
    enabled: bool,
) -> list[str]:
    if not enabled:
        return []
    all_names: list[str] = []
    name_to_paths: dict[str, list[str]] = {}
    for dir_key in candidate_dirs:
        folder = scanned_index.get("folders", {}).get(dir_key, {})
        basename_index = folder.get("basename_index", {})
        for name, paths in basename_index.items():
            all_names.append(name)
            name_to_paths.setdefault(name, []).extend(paths)

    if not all_names:
        return []

    close_names = difflib.get_close_matches(
        requested_basename_lower,
        sorted(set(all_names)),
        n=5,
        cutoff=cutoff,
    )
    out: list[str] = []
    for name in close_names:
        out.extend(name_to_paths.get(name, []))
    return sorted(set(out))


def _normalize_resolution_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    raw = policy if isinstance(policy, dict) else {}
    aliases = raw.get("aliases", {}) if isinstance(raw.get("aliases", {}), dict) else {}
    path_overrides = (
        raw.get("path_overrides", {})
        if isinstance(raw.get("path_overrides", {}), dict)
        else {}
    )
    return {
        "case_insensitive": bool(raw.get("case_insensitive", True)),
        "allow_stem_match": bool(raw.get("allow_stem_match", True)),
        "allow_fuzzy_match": bool(raw.get("allow_fuzzy_match", True)),
        "fuzzy_cutoff": float(raw.get("fuzzy_cutoff", 0.6)),
        "aliases": {str(k): str(v) for k, v in aliases.items()},
        "path_overrides": {str(k): str(v) for k, v in path_overrides.items()},
    }


def _resolve_alias_name(
    original_model_name: str,
    original_basename: str,
    policy: dict[str, Any],
) -> tuple[str, bool]:
    aliases = policy.get("aliases", {})
    keys = [
        original_model_name,
        original_basename,
        original_model_name.lower(),
        original_basename.lower(),
    ]
    for key in keys:
        if key in aliases and str(aliases[key]).strip():
            return Path(str(aliases[key]).strip()).name, True
    return original_basename, False


def _resolve_path_override(
    original_model_name: str,
    original_basename: str,
    policy: dict[str, Any],
) -> dict[str, Any] | None:
    overrides = policy.get("path_overrides", {})
    keys = [
        original_model_name,
        original_basename,
        original_model_name.lower(),
        original_basename.lower(),
    ]
    for key in keys:
        if key in overrides and str(overrides[key]).strip():
            candidate = Path(str(overrides[key]).strip())
            if candidate.exists() and candidate.is_file():
                return {
                    "status": "resolved",
                    "match_type": "path_override",
                    "resolved_path": str(candidate.as_posix()),
                    "override_applied": True,
                }
            return {
                "status": "missing",
                "match_type": "path_override_missing",
                "candidates": [str(candidate.as_posix())],
                "override_applied": True,
            }
    return None
