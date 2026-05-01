# Pipeline Contract

本文档定义 AIGC 2D 生成工作台的稳定契约。实现以 `src/aigc2d/*` 为准。

## 工程边界

Python 仓库负责参考图资产管理、分析、prompt bundle、workflow 参数 patch、调度、下载、评分、复现、检索和 agent 建议。ComfyUI 负责模型加载与真正生成。

多节点 ComfyUI workflow 必须先在 ComfyUI UI 手工搭建并验证，再导出 API JSON。Python 不改 ComfyUI 节点连接，也不在核心代码里写死 node_id；它导入 API JSON 后自动分析节点结构，生成 registry / patch contract，运行时只按 registry patch。

## 核心数据结构

- `ExperimentConfig`：一次实验的配置，包括 `mode`、`workflow_name`、模型、VAE、尺寸、seed、steps、cfg、sampler、scheduler、denoise、batch、sweep、style preset、negative prompt、评分权重和 ComfyUI base_url。
- `BenchmarkItem`：benchmark 输入项，包含 `id`、`character_name`、`image_path`、`source`、`tags`、`notes`。
- `PromptSpec`：最终 prompt，包含 `positive_prompt`、`negative_prompt`、分层 `layers`、`metadata`。
- `GenerationTask`：一次可执行生成任务，包含 workflow、模型、prompt、输入图、生成参数、ControlNet/IP-Adapter 参数。
- `ScoreRecord`：单张输出图的统一评分记录，包含 text-image alignment、image-image similarity、structural similarity、VLM judge 和 weighted score。
- `RunManifest`：一次 run 的持久化记录，保存 `run_id`、timestamp、workflow、mode、model、vae、prompts、input_images、output_images、generation_params、scores、notes。

## StorageRoot / ModelProfile Contract

`configs/models/storage_roots.yaml` 定义逻辑根：

```yaml
storage_roots:
  python_weights_root: F:/.../weights
  comfy_model_root: E:/Comfyui/models
  legacy_modelscope_root: E:/modelscope_tmp_clean
```

模型 profile 使用：

```yaml
profile_name:
  root_key: comfy_model_root
  relative_path: checkpoints/model.safetensors
```

运行时通过 `ModelProfileResolver` 解析真实路径。默认值来自 `configs/models/analysis_profiles.yaml` 和 generation YAML，允许被 manifest row、prompt row、CLI 覆盖。

LoRA contract：

```yaml
enable_lora: true
lora_profiles: [firefly_identity_reserved]
lora_weights:
  firefly_identity_reserved: 0.75
lora_trigger_words:
  firefly_identity_reserved: [firefly, liuying]
lora_apply_order: [firefly_identity_reserved]
```

当前可禁用 LoRA；workflow 如需启用，应在 ComfyUI 中先验证 LoRA 节点并导出模板。

## ReferencePack Contract

Reference pack 是一等输入对象，目录结构固定：

```text
data/reference_packs/<pack_id>/
  raw
  style
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
  processed/masks
  processed/crops
  processed/alpha
  processed/caption
  processed/tags
  processed/analysis
  processed/prompt_bundle
```

`raw/` 是角色主资产源，`style/` 是风格约束源；同时兼容更细的 `raw/official`、`selected/init`、`identity`、`composition`、`background` 等目录。扫描会为每个资产生成统一结构：`asset_id`、`pack_id`、`path`、`rel_path`、`role`、`source_type`、`priority`、`filename`、`notes`。`processed/*` 是自动分析后可人工修订的中间产物。

raw 角色图每张输出：

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

style 图每张输出：

```text
processed/style/<asset_id>/
  source.json
  caption.json
  tags.json
  analysis.json
  style_palette.json
  prompt_bundle.json
```

`scripts/analyze_references.py` 默认使用真实 provider：SAM3.1/SAM3、BiRefNet、WD14、Qwen2.5-VL/Florence。GroundingDINO 保留为可选扩展，但默认禁用；默认链路不要求 detector 成功，也不写假的 detection box。mock 只用于测试和调试，必须显式传 `--provider mock`，并在 JSON 里标记 `mock: true`。

真实分析命令：

```powershell
python scripts/analyze_references.py --pack data/reference_packs/firefly_v1 --provider real --device cuda --strict-real
```

mock 调试命令：

```powershell
python scripts/analyze_references.py --pack data/reference_packs/firefly_v1 --provider mock
```

真实模式要求本地权重存在：

```text
weights/segmentation/BiRefNet
weights/segmentation/sam3
weights/segmentation/sam3.1
weights/tagger/wd14_tagger_with_embeddings
weights/vlm/Florence-2-large
weights/vlm/Florence-2-large-PromptGen-v2.0
weights/vlm/Qwen2.5-VL-7B-Instruct
```

strict-real 下任何 provider 加载失败、依赖缺失或推理失败都会终止，不允许写假 caption、假 tags、空白 mask 或 `mock: true` 的分析文件。

