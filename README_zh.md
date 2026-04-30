# GAME-AIGC-ASSET-WORKFLOW

本仓库是本地多模态 AIGC 实验工作台。当前主线是：在 ComfyUI 里手工验证 workflow，然后由 Python 侧管理参考图、分析产物、PromptBundle、任务表、workflow patch、批量调度、结果下载和复现记录。

## 核心边界

Python 仓库负责：

- 管理 `reference pack`
- 生成 `manifest.csv`、`prompt_sheet.csv`、`generation_tasks.csv`
- 调用 VLM / Tagger / Detection / Segmentation provider，当前可为 mock
- 生成标准 `processed/` 中间产物
- 导入和切换 ComfyUI API JSON
- 根据 active workflow metadata 做参数 patch
- 调用 ComfyUI HTTP API，下载输出，写 run manifest

ComfyUI 负责：

- 真正加载 checkpoint / VAE / LoRA / IPAdapter / ControlNet / Upscale / Video 模型
- 真正执行 text2img / img2img / upscale / video workflow
- 多节点 workflow 的节点连接

重要原则：workflow 必须先在 ComfyUI UI 里手工搭建、跑通、导出 API JSON。Python 不猜节点连接，只导入、注册、切换、patch 参数和批量调度。

## 一次完整使用流程

### 1. 准备模型路径

先检查并按本机路径修改：

- `configs/models/storage_roots.yaml`
- `configs/models/checkpoint_profiles.yaml`
- `configs/models/control_profiles.yaml`
- `configs/models/ipadapter_profiles.yaml`
- `configs/models/upscale_profiles.yaml`
- `configs/models/analysis_profiles.yaml`
- `configs/models/lora_profiles.yaml`

模型路径用 `root_key + relative_path`，不要在代码里写死绝对路径。例如 E 盘 ComfyUI 模型和 F 盘 Python 分析权重可以同时存在，只需要改 `storage_roots.yaml`。

### 2. 导入真实 ComfyUI workflow

把你从 ComfyUI 导出的真实 API JSON 放到例如：

```text
workflows/comfyui/incoming/firefly_img2img_28node_api.json
```

导入并设为 active：

```powershell
python scripts/import_comfy_workflow.py `
  --workflow-json workflows/comfyui/incoming/firefly_img2img_28node_api.json `
  --workflow-id firefly_img2img_v1 `
  --set-active
```

导入后会生成：

```text
workflows/comfyui/<workflow_id>.json
workflows/comfyui/registry/<workflow_id>.yaml
configs/workflows/active_workflow.yaml
```

如果导入的 API JSON 没有 `{{placeholder}}`，脚本会提示你去 registry metadata 里补 `patch_contract.node_inputs`。这不是错误，因为真实 ComfyUI 导出通常没有占位符，节点字段映射需要人工确认。

### 3. 检查 active workflow

```powershell
python scripts/inspect_workflow.py --active
```

重点看：

- 当前 active workflow id
- workflow JSON 路径
- workflow type
- optional modules：LoRA / IPAdapter / ControlNet / Upscale
- 可 patch 的 placeholder
- 缺失模型映射或缺失 patch contract 的 warning

### 4. 放入 reference pack 图片

当前默认 pack：

```text
data/reference_packs/firefly_v1/
  raw/      # 角色主图，建议 10 张左右
  style/    # 风格参考图，建议 20 张左右
```

也兼容更细目录：

```text
raw/official
raw/fanart
raw/screenshots
selected/init
selected/identity
selected/face
selected/mecha
selected/composition
selected/style
selected/background
```

如果只有一张流萤立绘，先放到 `raw/` 或 `raw/official/`。后续建议补 face、identity、composition、style、background 图。

### 5. 分析 reference pack

```powershell
python scripts/analyze_references.py --pack data/reference_packs/firefly_v1
```

脚本会自动创建并写入：

```text
data/reference_packs/firefly_v1/
  manifest.csv
  prompt_sheet.csv
  pack_summary.json
  processed/
