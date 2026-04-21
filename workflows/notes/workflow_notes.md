# Workflow Notes

## 1. Current Status

`workflows/comfyui/*.json` files in repo are still placeholder artifacts.

They are planning anchors and filename contracts, not runnable API prompts yet.

## 2. Format Boundary

Two workflow formats must not be mixed:

- UI workflow JSON (editor graph format)
- API workflow JSON (execution prompt format)

`patch_workflow` mode only supports API workflow JSON.

## 3. Replacement Steps

When real graph is ready:

1. Build and verify in ComfyUI UI.
2. Export via **File -> Export (API)**.
3. Replace the placeholder file.
4. Update mapping YAML node ids.

## 4. Baseline Priority

Current first-stage priority:

1. `sdxl_ui_icon_base.json`
2. `sdxl_concept_base.json`

These are checkpoint-family image baselines.

## 5. Compatibility Direction (Beyond SDXL Baseline)

Future workflow support direction includes split-model families:

- Qwen-family image/video style workflows
- FLUX-family workflows
- Hunyuan Video-like workflows

Those families often require:

- `diffusion_models`
- `text_encoders`
- `vae`

instead of checkpoint-only loading.

`classic_checkpoint / split_model / conditioning / postprocess / media_extension`
are project-level compatibility abstractions, not official ComfyUI terminology.

## 6. Adapter / Node Map Principle

Node mapping and adapter logic must stay workflow-agnostic:

- do not hardcode checkpoint-only assumptions
- keep requirements declared by config
- keep patch layer focused on explicit node/input mapping

## 7. Baseline Patch Scope (Current)

Current patch scope remains:

- positive / negative prompt
- seed / width / height / steps / cfg / sampler / scheduler
- `SaveImage.filename_prefix`

LoRA and ControlNet remain interface hooks, not full end-to-end runtime platform in this stage.