`raw/screenshots/` 在 prompt bundle 中不是普通 raw 图，而是动作、镜头、构图、场景、背景、VFX 和氛围的重要来源。`prompt_bundle.json` 会显式记录 `screenshot_cues`、`composition_cues`、`background_cues`，并把 screenshot-specific negatives（game ui、hud、subtitle、watermark 等）合入最终 negative prompt。

SAM3 / SAM3.1 运行在独立 conda 环境 `sam3` 中；主仓库环境不直接 import SAM3 包。主仓库通过以下命令检查环境：

```powershell
python scripts/check_sam3_env.py `
  --python-exe "D:/Program Files/anaconda3/envs/sam3/python.exe" `
  --sam3-repo-dir "F:/python_project/game-aigc-asset-workflow/sam3" `
  --sam3-model-root "F:/python_project/game-aigc-asset-workflow/weights/segmentation/sam3.1" `
  --offline
```

手动测试 SAM3 CLI：

```powershell
conda run -n sam3 python scripts/sam3_segment_cli.py `
  --image data/reference_packs/firefly_v1/selected/init/firefly_poster_01.jpg `
  --out-dir outputs/debug_sam3/firefly_poster_01 `
  --sam3-repo-dir "F:/python_project/game-aigc-asset-workflow/sam3" `
  --sam3-model-root "F:/python_project/game-aigc-asset-workflow/weights/segmentation/sam3.1" `
  --offline `
  --prompts "person" "anime character" "main subject" `
  --device cuda
