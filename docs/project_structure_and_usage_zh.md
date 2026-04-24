# 项目结构与使用说明（精简版）

## 1. 项目定位
本仓库是 ComfyUI 的外部批量调度器，不是 ComfyUI 本体。

当前保留能力：
- 读取 prompt pack
- patch ComfyUI API workflow
- 批量 submit
- 输出可追踪报告

## 2. 当前目录结构
- `configs/`
  - `z_image_turbo_api.yaml`
  - `qwen_image_illustration_lora_api.yaml`
  - `node_maps/`
- `workflows/comfyui/`
  - `image_z_image_turbo_api.json`
  - `qwen_image_illustration_lora_api.json`
- `examples/prompt_packs/`
- `scripts/run_batch_generation.py`
- `src/generation/`
- `tests/`
- `results/runs/.gitkeep`

## 3. 运行顺序
1. `workflow_import_pipeline`
2. `submit`

示例：
```powershell
python scripts/run_batch_generation.py --config configs/z_image_turbo_api.yaml --prompt-pack examples/prompt_packs/z_image_turbo_prompt_pack.csv --mode workflow_import_pipeline --run-name z_image_turbo_batch_test
python scripts/run_batch_generation.py --config configs/z_image_turbo_api.yaml --prompt-pack examples/prompt_packs/z_image_turbo_prompt_pack.csv --mode submit --run-name z_image_turbo_batch_test
```

## 4. 结果检查
- `run_manifest.json`：每个 item 的标准化参数、patched workflow 路径
- `patched_workflows/item_XXXX_patched_workflow.json`：每条任务的提交载荷
- `patch_reports/item_XXXX_patch_report.json`：每条任务 patch 结果
- `patch_report.md`：批量总报告
- `comfyui_submit_results.json`：批量提交结果

## 5. Prompt Pack 推荐字段
推荐：
- `id`
- `positive_prompt`
- `negative_prompt`
- `filename_prefix`

兼容别名：
- 正向：`positive_prompt_text` / `prompt` / `prompt_text` / `text`
- 负向：`negative_prompt_text` / `neg_prompt` / `negative` / `negative_text`
- 文件名前缀：`output_prefix` / `file_prefix`
