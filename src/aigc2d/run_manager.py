from __future__ import annotations

import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, write_json


def make_run_id(prefix: str = "run") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{stamp}_{uuid.uuid4().hex[:8]}"


def get_git_commit(cwd: str | Path = PROJECT_ROOT) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


class RunManager:
    def __init__(self, runs_root: str | Path = PROJECT_ROOT / "results" / "runs") -> None:
        self.runs_root = Path(runs_root)

    def run_dir(self, run_id: str) -> Path:
        path = self.runs_root / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_run_manifest(self, run_id: str, payload: dict[str, Any]) -> Path:
        enriched = {
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "git_commit": get_git_commit(),
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            **payload,
        }
        return write_json(self.run_dir(run_id) / "run_manifest.json", enriched)

    def write_batch_summary(self, run_id: str, items: list[dict[str, Any]]) -> Path:
        return write_json(
            self.run_dir(run_id) / "batch_summary.json",
            {"run_id": run_id, "count": len(items), "items": items},
        )
