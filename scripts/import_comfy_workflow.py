from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aigc2d.workflow_registry import WorkflowRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Import and optionally activate a verified ComfyUI API workflow JSON.")
    parser.add_argument("--workflow-json", required=True)
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--set-active", action="store_true")
    args = parser.parse_args()

    try:
        registry = WorkflowRegistry()
        metadata = registry.import_workflow(args.workflow_json, args.workflow_id, set_active=args.set_active)
    except Exception as exc:
        raise SystemExit(
            f"Import failed: {exc}\n"
            "Please confirm this JSON is a ComfyUI API prompt exported after manual UI validation."
        )

    print(f"imported workflow: {metadata.workflow_id}")
    print(f"workflow path: {Path(metadata.workflow_json_path).resolve()}")
    print(f"metadata path: {registry.metadata_path(metadata.workflow_id).resolve()}")
    if args.set_active:
        print("active workflow updated.")
        print(f"active config: {registry.active_path.resolve()}")
    if metadata.warnings:
        print("warnings:")
        for warning in metadata.warnings:
            print(f"- {warning}")
    print("")
    print("next steps:")
    print("1. Put character images in data/reference_packs/firefly_v1/raw or raw/official")
    print("2. Put style images in data/reference_packs/firefly_v1/style or selected/style")
    print("3. Run: python scripts/analyze_references.py --pack data/reference_packs/firefly_v1")
    print("4. Run: python scripts/build_tasks.py --pack data/reference_packs/firefly_v1")
    print("5. Dry-run: python scripts/batch_generate_stub.py --tasks data/reference_packs/firefly_v1/generation_tasks.csv --dry-run")
    print("6. Execute: python scripts/batch_generate_stub.py --tasks data/reference_packs/firefly_v1/generation_tasks.csv --execute --download-outputs")
    print("")
    print("To switch workflow again, rerun this script with --set-active.")


if __name__ == "__main__":
    main()
