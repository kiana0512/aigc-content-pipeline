from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Python version and required packages.")
    parser.parse_args()
    print(f"Python: {sys.version.split()[0]}")
    print(f"Executable: {sys.executable}")
    for package in ["yaml", "pydantic", "requests", "pytest"]:
        ok = importlib.util.find_spec(package) is not None
        print(f"{package}: {'OK' if ok else 'MISSING'}")
    for path in ["configs", "data/benchmarks", "workflows/comfyui", "results/runs"]:
        print(f"{path}: {'OK' if Path(path).exists() else 'MISSING'}")


if __name__ == "__main__":
    main()
