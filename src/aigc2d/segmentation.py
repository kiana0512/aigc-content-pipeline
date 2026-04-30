from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol


class SegmentationProvider(Protocol):
    def segment(self, image_path: str | Path, output_dir: str | Path) -> dict[str, str]:
        ...


class MockSegmentationProvider:
    """Contract-compatible segmentation stub.

    It writes deterministic placeholder artifacts by copying the source image.
    Replace with SAM/BiRefNet providers without changing downstream contracts.
    """

    def segment(self, image_path: str | Path, output_dir: str | Path) -> dict[str, str]:
        source = Path(image_path)
        root = Path(output_dir)
        paths = {
            "mask": root / "masks" / f"{source.stem}_mask.png",
            "crop": root / "crops" / f"{source.stem}_crop{source.suffix}",
            "alpha": root / "alpha" / f"{source.stem}_alpha.png",
        }
        for path in paths.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            if source.exists():
                shutil.copy2(source, path)
            else:
                path.write_bytes(b"")
        return {key: str(path) for key, path in paths.items()}
