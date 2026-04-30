# Pipeline Contract

本文档定义 AIGC 2D 生成工作台的稳定契约。实现以 `src/aigc2d/*` 为准。

## 工程边界

Python 仓库负责参考图资产管理、分析、prompt bundle、workflow 参数 patch、调度、下载、评分、复现、检索和 agent 建议。ComfyUI 负责模型加载与真正生成。

多节点 ComfyUI workflow 必须先在 ComfyUI UI 手工搭建并验证，再导出 API JSON 模板。Python 只替换占位符，不猜测节点连线。

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
  processed/masks
  processed/crops
  processed/alpha
  processed/caption
  processed/tags
  processed/analysis
  processed/prompt_bundle
```

`raw/` 是角色主资产源，`style/` 是风格约束源；同时兼容更细的 `raw/official`、`selected/style` 等目录。`processed/*` 是自动分析后可人工修订的中间产物。

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

当前 segmentation/detection/VLM/Tagger 可以是 mock provider，但必须写同样的文件 contract，并在 JSON 里标记 `mock: true`。

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
workflows/comfyui/<workflow_id>.json
workflows/comfyui/registry/<workflow_id>.yaml
```

metadata 至少包含：

```yaml
workflow_id: firefly_img2img_v1
workflow_json_path: workflows/comfyui/firefly_img2img_v1.json
workflow_type: img2img
supported_inputs: []
optional_modules:
  lora: true
  ipadapter: true
  controlnet: true
  upscale: true
patch_contract:
  placeholder_fields: {}
  node_inputs:
    positive_prompt:
      node_id: "12"
      input: text
      optional: false
warnings: []
```

如果导入的真实 API JSON 没有 `{{placeholder}}`，系统不会猜节点连接，会给 warning。用户可以在 registry metadata 里手工补 `patch_contract.node_inputs`。

真实 ComfyUI API JSON 由 `scripts/import_comfy_workflow.py` 导入到 `workflows/comfyui/<workflow_id>.json`。如果你希望自动 placeholder patch，可以在 workflow JSON 中保留这些占位符；如果真实导出没有占位符，就在 registry metadata 的 `patch_contract.node_inputs` 里手工补节点映射。

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

`WorkflowRuntime` 只做模板加载与占位替换，不负责真实模型存在性校验，不负责发明 workflow 连接。

## GenerationTasks Contract

`scripts/build_tasks.py` 从 `manifest.csv`、`prompt_sheet.csv`、raw/style assets 和 prompt bundle 生成：

```text
data/reference_packs/<pack_id>/generation_tasks.csv
```

字段包括：

```text
task_id, character_id, task_type, reference_pack_id,
init_image, raw_asset, style_asset, style_refs,
identity_refs, face_refs, mecha_refs, composition_refs, background_refs,
prompt_bundle, positive_prompt, negative_prompt,
workflow_id, generation_profile, notes
```

默认模式是 `topk_style_per_raw`，防止 raw/style 组合数量爆炸。也支持 `cartesian` 和 `manual`。

## Manifest 结构

每次实验写入：

```text
results/runs/<run_id>/run_manifest.json
results/runs/<run_id>/batch_summary.json
results/runs/<run_id>/task_000.workflow.json
```

`run_manifest.json` 是后续检索、评分、badcase 分析和复现实验的主入口。至少记录 generation config、workflow template、prompt row、resolved prompt、resolved models、resolved params、ComfyUI URL、prompt id、输入参考图、输出图、评分摘要、git commit、Python 版本。

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

第一版 scorer 是 mock/provider interface，但 JSON 结构稳定，后续可以替换 CLIP、DINO、aesthetic predictor、technical checker、VLM judge。

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

第一阶段默认使用 mock provider。真实 CLIP、SigLIP、LPIPS、DINO、VLM Judge 应通过同一接口接入。

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
