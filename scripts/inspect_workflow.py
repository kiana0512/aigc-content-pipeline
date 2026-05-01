from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aigc2d.config import load_yaml
from aigc2d.workflow_inspector import check_model_mapping, inspect_active_workflow
from aigc2d.workflow_registry import WorkflowRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect active or registered ComfyUI workflow metadata.")
    parser.add_argument("--active", action="store_true")
    parser.add_argument("--workflow-id", default="")
    parser.add_argument("--task-config", default="configs/generation/firefly_wallpaper.yaml")
    parser.add_argument("--show-candidates", action="store_true")
    parser.add_argument("--show-graph", action="store_true")
    args = parser.parse_args()

    try:
        if args.active or not args.workflow_id:
            info = inspect_active_workflow()
        else:
            info = __import__("aigc2d.workflow_inspector", fromlist=["inspect_workflow"]).inspect_workflow(
                WorkflowRegistry().load_metadata(args.workflow_id)
            )
    except Exception as exc:
        raise SystemExit(f"检查失败：{exc}\n可先运行 scripts/import_comfy_workflow.py --workflow-json <json> --workflow-id <id> --set-active")

    model_warnings = check_model_mapping(load_yaml(args.task_config) if Path(args.task_config).exists() else {})
    print(f"workflow id: {info['workflow_id']}")
    print(f"workflow path: {Path(info['workflow_path']).resolve()}")
    print(f"registry path: {Path(info['registry_path']).resolve()}")
    print(f"type: {info['workflow_type']}")
    print("detected modules:")
    for name, enabled in info["detected_modules"].items():
        print(f"- {name}: {enabled}")
    print("patch contract node_inputs:")
    node_inputs = (info.get("patch_contract") or {}).get("node_inputs", {})
    if node_inputs:
        for field, mapping in node_inputs.items():
            required = "optional" if mapping.get("optional", True) else "required"
            print(f"- {field}: node {mapping.get('node_id')}.{mapping.get('input')} ({required}, {mapping.get('source', 'unknown')})")
    else:
        print("- 未发现自动映射；请编辑 registry patch_contract.node_inputs。")
    missing_required = [
        field for field in ["positive_prompt", "negative_prompt", "init_image"]
        if field not in node_inputs
    ]
    if missing_required:
        print("missing key fields:")
        for field in missing_required:
            print(f"- {field}")
    if args.show_candidates:
        print("candidates:")
        for name, value in (info.get("candidates") or {}).items():
            print(f"- {name}: {value}")
        print("ambiguous candidates:")
        for name, value in (info.get("ambiguous_candidates") or {}).items():
            print(f"- {name}: {value}")
    else:
        ambiguous = info.get("ambiguous_candidates") or {}
        print("ambiguous candidates:")
        if any(ambiguous.values()):
            for name, value in ambiguous.items():
                if value:
                    print(f"- {name}: {len(value) if isinstance(value, list) else value}")
        else:
            print("- none")
    if args.show_graph:
        print("graph:")
        print(f"- upstream_map: {info.get('graph', {}).get('upstream_map', {})}")
        print(f"- downstream_map: {info.get('graph', {}).get('downstream_map', {})}")
    warnings = [*info.get("warnings", []), *model_warnings]
    errors = info.get("errors", [])
    if errors:
        print("errors:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(2)
    if warnings:
        print("warnings:")
        for warning in warnings:
            print(f"- {warning}")
    print("next steps:")
    print("- python scripts/analyze_references.py --pack data/reference_packs/firefly_v1")
    print("- python scripts/build_tasks.py --pack data/reference_packs/firefly_v1 --mode single_init_all_styles")
    print("- python scripts/batch_generate_stub.py --tasks data/reference_packs/firefly_v1/generation_tasks.csv --dry-run")


if __name__ == "__main__":
    main()