```

`segmentation.json` 的默认 provider 为 `SAM3.1-external-conda`，并包含 `source_mode: external_conda_sam3_text_prompt`。

`sam3_repo_dir` 是源码目录，`sam3_model_root` 是本地模型权重目录。离线模式禁止默认访问 `facebook/sam3`；如果出现 HuggingFace 401 / gated repo，说明本地模型路径没有正确传入或 SAM3 构建函数没有使用本地路径。

`manifest.csv` 自动生成但允许人工编辑，字段至少包含：

```text
task_id, character_id, task_type, reference_pack_id, init_image,
identity_refs, face_refs, mecha_refs, composition_refs, style_refs,
background_refs, generation_profile, notes
```

## PromptBundle Contract

`processed/prompt_bundle/*.json` 包含：

```json
{
  "positive_prompt": "...",
  "negative_prompt": "...",
  "prompt_sections": {
    "subject": "...",
    "identity": "...",
    "face": "...",
    "outfit": "...",
    "mecha": "...",
    "composition": "...",
    "background": "...",
    "style": "...",
    "quality": "...",
    "wallpaper": "..."
  },
  "source_refs_used": [],
  "source_analysis_used": [],
  "tags_used": [],
  "style_preset_used": "wallpaper_firefly",
  "notes": ""
}
```

PromptBundle 是评分、retrieval、agent retry 的引用对象，不只是最终字符串。

## Active Workflow / Registry Contract

导入 ComfyUI API JSON：

```powershell
python scripts/import_comfy_workflow.py --workflow-json <api.json> --workflow-id <id> --set-active
```

注册文件：

```text
configs/workflows/active_workflow.yaml
workflows/comfyui/_raw_exports/<raw_export>.json
workflows/comfyui/registered/<workflow_id>.json
workflows/comfyui/registry/<workflow_id>.yaml
```

metadata 至少包含：

```yaml
workflow_id: firefly_img2img_v1
workflow_json_path: workflows/comfyui/registered/firefly_img2img_v1.json
source_raw_json_path: workflows/comfyui/_raw_exports/firefly_img2img_v1.json
workflow_type: img2img
auto_analyzed: true
detected_modules:
  lora: true
  ipadapter: true
  controlnet: true
  upscale: true
node_inventory:
  "1":
    class_type: CheckpointLoaderSimple
    title: ""
    input_keys: [ckpt_name]
patch_contract:
  node_inputs:
    ckpt_name:
      node_id: "1"
      input: ckpt_name
      optional: true
      source: auto
    positive_prompt:
      node_id: "12"
      input: text
      optional: false
      source: auto
candidates:
  prompt_nodes: []
  image_nodes: []
  sampler_nodes: []
  save_nodes: []
  model_nodes: []
ambiguous_candidates:
  image_roles: []
  prompt_roles: []
  sampler_roles: []
warnings: []
manual_overrides:
  enabled: true
  notes: ""
```

导入命令推荐：

```powershell
python scripts/import_comfy_workflow.py `
  --workflow-json workflows/comfyui/_raw_exports/<your_workflow>.json `
  --workflow-id <workflow_id> `
  --set-active `
  --auto-map
```

检查命令推荐：

```powershell
python scripts/inspect_workflow.py --active --show-candidates
```

不同 ComfyUI API JSON 的节点 ID、节点数量、class_type 和连接关系都可能不同，所以不能写死 `node 8 = positive prompt` 之类映射。自动 analyzer 会根据图连接推断 prompt、LoadImage、sampler、SaveImage、模型 loader、尺寸字段等 patch candidates；无法确定时写入 `ambiguous_candidates` 和 `warnings`，由用户人工确认 registry。

```text
{{model_name}}
{{vae_name}}
{{positive_prompt}}
{{negative_prompt}}
{{width}}
{{height}}
{{seed}}
{{steps}}
{{cfg}}
{{sampler}}
{{scheduler}}
{{denoise}}
{{input_image_path}}
{{controlnet_name}}
{{controlnet_weight}}
{{ipadapter_name}}
{{ipadapter_weight}}
```

`WorkflowRuntime` 支持多输入逻辑字段：

```text
init_image
identity_ref_images[]
face_ref_images[]
mecha_ref_images[]
composition_ref_images[]
style_ref_images[]
background_ref_images[]
character_mask
mecha_mask
ui_mask
prompt_bundle
lora_settings
controlnet settings
ipadapter settings
```

模板可以使用 `{{identity_ref_images_first}}`、`{{identity_ref_images_json}}` 等占位符。不需要的输入会被优雅忽略。

`WorkflowRuntime` 只做模板加载、占位替换、registry patch、ComfyUI input image 复制/上传，不负责真实模型存在性校验，不负责发明 workflow 连接。

## GenerationTasks Contract

`scripts/build_tasks.py` 从 `manifest.csv`、`prompt_sheet.csv`、raw/style assets 和 prompt bundle 生成：

```text
data/reference_packs/<pack_id>/generation_tasks.csv
```

字段包括：

```text
task_id, character_id, task_type, reference_pack_id,
workflow_id, init_image, identity_ref_image, face_ref_image,
mecha_ref_image, composition_ref_image, background_ref_image, style_ref_image,
prompt_bundle, positive_prompt, negative_prompt,
user_positive_append, user_negative_append, generation_profile,
model/profile fields, sampler fields, output fields, notes
```

只有一张主图 + 多张风格图时推荐：

```powershell
python scripts/analyze_references.py --pack data/reference_packs/firefly_v1
python scripts/build_tasks.py --pack data/reference_packs/firefly_v1 --mode single_init_all_styles
python scripts/batch_generate_stub.py --tasks data/reference_packs/firefly_v1/generation_tasks.csv --dry-run
```

`build_tasks.py` 支持 `single_init_all_styles`、`topk_style_per_init --topk N`、`cartesian`、`manual`。缺少 face / mecha / composition 时会 fallback 到 init 或更合适的截图/角色图；缺少 style 时保留空字段并由 runtime 按 registry optional 规则处理。

## Manifest 结构

每次实验写入：

```text
results/runs/<run_id>/run_manifest.json
results/runs/<run_id>/batch_summary.json
results/runs/<run_id>/task_000.workflow.json
```

`run_manifest.json` 是后续检索、评分、badcase 分析和复现实验的主入口。至少记录 workflow_id、workflow_type、registry path、registered workflow path、原始 task row、final positive/negative prompt、patched fields、skipped fields、warnings、复制/上传后的 ComfyUI input image name、generation config、resolved models、resolved params、ComfyUI URL、prompt id、输出图、评分摘要、git commit、Python 版本。

## Scoring Contract

评分记录必须包含分数、解释和 warnings：

```text
prompt_alignment_score
reference_fidelity_score
aesthetic_score
technical_score
wallpaper_score
vlm_critique_score
final_score
score_explanations
warnings
```

Reference analysis 已默认真实模型链路；scorer 仍是 mock/provider interface，但 JSON 结构稳定，后续可以替换 CLIP、DINO、aesthetic predictor、technical checker、VLM judge。

## Provider 接口

`VLMProvider`：

```python
def describe(image_path: str) -> dict: ...
```

返回结构化描述，建议字段：`summary`、`appearance`、`outfit`、`pose`、`composition`、`background`、`style`、`keywords`。

`TaggerProvider`：

```python
def tag(image_path: str) -> list[str]: ...
```

`ScoringProvider`：

```python
def score(task, output_image_path, run_id, reference_image_path=None) -> ScoreRecord: ...
```

评分第一阶段默认使用 mock provider。真实 CLIP、SigLIP、LPIPS、DINO、VLM Judge 应通过同一接口接入。Reference analysis 不再默认 mock。

`RetrievalStore`：

```python
def add(record: dict) -> None: ...
def search(query: str, limit: int = 5) -> list[dict]: ...
```

默认实现是本地 JSONL，可保存高分 prompt、最佳参数、失败案例和 benchmark 历史结果。后续可替换为 embedding/向量检索。

`ExperimentAgent`：

- 根据 mode 选择 workflow。
- 根据 `ExperimentConfig.sweep` 生成 sweep 计划。
- 根据 `ScoreRecord` 输出下一轮建议。

第一阶段保持 rule-based，不强依赖 LangChain/LangGraph。
