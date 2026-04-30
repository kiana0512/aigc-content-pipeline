from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


TaskType = Literal[
    "text2img",
    "img2img",
    "img2img_ipadapter_controlnet",
    "upscale_4k",
    "image_analysis",
    "image_scoring",
    "image2video",
    "text2video",
]
Mode = Literal["t2i", "i2i", "i2v", "t2v", "2d3d"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PromptSpec(BaseModel):
    positive_prompt: str
    negative_prompt: str = ""
    layers: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerationTask(BaseModel):
    task_id: str
    mode: Mode = "t2i"
    task_type: TaskType = "text2img"
    workflow_name: str
    prompt: PromptSpec
    model_name: str
    vae_name: str | None = None
    width: int = 1024
    height: int = 1024
    seed: int = -1
    steps: int = 28
    cfg: float = 5.0
    sampler: str = "euler"
    scheduler: str = "normal"
    denoise: float = 1.0
    input_image_path: str | None = None
    controlnet_name: str | None = None
    controlnet_weight: float | None = None
    ipadapter_name: str | None = None
    ipadapter_weight: float | None = None
    extra_params: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class BenchmarkItem(BaseModel):
    id: str
    character_name: str
    image_path: str
    source: str
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class ScoreRecord(BaseModel):
    item_id: str
    run_id: str
    output_image_path: str
    text_image_alignment_score: float | None = None
    prompt_alignment_score: float | None = None
    image_image_similarity_score: float | None = None
    reference_fidelity_score: float | None = None
    structural_similarity_score: float | None = None
    aesthetic_quality_score: float | None = None
    aesthetic_score: float | None = None
    technical_quality_score: float | None = None
    technical_score: float | None = None
    wallpaper_suitability_score: float | None = None
    wallpaper_score: float | None = None
    vlm_judge_score: float | None = None
    vlm_critique_score: float | None = None
    manual_score: float | None = None
    final_score: float | None = None
    weighted_score: float | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    score_explanations: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: str = ""


class RunManifest(BaseModel):
    run_id: str
    timestamp: str = Field(default_factory=utc_now_iso)
    workflow_name: str
    task_type: TaskType = "text2img"
    mode: Mode
    model: str
    vae: str | None = None
    prompts: list[PromptSpec] = Field(default_factory=list)
    input_images: list[str] = Field(default_factory=list)
    output_images: list[str] = Field(default_factory=list)
    generation_params: dict[str, Any] = Field(default_factory=dict)
    scores: list[ScoreRecord] = Field(default_factory=list)
    notes: str = ""


class ExperimentConfig(BaseModel):
    name: str
    mode: Mode = "t2i"
    task_type: TaskType = "text2img"
    workflow_name: str
    model_name: str
    vae_name: str | None = None
    width: int = 1024
    height: int = 1024
    seed: int = -1
    steps: int = 28
    cfg: float = 5.0
    sampler: str = "euler"
    scheduler: str = "normal"
    denoise: float = 1.0
    batch_size: int = 1
    sweep: dict[str, list[Any]] = Field(default_factory=dict)
    style_preset: str = "anime_game_asset"
    quality_tokens: list[str] = Field(default_factory=list)
    negative_prompt: str = ""
    scoring_weights: dict[str, float] = Field(default_factory=dict)
    comfyui_base_url: str = "http://127.0.0.1:8188"
    notes: str = ""
