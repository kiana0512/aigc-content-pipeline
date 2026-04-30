from __future__ import annotations

import csv
from pathlib import Path
from statistics import mean
from typing import Protocol

from .schemas import GenerationTask, ScoreRecord
from .scorers.aesthetic_scorer import MockAestheticScorer
from .scorers.clip_scorer import MockClipScorer
from .scorers.technical_scorer import MockTechnicalScorer
from .scorers.vlm_critic import MockVLMCritic
from .scorers.wallpaper_scorer import WallpaperScorer


SCORE_FIELDS = [
    "text_image_alignment_score",
    "prompt_alignment_score",
    "image_image_similarity_score",
    "reference_fidelity_score",
    "structural_similarity_score",
    "aesthetic_quality_score",
    "technical_quality_score",
    "wallpaper_suitability_score",
    "vlm_judge_score",
    "vlm_critique_score",
    "manual_score",
]
MANUAL_SCORE_FIELDS = ["aesthetic", "prompt_alignment", "style_consistency", "anatomy", "production_usability"]


class ScoringProvider(Protocol):
    def score(
        self,
        task: GenerationTask,
        output_image_path: str,
        run_id: str,
        reference_image_path: str | None = None,
    ) -> ScoreRecord:
        ...


class MockScoringProvider:
    def __init__(self, default_score: float = 0.5) -> None:
        self.default_score = default_score
        self.clip = MockClipScorer()
        self.aesthetic = MockAestheticScorer()
        self.technical = MockTechnicalScorer()
        self.vlm = MockVLMCritic()
        self.wallpaper = WallpaperScorer()

    def score(
        self,
        task: GenerationTask,
        output_image_path: str,
        run_id: str,
        reference_image_path: str | None = None,
    ) -> ScoreRecord:
        text_alignment = self.clip.score_text_image(task.prompt.positive_prompt, output_image_path)
        image_similarity = (
            self.clip.score_reference_similarity(reference_image_path, output_image_path)
            if reference_image_path
            else None
        )
        structural = self.default_score if reference_image_path else None
        aesthetic = self.aesthetic.score(output_image_path)
        technical = self.technical.score(output_image_path)
        wallpaper = self.wallpaper.score(output_image_path, task.width, task.height)
        vlm_judge = self.vlm.score(output_image_path, task.prompt.positive_prompt)
        values = [
            text_alignment,
            image_similarity,
            structural,
            aesthetic,
            technical,
            wallpaper,
            vlm_judge,
        ]
        available = [value for value in values if value is not None]
        return ScoreRecord(
            item_id=task.task_id,
            run_id=run_id,
            output_image_path=output_image_path,
            text_image_alignment_score=text_alignment,
            prompt_alignment_score=text_alignment,
            image_image_similarity_score=image_similarity,
            reference_fidelity_score=image_similarity,
            structural_similarity_score=structural,
            aesthetic_quality_score=aesthetic,
            aesthetic_score=aesthetic,
            technical_quality_score=technical,
            technical_score=technical,
            wallpaper_suitability_score=wallpaper,
            wallpaper_score=wallpaper,
            vlm_judge_score=vlm_judge,
            vlm_critique_score=vlm_judge,
            final_score=mean(available) if available else None,
            weighted_score=mean(available) if available else None,
            metrics={
                "text_image_alignment": text_alignment,
                "aesthetic_quality": aesthetic,
                "technical_quality": technical,
                "wallpaper_suitability": wallpaper,
            },
            score_explanations={
                "prompt_alignment_score": "Mock CLIP-style text-image score based on prompt/image presence.",
                "reference_fidelity_score": "Mock reference similarity; replace with CLIP/DINO/face/identity metrics.",
                "aesthetic_score": "Mock aesthetic score; replace with an aesthetic predictor.",
                "technical_score": "Mock technical score for blur/artifacts/resolution checks.",
                "wallpaper_score": "Aspect-ratio-aware wallpaper suitability heuristic.",
                "vlm_critique_score": "Mock VLM critique score with provider interface.",
            },
            warnings=[
                "Scores are mock/provider-interface outputs until real scorer providers are configured."
            ],
            notes="Mock score; replace provider with CLIP/SigLIP/LPIPS/DINO/VLM judge.",
        )


def aggregate_score_records(records: list[ScoreRecord]) -> dict[str, object]:
    summary: dict[str, object] = {"count": len(records), "fields": {}, "overall_mean": None}
    field_means: list[float] = []
    for field in SCORE_FIELDS:
        values = [
            getattr(record, field)
            for record in records
            if getattr(record, field) is not None
        ]
        avg = mean(values) if values else None
        summary["fields"][field] = {"mean": avg, "count": len(values)}
        if avg is not None:
            field_means.append(avg)
    summary["overall_mean"] = mean(field_means) if field_means else None
    return summary


def create_score_sheet(path: str | Path, image_paths: list[str]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["image_path", *MANUAL_SCORE_FIELDS, "badcase_category", "notes"])
        writer.writeheader()
        for image_path in image_paths:
            writer.writerow({"image_path": image_path})
    return target


def aggregate_scores(path: str | Path) -> dict[str, object]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    summary: dict[str, object] = {"count": len(rows), "fields": {}, "overall_mean": None}
    field_means: list[float] = []
    for field in MANUAL_SCORE_FIELDS:
        values = [float(row[field]) for row in rows if row.get(field) not in (None, "")]
        avg = mean(values) if values else None
        summary["fields"][field] = {"mean": avg, "count": len(values)}
        if avg is not None:
            field_means.append(avg)
    summary["overall_mean"] = mean(field_means) if field_means else None
    return summary
