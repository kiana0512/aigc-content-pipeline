# ComfyUI Baseline Setup

## 1) Scope

Current repo stage:

- mainline: image baseline workflows (UI icon / character concept)
- baseline model strategy: SDXL base first
- LoRA / ControlNet: interface-ready, default disabled
- UE5 automation: out of scope for current stage
- this repo acts as baseline integration preparation + compatibility layer, not a full ComfyUI all-in-one platform

ComfyUI in this project is treated as a **node-based generation platform**, not only a text-to-image tool.  
It can host image, video, reference-conditioning, audio-condition, and API/3D-related node workflows.

## 1.1) About model family terms

`classic_checkpoint / split_model / conditioning / postprocess / media_extension` are
**project-internal compatibility abstractions**, not official ComfyUI terminology.

## 2) JSON Format Boundary (Critical)

There are two different JSON concepts:

- UI workflow JSON: editor graph format (usually contains `nodes` list)
- API workflow JSON: execution prompt format (node-id keyed object)

`patch_workflow` only accepts **API workflow JSON**.

If you pass UI workflow JSON, adapter rejects it.
If you pass repo placeholder workflow JSON, adapter rejects it with:

`Current workflow JSON is still a placeholder and cannot be patched. Please replace it with an actual ComfyUI-exported workflow first.`

## 3) Export Workflow for Patching

Use ComfyUI menu:

1. Build and test graph in ComfyUI UI.
2. Export with **File -> Export (API)**.
3. Replace one repo workflow file:
   - `workflows/comfyui/sdxl_ui_icon_base.json`
   - `workflows/comfyui/sdxl_concept_base.json`
   - `workflows/comfyui/controlnet_edge_icon.json`
4. Update node ids in mapping YAML under `configs/`.

## 4) Minimal Baseline Graph (Image Mainline)

Recommended minimum nodes:

1. `CheckpointLoaderSimple`
2. `CLIPTextEncode` (positive)
3. `CLIPTextEncode` (negative)
4. `EmptyLatentImage`
5. `KSampler`
6. `VAEDecode`
7. `SaveImage`

## 5) Baseline Workflow Recommendations

### UI icon baseline

1. Start with SDXL base checkpoint.
2. Use `prompts/ui_icons/*`.
3. Keep square resolution first (`1024x1024`).
4. Keep LoRA / ControlNet disabled initially.
5. Export API JSON and patch by script.

### Character concept baseline

1. Use SDXL base checkpoint.
2. Use `prompts/character_concepts/*`.
3. Iterate sampler/scheduler after first stable baseline pass.
4. Keep LoRA / ControlNet disabled initially.
5. Export API JSON and patch by script.

## 6) SaveImage Patch Policy

Baseline policy:

- patch `SaveImage.filename_prefix` by default
- do not rely on output directory patching as baseline dependency

`output_dir` patch is optional advanced behavior:

- `comfyui.patch_save_image_output_dir: false` (default)

## 7) Model Folder Compatibility (ComfyUI)

ComfyUI models are folder-organized. Different workflows depend on different folders.

In this repo, folder compatibility is expressed through `comfyui_models` config section and workflow requirements under `comfyui`.
Runner only resolves declared requirements and prints a compatibility report; it does not auto-infer every node dependency.

### Mainline required-by-architecture folders

- `checkpoints`
- `diffusion_models`
- `vae`
- `text_encoders`

### Common extension folders

- `clip_vision`
- `loras`
- `controlnet`
- `embeddings`
- `style_models`
- `upscale_models`
- `latent_upscale_models`
- `photomaker`
- `gligen`
- `hypernetworks`
- `audio_encoders`

### Advanced optional folders (not current mainline)

- `diffusers`
- `vae_approx`
- `classifiers`
- `model_patches`
- `download_model_base`

## 8) checkpoints vs diffusion_models

- `checkpoints`: monolithic model files (classic SD/SDXL style workflows)
- `diffusion_models` + `text_encoders` + `vae`: split-model style workflows (common in newer families)

This repo now supports both requirement expressions:

- `classic_checkpoint` family
- `split_model` family
- plus conditioning/postprocess/media extension families as compatibility declarations

## 9) Key Components Role

- `text_encoders`: text side model components for prompt understanding in split workflows
- `clip_vision`: image/reference-side encoder for image-conditioned workflows
- `style_models` / `photomaker` / `gligen` / `hypernetworks`: conditioning or style-control extensions
- `upscale_models` / `latent_upscale_models`: postprocess/upscale chains
- `audio_encoders`: media-extension workflows with audio conditions

Current repo does **not** claim full runtime support for all above families; it provides compatibility declaration + runner hints + adapter extension points.

## 10) Config Mapping to Node Inputs

For baseline image workflow:

- `runtime.seed` -> `KSampler.seed`
- `generation.width` / `generation.height` -> `EmptyLatentImage.width/height`
- `generation.num_inference_steps` -> `KSampler.steps`
- `generation.guidance_scale` -> `KSampler.cfg`
- `generation.sampler` -> `KSampler.sampler_name`
- `generation.scheduler` -> `KSampler.scheduler`
- prompt pack positive / negative -> `CLIPTextEncode.text`
- per-item file prefix -> `SaveImage.filename_prefix`

`model.base_model_name` and `model.variant` are experiment metadata fields; they should match the actual ComfyUI node selection.

## 11) Baseline-first Strategy

Why not enable every model folder/workflow family immediately:

1. baseline image quality and stability must be verified first
2. each new family adds model management and validation complexity
3. game asset production flow benefits from staged rollout (baseline -> conditioning -> advanced families)

## 12) Commands

Manifest mode:

```bash
python scripts/run_batch_generation.py \
  --config configs/sdxl_icon.yaml \
  --prompt-pack outputs/prompt_pack/ui_icons/prompt_pack.csv \
  --mode manifest
```

Patch workflow mode:

```bash
python scripts/run_batch_generation.py \
  --config configs/sdxl_icon.yaml \
  --prompt-pack outputs/prompt_pack/ui_icons/prompt_pack.csv \
  --mode patch_workflow
```

Optional submit mode:

```bash
python scripts/run_batch_generation.py \
  --config configs/sdxl_icon.yaml \
  --prompt-pack outputs/prompt_pack/ui_icons/prompt_pack.csv \
  --mode submit \
  --comfyui-url http://127.0.0.1:8188
```

`submit` is experimental (smoke-test level), not a production-grade orchestration subsystem.

## 13) strict_model_dir_check

- `strict_model_dir_check: false` (default):
  - missing required directories are reported as warnings in compatibility report
  - useful during setup and migration period
- `strict_model_dir_check: true`:
  - missing required directory declarations fail fast
  - useful for CI and stable team environments
