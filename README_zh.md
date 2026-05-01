# GAME-AIGC-ASSET-WORKFLOW

本仓库是本地多模态 AIGC 实验工作台。当前主线是：在 ComfyUI 里手工验证 workflow，然后由 Python 侧管理参考图、分析产物、PromptBundle、任务表、workflow patch、批量调度、结果下载和复现记录。

## 核心边界

Python 仓库负责：

- 管理 `reference pack`
- 生成 `manifest.csv`、`prompt_sheet.csv`、`generation_tasks.csv`
- 调用真实 VLM / Tagger / Detection / Segmentation / Matting provider
- 生成标准 `processed/` 中间产物
- 导入和切换 ComfyUI API JSON
- 根据 active workflow metadata 做参数 patch
- 调用 ComfyUI HTTP API，下载输出，写 run manifest

ComfyUI 负责：

- 真正加载 checkpoint / VAE / LoRA / IPAdapter / ControlNet / Upscale / Video 模型
- 真正执行 text2img / img2img / upscale / video workflow
- 多节点 workflow 的节点连接

重要原则：workflow 必须先在 ComfyUI UI 里手工搭建、跑通、导出 API JSON。Python 不改节点连接，也不在运行时代码里写死 node_id；它会读取 API JSON，自动分析节点结构，生成 registry / patch contract，再按 registry patch 参数和批量调度。

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
workflows/comfyui/_raw_exports/<your_workflow>.json
```

导入并设为 active：

```powershell
python scripts/import_comfy_workflow.py `
  --workflow-json workflows/comfyui/_raw_exports/<your_workflow>.json `
  --workflow-id <workflow_id> `
  --set-active `
  --auto-map
```

导入后会生成：

```text
workflows/comfyui/registered/<workflow_id>.json
workflows/comfyui/registry/<workflow_id>.yaml
configs/workflows/active_workflow.yaml
```

registry 里会记录 `node_inventory`、`detected_modules`、`patch_contract.node_inputs`、`candidates`、`ambiguous_candidates` 和 `warnings`。自动解析不是魔法：能确定的字段会自动映射，有歧义的 prompt / image / sampler 角色会写入 warnings，需要你检查 registry。

### 3. 检查 active workflow

```powershell
python scripts/inspect_workflow.py --active --show-candidates
```

重点看：

- 当前 active workflow id
- workflow JSON 路径
- workflow type
- optional modules：LoRA / IPAdapter / ControlNet / Upscale
- 自动映射的 `patch_contract.node_inputs`
- 候选节点、歧义节点和 warning
- registry 指向的 node_id / input key 是否存在

### 4. 放入 reference pack 图片

当前默认 pack：

```text
data/reference_packs/firefly_v1/
  selected/init/
  selected/identity/
  selected/style/
  raw/
  style/
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
init
identity
face
mecha
composition
background
```

如果只有一张流萤立绘，先放到 `raw/` 或 `raw/official/`。后续建议补 face、identity、composition、style、background 图。

### 5. 分析 reference pack

```powershell
python scripts/analyze_references.py --pack data/reference_packs/firefly_v1
```

默认等价于：

```powershell
python scripts/analyze_references.py --pack data/reference_packs/firefly_v1 --provider real --device cuda --strict-real
```

真实模式会加载本地模型并真实推理，速度不会像 mock 那样瞬间完成。当前默认主链路是 `SAM3.1 + BiRefNet + WD14 + Qwen2.5-VL / Florence`，不再默认依赖 GroundingDINO：

- `weights/segmentation/sam3.1`，必要时可配置 `sam3`
- `weights/segmentation/BiRefNet`
- `weights/tagger/wd14_tagger_with_embeddings`
- `weights/vlm/Qwen2.5-VL-7B-Instruct` 或 Florence

`raw/screenshots/` 会被重点用于提取角色主体性、动作、镜头、构图、场景背景、特效光照和战斗氛围。GroundingDINO 代码保留为未来可选扩展，但默认禁用。

SAM3 / SAM3.1 不安装在当前主仓库环境里，而是运行在独立 conda 环境 `sam3` 中。主仓库通过 `conda run` 调用外部 CLI：

```powershell
python scripts/check_sam3_env.py `
  --python-exe "D:/Program Files/anaconda3/envs/sam3/python.exe" `
  --sam3-repo-dir "F:/python_project/game-aigc-asset-workflow/sam3" `
  --sam3-model-root "F:/python_project/game-aigc-asset-workflow/weights/segmentation/sam3.1" `
  --offline
conda run -n sam3 python scripts/sam3_segment_cli.py `
  --image data/reference_packs/firefly_v1/selected/init/firefly_poster_01.jpg `
  --out-dir outputs/debug_sam3/firefly_poster_01 `
  --sam3-repo-dir "F:/python_project/game-aigc-asset-workflow/sam3" `
  --sam3-model-root "F:/python_project/game-aigc-asset-workflow/weights/segmentation/sam3.1" `
  --offline `
  --prompts "person" "anime character" "main subject" `
  --device cuda
```

`sam3_repo_dir` 指向 SAM3 源码目录，`sam3_model_root` 指向本地 SAM3/SAM3.1 权重目录，两者不是同一个概念。CLI 会拒绝无本地路径调用 `build_sam3_image_model()`，因为那可能访问 HuggingFace 的 `facebook/sam3`。如果看到 401 / gated repo，优先检查 `sam3_model_root`、`sam3_config_path`、`sam3_checkpoint_path`。

如果模型缺失、依赖缺失、加载失败或推理失败，strict-real 会直接报错并停止，不会写 `mock: true` 的假分析文件。

只有显式指定时才允许 mock：

```powershell
python scripts/analyze_references.py --pack data/reference_packs/firefly_v1 --provider mock
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

当前 `analyze_references.py` 默认使用真实 provider。mock 只用于单元测试或调试，必须显式传 `--provider mock`。

### 6. 生成 generation tasks

只有一张主图 + 多张风格图时，使用 `single_init_all_styles`：

```powershell
python scripts/build_tasks.py --pack data/reference_packs/firefly_v1 --mode single_init_all_styles
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
- SAM3.1 / BiRefNet / WD14 / VLM 真实 reference analysis
- manifest / prompt_sheet / generation_tasks 自动生成
- workflow patch dry-run
- ComfyUI HTTP API submit / poll / download
- run manifest / batch summary / patched workflow 保存

仍是 mock/provider 或显式调试：

- `analyze_references.py --provider mock`：仅测试/调试，必须显式指定
- CLIP / aesthetic / technical / VLM / wallpaper scoring

默认 reference analysis 已不是 mock。真实模式失败会直接报错，不会静默 fallback。

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
