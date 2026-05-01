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
- real reference analysis providers for SAM3.1/SAM3, BiRefNet, WD14, and Qwen2.5-VL/Florence; GroundingDINO is optional and disabled by default

## Responsibility Boundary

Python manages reference assets, analysis contracts, prompt bundles, workflow input patching, scheduling, output download, scoring, reproducibility, retrieval, and agent suggestions.

ComfyUI manages actual model loading and generation: text2img, img2img, IP-Adapter, ControlNet, LoRA, upscale, and future video. Multi-node workflows must be built and validated manually in ComfyUI first, then exported as API JSON. Python reads the API JSON, analyzes graph structure, writes a registry patch contract, and patches only fields described by that registry. Node IDs are never hard-coded in runtime code because every ComfyUI export can have different IDs.

## Run

```powershell
pip install -r requirements.txt
python scripts/check_env.py
```

Import a real ComfyUI API JSON exported from a workflow that was already validated in the ComfyUI UI:

```powershell
python scripts/import_comfy_workflow.py `
  --workflow-json workflows/comfyui/_raw_exports/<your_workflow>.json `
  --workflow-id <workflow_id> `
  --set-active `
  --auto-map
```

Inspect the active workflow:

```powershell
python scripts/inspect_workflow.py --active --show-candidates
```

Analyze references and build tasks:

```powershell
python scripts/analyze_references.py --pack data/reference_packs/firefly_v1
python scripts/build_tasks.py --pack data/reference_packs/firefly_v1 --mode single_init_all_styles
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

Put original ComfyUI exports in `workflows/comfyui/_raw_exports/`. Import copies the active JSON to `workflows/comfyui/registered/` and writes analyzer output to `workflows/comfyui/registry/<workflow_id>.yaml`; `configs/workflows/active_workflow.yaml` only records the active workflow id.

Put reference images in role directories such as `data/reference_packs/firefly_v1/selected/init/`, `selected/identity/`, `selected/style/`, `raw/`, and `style/`. The analysis script writes editable artifacts under `processed/` and generates `manifest.csv` plus `prompt_sheet.csv`; generated artifacts and runtime outputs are ignored by git by default.

`scripts/analyze_references.py` defaults to real local inference:

```powershell
python scripts/analyze_references.py --pack data/reference_packs/firefly_v1 --provider real --device cuda --strict-real
```

Real mode loads local weights from `weights/segmentation/sam3.1`, `weights/segmentation/BiRefNet`, `weights/tagger/wd14_tagger_with_embeddings`, and `weights/vlm/Qwen2.5-VL-7B-Instruct` or Florence. GroundingDINO can be re-enabled later as an optional detector, but it is not part of the default reference analysis path. Screenshots under `raw/screenshots/` are emphasized for pose/action, camera composition, scene/background, VFX, and mood cues. Real mode fails immediately if a required provider, dependency, model file, or inference call fails; it does not write mock analysis files. Mock is only for tests/debug and must be explicit:

```powershell
python scripts/analyze_references.py --pack data/reference_packs/firefly_v1 --provider mock
```

SAM3/SAM3.1 runs in a separate conda env named `sam3`; the main repo environment calls it through `conda run` and does not import the SAM3 package directly:

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

`sam3_repo_dir` points to local SAM3 source code, while `sam3_model_root` points to local SAM3/SAM3.1 weights. The CLI refuses to call `build_sam3_image_model()` without local model paths because that can try to access `facebook/sam3` on HuggingFace. If you see a HuggingFace 401/gated repo error, check `sam3_model_root`, `sam3_config_path`, and `sam3_checkpoint_path`.

Automatic analysis is not magic: deterministic mappings are filled into the registry, ambiguous prompt/image/sampler roles are preserved as candidates with warnings, and the user should inspect the registry before execution.

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