```

raw 图每张会生成：

```text
processed/raw/<asset_id>/
  source.json
  detection.json
  subject_mask.png
  subject_alpha.png
  subject_crop_tight.png
  subject_crop_pad.png
  subject_square_1024.png
  halfbody_crop.png
  face_crop.png
  control_depth.png
  control_canny.png
  control_lineart.png
  control_pose.png
  caption.json
  tags.json
  analysis.json
  prompt_bundle.json
```

style 图每张会生成：

```text
processed/style/<asset_id>/
  source.json
  caption.json
  tags.json
  analysis.json
  style_palette.json
  prompt_bundle.json
```

当前 Detection / Segmentation / VLM / Tagger 可以是 mock provider，但输出结构保持稳定，后续可替换真实模型。

### 6. 生成 generation tasks

默认每张 raw 只取 top-3 style，避免 10 x 20 一次爆量：

```powershell
python scripts/build_tasks.py --pack data/reference_packs/firefly_v1 --mode topk_style_per_raw --topk 3
```

输出：

```text
data/reference_packs/firefly_v1/generation_tasks.csv
```

这个文件可以人工修改，例如绑定指定 style、替换 prompt bundle、调整 notes。

### 7. Dry-run 检查 patched workflow

```powershell
python scripts/batch_generate_stub.py `
  --tasks data/reference_packs/firefly_v1/generation_tasks.csv `
  --dry-run
```

dry-run 不调用 ComfyUI，只会写：

```text
results/runs/<run_id>/
  task_000.workflow.json
  batch_summary.json
  run_manifest.json
```

请先打开 `task_000.workflow.json` 检查 patch 是否写进正确节点。

### 8. Execute 调用 ComfyUI

确认 patched workflow 正确后执行：

```powershell
python scripts/batch_generate_stub.py `
  --tasks data/reference_packs/firefly_v1/generation_tasks.csv `
  --execute `
  --download-outputs `
  --comfy-url http://127.0.0.1:8188 `
  --timeout-sec 600
```

如果 ComfyUI 是 `http://127.0.0.1:8000`，替换 `--comfy-url`。

结果写入：

```text
results/runs/<run_id>/
  run_manifest.json
  batch_summary.json
  task_000.workflow.json
  outputs/
```

### 9. 生成报告

```powershell
python scripts/generate_report.py --run-manifest results/runs/<run_id>/run_manifest.json
```

## 当前真实能力与 mock 边界

真实落地：

- workflow 导入 / registry / active 切换
- active workflow inspect
- reference pack 扫描
- manifest / prompt_sheet / generation_tasks 自动生成
- workflow patch dry-run
- ComfyUI HTTP API submit / poll / download
- run manifest / batch summary / patched workflow 保存

Mock/provider：

- detection
- segmentation
- VLM caption / critique
- tagger
- palette analysis
- CLIP / aesthetic / technical / VLM / wallpaper scoring

这些 mock 不影响流程跑通，后续替换 provider 即可。

## 文件职责

- `src/aigc2d/workflow_registry.py`：workflow 导入、注册、active 切换。
- `src/aigc2d/workflow_inspector.py`：检查 active workflow 和风险提示。
- `src/aigc2d/workflow_runtime.py`：合并配置、模型、任务行并 patch workflow。
- `src/aigc2d/reference_pack.py`：扫描 reference pack，生成 manifest row。
- `src/aigc2d/reference_analysis.py`：生成 processed 中间产物。
- `src/aigc2d/prompt_bundle.py`：PromptBundle JSON contract。
- `src/aigc2d/model_profiles.py`：storage root、profile、LoRA 配置解析。
- `src/aigc2d/comfy_client.py`：ComfyUI HTTP API。
- `scripts/import_comfy_workflow.py`：导入并切换 workflow。
- `scripts/inspect_workflow.py`：检查当前 active workflow。
- `scripts/analyze_references.py`：分析 reference pack。
- `scripts/build_manifest.py`：只生成 manifest。
- `scripts/build_tasks.py`：生成 generation_tasks。
- `scripts/batch_generate_stub.py`：dry-run / execute 批量生成。
