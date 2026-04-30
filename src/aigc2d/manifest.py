from __future__ import annotations

import uuid
from pathlib import Path

from .config import PROJECT_ROOT, load_json, model_to_dict, write_json
from .schemas import GenerationTask, PromptSpec, RunManifest, ScoreRecord


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def run_dir(run_id: str, root: str | Path = PROJECT_ROOT / "results" / "runs") -> Path:
    return Path(root) / run_id


def create_run_manifest(
    run_id: str,
    task: GenerationTask,
    output_images: list[str] | None = None,
    scores: list[ScoreRecord] | None = None,
    notes: str = "",
) -> RunManifest:
    generation_params = {
        "width": task.width,
        "height": task.height,
        "seed": task.seed,
        "steps": task.steps,
        "cfg": task.cfg,
        "sampler": task.sampler,
        "scheduler": task.scheduler,
        "denoise": task.denoise,
        "controlnet_name": task.controlnet_name,
        "controlnet_weight": task.controlnet_weight,
        "ipadapter_name": task.ipadapter_name,
        "ipadapter_weight": task.ipadapter_weight,
        **task.extra_params,
    }
    return RunManifest(
        run_id=run_id,
        workflow_name=task.workflow_name,
        task_type=task.task_type,
        mode=task.mode,
        model=task.model_name,
        vae=task.vae_name,
        prompts=[task.prompt],
        input_images=[task.input_image_path] if task.input_image_path else [],
        output_images=output_images or [],
        generation_params=generation_params,
        scores=scores or [],
        notes=notes or task.notes,
    )


def save_run_manifest(
    manifest: RunManifest,
    root: str | Path = PROJECT_ROOT / "results" / "runs",
) -> Path:
    target = run_dir(manifest.run_id, root) / "manifest.json"
    return write_json(target, model_to_dict(manifest))


def load_run_manifest(path: str | Path) -> RunManifest:
    return RunManifest(**load_json(path))


def sample_task() -> GenerationTask:
    return GenerationTask(
        task_id="sample_t2i",
        mode="t2i",
        task_type="text2img",
        workflow_name="text2img_animagine",
        model_name="animagine-xl.safetensors",
        vae_name="sdxl_vae.safetensors",
        prompt=PromptSpec(
            positive_prompt="anime game character, clean lineart",
            negative_prompt="low quality, bad anatomy",
        ),
    )
