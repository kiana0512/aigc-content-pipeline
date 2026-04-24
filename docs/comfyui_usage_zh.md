# ComfyUI 操作手册（精简版）

## 1. 前提
- ComfyUI 已运行，API 可访问（默认 `http://127.0.0.1:8000`）
- 使用 API 格式 workflow JSON（不是 UI `nodes` 格式）

## 2. 常用命令
### 2.1 生成批量 patched workflows
```powershell
python scripts/run_batch_generation.py --config configs/z_image_turbo_api.yaml --prompt-pack examples/prompt_packs/z_image_turbo_prompt_pack.csv --mode workflow_import_pipeline --run-name z_image_turbo_batch_test
```

### 2.2 批量提交
```powershell
python scripts/run_batch_generation.py --config configs/z_image_turbo_api.yaml --prompt-pack examples/prompt_packs/z_image_turbo_prompt_pack.csv --mode submit --run-name z_image_turbo_batch_test
```

## 3. 关键行为
- `workflow_import_pipeline` 会为每个 item 生成独立文件：
  - `patched_workflows/item_0001_patched_workflow.json`
  - `patch_reports/item_0001_patch_report.json`
- `submit` 会按 item 全量提交，不会只提交第一条。
- 当 `manifest` 是多条但仅有单个 legacy `patched_workflow.json` 时，程序会告警并报错。

## 4. 参数来源规则（简化）
- `positive_prompt` / `negative_prompt`：优先 CSV，其次 config/workflow fallback
- `filename_prefix`：优先 CSV，没有则用 config 默认并附加 item 标识
- `seed`：默认来自 config，可被 CSV `seed` 覆盖
- `width/height/batch_size/steps/cfg/sampler/scheduler/denoise`：来自 config

## 5. 故障排查
- 检查 `run_manifest.json` 是否含每个 item 的 `patched_workflow_path`
- 检查 `patched_workflows/` 是否数量与 CSV 行数一致
- 检查 `comfyui_submit_results.json`：
  - `total_items`
  - `submitted_items`
  - `failed_items`
  - `results[]`
