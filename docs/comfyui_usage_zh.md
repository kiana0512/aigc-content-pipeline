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

### 2.3 导出 workflow 默认 prompt 为一行 CSV（可选）
```powershell
python scripts/run_batch_generation.py --config configs/z_image_turbo_api.yaml --mode export_default_prompt_pack
```

## 3. 关键行为
- `workflow_import_pipeline` 会为每个 item 生成独立文件：
  - `patched_workflows/item_0001_patched_workflow.json`
  - `patch_reports/item_0001_patch_report.json`
- `submit` 会按 item 全量提交，不会只提交第一条。
- 当 `manifest` 是多条但仅有单个 legacy `patched_workflow.json` 时，程序会告警并报错。
- 原始 workflow JSON 里的 prompt 只是模板默认示例。
- 运行时如果提供 prompt pack，最终 prompt 以 prompt pack 为准。
- 原始 JSON 决定怎么生成，CSV 决定生成什么。

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

## 6. 接入一个新的 ComfyUI API workflow
1. 把新的 API workflow JSON 放到 `workflows/comfyui/`

2. 运行 scaffold（自动生成 config/node_map/prompt_pack/report）
```powershell
python scripts/run_batch_generation.py --mode scaffold_workflow --workflow-json workflows/comfyui/my_new_workflow_api.json --slug my_new_workflow
```

3. 先用默认 prompt 复现 workflow 导出图
```powershell
python scripts/run_batch_generation.py --config configs/my_new_workflow_api.yaml --prompt-pack examples/prompt_packs/my_new_workflow_default_from_workflow.csv --mode workflow_import_pipeline --run-name my_new_workflow_default_round1
python scripts/run_batch_generation.py --config configs/my_new_workflow_api.yaml --prompt-pack examples/prompt_packs/my_new_workflow_default_from_workflow.csv --mode submit --run-name my_new_workflow_default_round1
```

4. 再用可编辑 prompt pack 做批量生成
```powershell
python scripts/run_batch_generation.py --config configs/my_new_workflow_api.yaml --prompt-pack examples/prompt_packs/my_new_workflow_prompt_pack.csv --mode workflow_import_pipeline --run-name my_new_workflow_round1
python scripts/run_batch_generation.py --config configs/my_new_workflow_api.yaml --prompt-pack examples/prompt_packs/my_new_workflow_prompt_pack.csv --mode submit --run-name my_new_workflow_round1
```

可选参数：
- `--force`：覆盖已有 scaffold 文件
- `--validate`：生成后自动跑一次 pipeline 验证
- `--submit-after-validate`：验证后自动 submit
