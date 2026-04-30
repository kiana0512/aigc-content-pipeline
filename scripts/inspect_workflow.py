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
    print(f"type: {info['workflow_type']}")
    print("optional modules:")
    for name, enabled in info["optional_modules"].items():
        print(f"- {name}: {'yes' if enabled else 'no'}")
    print("required/known placeholders:")
    if info["placeholders"]:
        for item in info["placeholders"]:
            print(f"- {item}")
    else:
        print("- 未发现 {{placeholder}}；请在 registry metadata 的 patch_contract.node_inputs 中补充节点映射。")
    warnings = [*info.get("warnings", []), *model_warnings]
    if warnings:
        print("warnings:")
        for warning in warnings:
            print(f"- {warning}")
    print("next steps:")
    print("- python scripts/analyze_references.py --pack data/reference_packs/firefly_v1")
    print("- python scripts/build_tasks.py --pack data/reference_packs/firefly_v1")
    print("- python scripts/batch_generate_stub.py --tasks data/reference_packs/firefly_v1/generation_tasks.csv --dry-run")


if __name__ == "__main__":
    main()
