from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .comfy_client import ComfyClient


def ensure_comfy_input_image(
    image_path: str | Path,
    comfy_input_dir: str | Path | None = None,
    run_id: str | None = None,
    pack_id: str | None = None,
    comfy_url: str = "http://127.0.0.1:8188",
    dry_run: bool = False,
    client: ComfyClient | None = None,
) -> str:
    source = Path(image_path)
    if not source.exists():
        raise FileNotFoundError(f"Input image not found: {source}")
    target_name = _hashed_name(source)
    subfolder = f"aigc2d/{run_id or pack_id or 'inputs'}"
    subfolder_norm = subfolder.replace("\\", "/")
    if comfy_input_dir:
        target_dir = Path(comfy_input_dir) / subfolder_norm
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target_dir / target_name)
        return f"{subfolder_norm}/{target_name}".replace("\\", "/")
    if dry_run:
        return f"{subfolder_norm}/{target_name}".replace("\\", "/")

    if client is not None:
        payload = client.upload_image(source, subfolder=subfolder_norm, filename=target_name)
        return client.load_image_value_from_upload_result(payload)

    return _upload_via_requests(source, target_name, subfolder_norm, comfy_url.rstrip("/"))


def _hashed_name(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:10]
    return f"{digest}_{path.name}"


def _upload_via_requests(source: Path, filename: str, subfolder: str, comfy_url: str) -> str:
    """Legacy upload when no ComfyClient instance is provided."""
    with source.open("rb") as fh:
        response = requests.post(
            f"{comfy_url}/upload/image",
            files={"image": (filename, fh)},
            data={"overwrite": "true", "subfolder": subfolder, "type": "input"},
            timeout=120,
        )
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        returned_subfolder = str(data.get("subfolder") or subfolder).replace("\\", "/")
        name = str(data.get("name") or data.get("filename") or filename)
        combined = f"{returned_subfolder}/{name}".strip("/").replace("\\", "/").replace("//", "/")
        return combined
    return f"{subfolder}/{filename}".replace("\\", "/")

