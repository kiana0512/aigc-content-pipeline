from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aigc2d.reporting import build_run_report, write_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a markdown report from run_manifest.json.")
    parser.add_argument("--run-manifest", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    markdown = build_run_report(args.run_manifest)
    output = args.output or str(Path(args.run_manifest).with_name("report.md"))
    path = write_report(output, markdown)
    print(f"report: {path}")


if __name__ == "__main__":
    main()
