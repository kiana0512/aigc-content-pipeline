from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from .config import PROJECT_ROOT
from .config import load_json


class RetrievalStore(Protocol):
    def add(self, record: dict[str, Any]) -> None:
        ...

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        ...


class JsonlRetrievalStore:
    def __init__(self, path: str | Path = PROJECT_ROOT / "results" / "retrieval.jsonl") -> None:
        self.path = Path(path)

    def add(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        terms = {term.lower() for term in query.split() if term.strip()}
        rows = self.all()
        if not terms:
            return rows[:limit]
        scored: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            text = json.dumps(row, ensure_ascii=False).lower()
            score = sum(1 for term in terms if term in text)
            if score:
                scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [row for _, row in scored[:limit]]


class RunManifestRetrieval:
    def __init__(self, runs_root: str | Path = PROJECT_ROOT / "results" / "runs") -> None:
        self.runs_root = Path(runs_root)

    def load_manifests(self) -> list[dict[str, Any]]:
        return [
            load_json(path)
            for path in sorted(self.runs_root.glob("*/run_manifest.json"))
        ] if self.runs_root.exists() else []

    def search_runs(
        self,
        character_name: str = "",
        style: str = "",
        task_type: str = "",
        model_name: str = "",
        min_score: float | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        rows = self.load_manifests()
        matched: list[dict[str, Any]] = []
        for row in rows:
            text = str(row).lower()
            if character_name and character_name.lower() not in text:
                continue
            if style and style.lower() not in text:
                continue
            if task_type and row.get("task_type") != task_type:
                continue
            if model_name and model_name.lower() not in text:
                continue
            score = (row.get("scoring_summary") or {}).get("overall_mean")
            if min_score is not None and (score is None or score < min_score):
                continue
            matched.append(row)
        return matched[:limit]

    def search_prompts(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        return [
            {
                "run_id": row.get("run_id"),
                "positive_prompt": row.get("resolved_positive_prompt"),
                "negative_prompt": row.get("resolved_negative_prompt"),
            }
            for row in self.search_runs(limit=100)
            if query.lower() in str(row.get("resolved_positive_prompt", "")).lower()
        ][:limit]

    def high_score_cases(self, min_score: float = 0.75, limit: int = 10) -> list[dict[str, Any]]:
        return self.search_runs(min_score=min_score, limit=limit)

    def high_score_by_character(self, character_id: str, limit: int = 10) -> list[dict[str, Any]]:
        return self.search_runs(character_name=character_id, min_score=0.75, limit=limit)

    def best_config_for_workflow(self, workflow_name: str, limit: int = 5) -> list[dict[str, Any]]:
        rows = [row for row in self.load_manifests() if row.get("workflow_name") == workflow_name]
        rows.sort(key=lambda row: (row.get("scoring_summary") or {}).get("overall_mean") or 0, reverse=True)
        return rows[:limit]

    def good_results_for_checkpoint(self, checkpoint: str, limit: int = 10) -> list[dict[str, Any]]:
        return self.search_runs(model_name=checkpoint, min_score=0.75, limit=limit)

    def best_prompt_bundles_by_style(self, style_preset: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = [
            row for row in self.load_manifests()
            if style_preset.lower() in str(row.get("prompt_row", "")).lower()
            or style_preset.lower() in str(row.get("resolved_positive_prompt", "")).lower()
        ]
        rows.sort(key=lambda row: (row.get("scoring_summary") or {}).get("overall_mean") or 0, reverse=True)
        return rows[:limit]

    def badcase_samples(self, category: str, limit: int = 10) -> list[dict[str, Any]]:
        return [
            row for row in self.load_manifests()
            if category.lower() in str(row.get("badcase_summary", "")).lower()
        ][:limit]
