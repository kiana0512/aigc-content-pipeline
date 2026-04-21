# ComfyUI Model Folders

This file summarizes ComfyUI model folder roles for this project.

`classic_checkpoint / split_model / conditioning / postprocess / media_extension`
are project compatibility abstractions in this repository, not official ComfyUI terminology.

## Classification

- current mainline: directly relevant to current baseline delivery
- common extension: often needed in next-stage workflows
- advanced optional: specialized/internal/infra-oriented folders

## 1) Current Mainline

### `checkpoints`
- class: current mainline
- typical use: classic SD/SDXL workflows (single checkpoint loader)
- game AIGC relevance: baseline icon/concept generation

### `diffusion_models`
- class: current mainline compatibility target
- typical use: split-model families (with separate text encoder and vae)
- game AIGC relevance: future Qwen / FLUX / Hunyuan-like split workflows

### `text_encoders`
- class: current mainline compatibility target
- typical use: prompt encoding for split-model workflows
- game AIGC relevance: future multi-family expansion beyond checkpoint-only design

### `vae`
- class: current mainline
- typical use: latent <-> pixel decode/encode components
- game AIGC relevance: baseline and split-model workflows

## 2) Common Extension

### `loras`
- class: common extension
- use: style/identity lightweight adaptation
- repo status: interface-ready, not full pipeline

### `controlnet`
- class: common extension
- use: structure/control conditioning
- repo status: interface-ready, baseline disabled

### `embeddings`
- class: common extension
- use: textual inversion / embedding tokens

### `clip_vision`
- class: common extension
- use: image/reference-side conditioning

### `style_models`
- class: common extension
- use: style transfer / style-conditioned generation chains

### `upscale_models`
- class: common extension
- use: pixel-space upscale/postprocess

### `latent_upscale_models`
- class: common extension
- use: latent-space upscale chains

### `photomaker`
- class: common extension
- use: identity/reference-driven generation workflows

### `gligen`
- class: common extension
- use: grounding/layout/region-aware conditioning families

### `hypernetworks`
- class: common extension
- use: additional style/adaptation model components

### `audio_encoders`
- class: common extension
- use: audio-conditioned workflows
- game AIGC relevance: potential voice/audio-driven media asset pipeline

## 3) Advanced Optional

### `diffusers`
- class: advanced optional
- note: often environment/toolchain specific layout

### `vae_approx`
- class: advanced optional
- note: optimization/specialized approximate vae components

### `classifiers`
- class: advanced optional
- note: workflow-specific or legacy guidance components

### `model_patches`
- class: advanced optional
- note: patch overlays / internal model customization

### `download_model_base`
- class: advanced optional
- note: infrastructure/download-base oriented directory

## Layered Adoption Recommendation

1. first stage (now):
   - `checkpoints`, `vae`, baseline image workflows
2. second stage:
   - `loras`, `controlnet`, `embeddings`, `upscale_models`
3. third stage:
   - split-model adoption: `diffusion_models` + `text_encoders` + `vae`
4. fourth stage:
   - specialized extensions: `clip_vision`, `style_models`, `photomaker`, `audio_encoders`, etc.
5. advanced optional:
   - only when workflow/tooling explicitly requires them

This staged approach keeps baseline stable while preserving forward compatibility.

## Task-Folder Matrix

| Workflow Task | Typical Family (Project Abstraction) | Core Folders | Extended Folders |
| --- | --- | --- | --- |
| SDXL baseline image generation | `classic_checkpoint` | `checkpoints`, `vae` | `loras`, `controlnet`, `embeddings` |
| Split-model baseline (Qwen/FLUX-style) | `split_model` | `diffusion_models`, `text_encoders`, `vae` | `clip_vision`, `loras`, `controlnet` |
| Style/reference conditioning | `conditioning` | (depends on base family) | `clip_vision`, `style_models`, `photomaker`, `gligen`, `hypernetworks` |
| Upscale/postprocess | `postprocess` | (depends on base family) | `upscale_models`, `latent_upscale_models` |
| Audio/video extension preparation | `media_extension` | (depends on base family) | `audio_encoders` (+ workflow-specific video stacks) |
