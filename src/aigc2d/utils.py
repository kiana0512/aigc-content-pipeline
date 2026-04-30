from __future__ import annotations

import random
from pathlib import Path


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def resolve_seed(seed: int) -> int:
    return random.randint(0, 2**32 - 1) if seed < 0 else seed
