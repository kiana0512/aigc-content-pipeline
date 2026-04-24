# game-aigc-asset-workflow

精简后的 ComfyUI API 批量生成仓库。
当前只保留一条主链路：`prompt pack -> patch workflow -> submit`。

## 保留能力
- 读取 prompt pack 多行任务
- 为每个 item 生成独立 patched workflow
- 批量提交到 ComfyUI `/prompt`
- 产出每个 item 的 patch 报告与提交结果

## Prompt 覆盖规则（重要）
- 原始 workflow JSON 里的 prompt 只是模板默认示例。
- 运行时如果提供 prompt pack，最终 prompt 以 prompt pack 为准。
- 一句话：原始 JSON 决定怎么生成，CSV 决定生成什么。

## 目录（已精简）
- `configs/`：两套可运行配置 + 对应 node map
- `workflows/comfyui/`：两份真实 API workflow
- `examples/prompt_packs/`：两份示例 prompt pack
- `scripts/run_batch_generation.py`：唯一入口脚本
- `src/generation/`：核心实现
- `tests/`：当前主链路测试
- `results/runs/`：运行输出目录（默认仅保留 `.gitkeep`）

## 快速开始（PowerShell）
1. 生成按 item 拆分的 patched workflows
```powershell
python scripts/run_batch_generation.py --config configs/z_image_turbo_api.yaml --prompt-pack examples/prompt_packs/z_image_turbo_prompt_pack.csv --mode workflow_import_pipeline --run-name z_image_turbo_batch_test
```

2. 批量 submit 到 ComfyUI
```powershell
python scripts/run_batch_generation.py --config configs/z_image_turbo_api.yaml --prompt-pack examples/prompt_packs/z_image_turbo_prompt_pack.csv --mode submit --run-name z_image_turbo_batch_test
```

3. 从 workflow 默认 prompt 导出一行 prompt pack（可选）
```powershell
python scripts/run_batch_generation.py --config configs/z_image_turbo_api.yaml --mode export_default_prompt_pack
```

## 关键输出
- `results/runs/<run_name>/run_manifest.json`
- `results/runs/<run_name>/patched_workflows/item_0001_patched_workflow.json`
- `results/runs/<run_name>/patch_reports/item_0001_patch_report.json`
- `results/runs/<run_name>/patch_report.md`
- `results/runs/<run_name>/comfyui_submit_results.json`

## 文档
- [项目结构与使用说明（中文）](/d:/RT/game-aigc-asset-workflow/docs/project_structure_and_usage_zh.md)
- [ComfyUI 操作手册（中文）](/d:/RT/game-aigc-asset-workflow/docs/comfyui_usage_zh.md)
