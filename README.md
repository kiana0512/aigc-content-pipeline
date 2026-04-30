# GAME-AIGC-ASSET-WORKFLOW

Local multimodal AIGC experiment workbench for reproducible 2D generation. Phase 1 focuses on: Firefly character standee -> high-aesthetic 4K wallpaper.

The Python repo owns benchmark data, prompt assembly, model profile resolution, ComfyUI workflow templating, real ComfyUI API calls, batch runs, run manifests, scoring summaries, lightweight retrieval, and rule-based agent hooks. ComfyUI only runs generation.

## What Works Now

- `text2img`, `img2img`, `img2img_ipadapter_controlnet`, `upscale_4k`
- reserved template/interface for `image2video` and `text2video`
- config-driven execution from `configs/generation/*.yaml`
- model profile resolution from `configs/models/*.yaml`, with `root_key + relative_path` storage roots
- reference pack scan, segmentation/crop/caption/tags/analysis artifacts, prompt bundle generation
- real HTTP ComfyUI API submit/poll/download
- reproducible `results/runs/<run_id>/run_manifest.json`
- mock VLM, Tagger, segmentation, CLIP/aesthetic/technical/VLM/wallpaper scoring providers

## Responsibility Boundary

Python manages reference assets, analysis contracts, prompt bundles, workflow input patching, scheduling, output download, scoring, reproducibility, retrieval, and agent suggestions.

ComfyUI manages actual model loading and generation: text2img, img2img, IP-Adapter, ControlNet, LoRA, upscale, and future video. Multi-node workflows must be built and validated manually in ComfyUI first, then exported as API JSON templates. Python does not guess node wiring; it only patches known placeholders and runs batches.

## Run

```powershell
pip install -r requirements.txt
python scripts/check_env.py
```

Import a real ComfyUI API JSON exported from a workflow that was already validated in the ComfyUI UI:

```powershell
python scripts/import_comfy_workflow.py `
  --workflow-json workflows/comfyui/incoming/firefly_img2img_28node_api.json `
  --workflow-id firefly_img2img_v1 `
  --set-active
```

Inspect the active workflow:

```powershell
python scripts/inspect_workflow.py --active
```

Analyze references and build tasks:

python scripts/analyze_references.py --pack data/reference_packs/firefly_v1
python scripts/build_tasks.py --pack data/reference_packs/firefly_v1 --mode topk_style_per_raw --topk 3
```

Dry-run, then execute:

```powershell
python scripts/batch_generate_stub.py --tasks data/reference_packs/firefly_v1/generation_tasks.csv --dry-run
python scripts/batch_generate_stub.py --tasks data/reference_packs/firefly_v1/generation_tasks.csv --execute --download-outputs --comfy-url http://127.0.0.1:8188
```

Use `http://127.0.0.1:8000` instead if your ComfyUI server runs there.

## Models

Edit `configs/models/storage_roots.yaml` and the profile YAML files in `configs/models/`. Model paths are not hard-coded; profiles use `root_key + relative_path`.

## Reference Pack

Put character images in `data/reference_packs/firefly_v1/raw/` and style images in `data/reference_packs/firefly_v1/style/`. The analysis script writes editable artifacts under `processed/` and generates `manifest.csv` plus `prompt_sheet.csv`.

## Results

Every run writes:

```text
results/runs/<run_id>/
  run_manifest.json
  batch_summary.json
  task_000.workflow.json
  tasks.json
  outputs/            # when --download-outputs is enabled
```

Generate a simple report:

```powershell
python scripts/generate_report.py --run-manifest results/runs/<run_id>/run_manifest.json
```

## Mock vs Real

Real: ComfyUI API client, workflow placeholder patching, config/profile merge, batch dry-run/execute path, run manifest writing, output downloading.

Mock/provider interface: VLM caption/critique, Tagger, CLIP/aesthetic/technical/VLM/wallpaper scorers, retrieval-assisted agent recommendations. Replace providers without changing the batch/runtime contracts.

## File Roles

- `src/aigc2d/reference_pack.py`: reference pack scan and auto manifest rows.
- `src/aigc2d/reference_analysis.py`: VLM/Tagger/segmentation orchestration.
- `src/aigc2d/prompt_bundle.py`: structured prompt bundle JSON.
- `src/aigc2d/workflow_runtime.py`: config/profile/manifest/prompt merge and workflow patching.
- `src/aigc2d/model_profiles.py`: storage roots, defaults, profile resolution, LoRA contract.
- `src/aigc2d/comfy_client.py`: real ComfyUI HTTP API client.
- `src/aigc2d/scoring.py` and `src/aigc2d/scorers/`: score breakdown and explanations.
- `src/aigc2d/retrieval.py`, `src/aigc2d/agent.py`: historical lookup and rule-based suggestions.
- `scripts/analyze_references.py`: build processed reference artifacts and prompt sheet.
- `scripts/build_manifest.py`: generate editable manifest from a reference pack.
- `scripts/batch_generate_stub.py`: dry-run or execute ComfyUI batch generation.
