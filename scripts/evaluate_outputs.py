from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.report_builder import build_markdown_report, save_markdown_report
from src.generation.result_parser import build_directory_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a simple evaluation summary for output images."
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        required=True,
        help="Directory containing generated images.",
    )
    parser.add_argument(
        "--report-out",
        type=str,
        required=True,
        help="Path to output markdown report.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_dir = Path(args.input_dir)
    report_out = Path(args.report_out)
    report_out.parent.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    summary = build_directory_summary(input_dir)
    if summary["num_images"] <= 0:
        print(f"[WARN] No images found in: {input_dir}")
        return

    report_content = build_markdown_report(
        title="Output Evaluation Report",
        summary={
            "input_dir": summary["input_dir"],
            "num_images": summary["num_images"],
            "avg_size_mb": f"{summary['avg_size_mb']:.2f}",
            "extension_distribution": summary["extension_distribution"],
            "resolution_distribution": summary["resolution_distribution"],
            "sample_files": summary["sample_files"],
        },
    )
    save_markdown_report(report_content, report_out)

    print(f"[OK] Evaluation report written to: {report_out}")


if __name__ == "__main__":
    main()
