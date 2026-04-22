# game-aigc-asset-workflow

面向游戏资产生成的 AIGC 实验工作流仓库，当前阶段聚焦 ComfyUI + Stable Diffusion/SDXL 的基线接入与 workflow-first 自动化落地。

## 项目定位

本仓库不是 ComfyUI 本体，也不是“一站式全模型平台”。  
当前目标是构建一个可复用、可追踪、可迭代的游戏资产生成实验流水线，重点场景包括：

- UI icon 基线生成
- 角色概念图（character concept）基线生成
- 提示词模板化与批量出图
- 结果记录、索引与对比

## 当前已实现能力

- ComfyUI API workflow patch（仅接受 API 格式 JSON）
- placeholder / UI workflow JSON 严格拒绝
- `manual_map` / `auto_detect` 双模式 patch
- workflow-first 工具链：
  - `inspect_workflow`
  - `resolve_models`
  - `suggest_mapping`
  - `auto_patch_workflow`
  - `workflow_import_pipeline`
- 模型目录兼容表达（`comfyui_models`）与目录检查
- LoRA / ControlNet 接口预留（默认关闭）

## 目录结构

```text
configs/         配置文件（任务配置、node map、workflow-first 示例）
data/            数据目录（raw/interim/processed/metadata）
docs/            使用文档、路线图、实验日志、简历描述
prompts/         prompt 模板与模板片段
scripts/         CLI 入口脚本
src/             核心实现模块
tests/           本地测试
workflows/       ComfyUI workflow JSON（含占位与示例）
```

## 快速开始

1. 准备好真实 ComfyUI API workflow JSON（`File -> Export (API)` 导出）
2. 配置 `configs/*.yaml` 中的 `comfyui.workflow_json` / `node_map`
3. 运行基础流程

```bash
# 1) 仅生成 manifest
python scripts/run_batch_generation.py \
  --config configs/sdxl_icon.yaml \
  --prompt-pack outputs/prompt_pack/ui_icons/prompt_pack.csv \
  --mode manifest

# 2) 检查 workflow 结构
python scripts/run_batch_generation.py \
  --config configs/sdxl_icon.yaml \
  --mode inspect_workflow

# 3) 扫描并匹配本地模型
python scripts/run_batch_generation.py \
  --config configs/sdxl_icon.yaml \
  --mode resolve_models \
  --comfyui-root D:/ComfyUI

# 4) 生成 mapping 建议
python scripts/run_batch_generation.py \
  --config configs/sdxl_icon.yaml \
  --mode suggest_mapping

# 5) 自动 patch（workflow-first）
python scripts/run_batch_generation.py \
  --config configs/sdxl_icon.yaml \
  --prompt-pack outputs/prompt_pack/ui_icons/prompt_pack.csv \
  --mode auto_patch_workflow
```

## workflow_import_pipeline（一键小闭环）

`workflow_import_pipeline` / `prepare_workflow_import` 会顺序执行：

1. inspect_workflow
2. resolve_models
3. suggest_mapping
4. auto_patch_workflow（默认 patch manifest 第一条）

输出目录统一为：

`results/runs/<run_name>/`

包含：

- `workflow_inspection.json`
- `model_resolution.json`
- `mapping_suggestion.yaml`
- `mapping_diff.md`
- `mapping_manual_review.yaml`
- `patch_report.json`
- `patch_report.md`
- `patched_workflow.json`
- `run_manifest.json`

## 重要边界

- 仅支持真实 ComfyUI API workflow JSON
- UI workflow JSON（含 `nodes` 列表）会直接报错
- placeholder workflow JSON 会直接报错
- submit 模式为实验性（smoke test 级别）
- 当前不做 UE5 自动化
- LoRA / ControlNet 当前是接口预留，不是完整训练/部署平台

## 文档入口

- `docs/comfyui_usage_zh.md`：中文使用总览（推荐先读）
- `docs/workflow_import_zh.md`：workflow-first 导入与自动化详解
- `docs/comfyui_baseline_setup.md`：ComfyUI 基线接入说明
- `docs/comfyui_model_folders.md`：模型目录说明与任务-目录矩阵
- `docs/experiment_log.md`：实验记录
