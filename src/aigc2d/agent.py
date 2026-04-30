from __future__ import annotations

from itertools import product
from typing import Any, Protocol

from .retrieval import RetrievalStore
from .schemas import ExperimentConfig, GenerationTask, PromptSpec, ScoreRecord


class AgentProvider(Protocol):
    def recommend_generation_plan(
        self,
        character_id: str,
        task_goal: str,
        reference_pack: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    def recommend_retry_plan(
        self,
        run_manifest: dict[str, Any],
        score_summary: dict[str, Any],
        badcase_summary: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    def summarize_badcases(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        ...

    def suggest_best_workflow(self, task_type: str, available_inputs: dict[str, Any]) -> str:
        ...


class ExperimentAgent:
    def __init__(self, retrieval_store: RetrievalStore | None = None) -> None:
        self.retrieval_store = retrieval_store

    def select_workflow(self, mode: str, use_reference_control: bool = False) -> str:
        if mode == "text2img":
            return "active_workflow"
        if mode == "img2img" and use_reference_control:
            return "active_workflow"
        if mode == "img2img":
            return "active_workflow"
        if mode == "t2i":
            return "text2img_animagine"
        if mode == "i2i" and use_reference_control:
            return "img2img_animagine_ipadapter_controlnet"
        if mode == "i2i":
            return "img2img_animagine"
        raise NotImplementedError(f"Mode is reserved for later phase: {mode}")

    def build_sweep_plan(
        self,
        config: ExperimentConfig,
        prompt: PromptSpec,
        input_image_path: str | None = None,
        max_tasks: int | None = None,
    ) -> list[GenerationTask]:
        keys = list(config.sweep)
        values = [config.sweep[key] for key in keys]
        combinations = [dict(zip(keys, combo)) for combo in product(*values)] if keys else [{}]
        tasks: list[GenerationTask] = []
        for index, params in enumerate(combinations):
            if max_tasks is not None and len(tasks) >= max_tasks:
                break
            payload: dict[str, Any] = {
                "task_id": f"{config.name}_{index:03d}",
                "mode": config.mode,
                "workflow_name": config.workflow_name,
                "prompt": prompt,
                "model_name": config.model_name,
                "vae_name": config.vae_name,
                "width": config.width,
                "height": config.height,
                "seed": config.seed,
                "steps": config.steps,
                "cfg": config.cfg,
                "sampler": config.sampler,
                "scheduler": config.scheduler,
                "denoise": config.denoise,
                "input_image_path": input_image_path,
            }
            payload.update(params)
            tasks.append(GenerationTask(**payload))
        return tasks

    def suggest_next_round(self, scores: list[ScoreRecord]) -> list[str]:
        if not scores:
            return ["No scores yet; run a small baseline batch before expanding the sweep."]
        best = max(scores, key=lambda item: item.weighted_score or 0)
        suggestions = [
            f"Keep prompt/task pattern from {best.item_id} as current best baseline.",
            "Sweep one parameter at a time around the best seed, cfg, steps, and denoise.",
        ]
        if self.retrieval_store:
            matches = self.retrieval_store.search(best.item_id, limit=2)
            if matches:
                suggestions.append("Review similar historical records before the next run.")
        return suggestions

    def recommend_generation_plan(
        self,
        character_id: str | dict[str, Any],
        task_goal: str = "4k_wallpaper",
        reference_pack: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if isinstance(character_id, dict):
            request = character_id
            character = request.get("character_id", "unknown")
            task_goal = request.get("task_goal", task_goal)
            reference_pack = request.get("reference_pack", reference_pack or {})
        else:
            character = character_id
        reference_pack = reference_pack or {}
        task_type = "img2img_ipadapter_controlnet" if reference_pack.get("assets") else "text2img"
        workflow = self.suggest_best_workflow(task_type, {"reference_pack": reference_pack})
        return {
            "character_id": character,
            "task_goal": task_goal,
            "task_type": task_type,
            "workflow": workflow,
            "recommended_steps": [28, 36],
            "recommended_cfg": [4.5, 5.5],
            "notes": "Rule-based plan; retrieval can refine this after enough historical runs.",
        }

    def recommend_retry_plan(
        self,
        run_manifest: dict[str, Any],
        score_summary: dict[str, Any] | None = None,
        badcase_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        score_summary = score_summary or run_manifest.get("scoring_summary") or {}
        badcase_summary = badcase_summary or {}
        score = score_summary.get("overall_mean") or score_summary.get("final_score")
        return {
            "rerun": score is None or score < 0.75,
            "adjustments": {"denoise": [0.45, 0.55], "cfg": [4.5, 5.0]},
            "reason": "Low or missing score; keep reference control and sweep denoise/cfg.",
            "badcase_focus": badcase_summary.get("category_counts", {}),
        }

    def summarize_badcases(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for record in records:
            category = record.get("badcase_category") or "unknown"
            counts[category] = counts.get(category, 0) + 1
        return {"count": len(records), "category_counts": counts}

    def suggest_best_workflow(
        self,
        task_type: str,
        available_inputs: dict[str, Any] | bool | None = None,
    ) -> str:
        if isinstance(available_inputs, bool):
            use_reference_control = available_inputs
        else:
            available_inputs = available_inputs or {}
            use_reference_control = bool(
                available_inputs.get("identity_ref_images")
                or available_inputs.get("face_ref_images")
                or available_inputs.get("reference_pack")
            )
        if task_type == "img2img_ipadapter_controlnet" or (task_type == "img2img" and use_reference_control):
            return "active_workflow"
        if task_type == "img2img":
            return "active_workflow"
        if task_type == "upscale_4k":
            return "active_workflow"
        if task_type == "image2video":
            return "active_workflow"
        if task_type == "text2video":
            return "active_workflow"
        return "active_workflow"

    def summarize_reference_pack(self, reference_pack: Any) -> dict[str, Any]:
        assets = getattr(reference_pack, "assets", None)
        if assets is None and isinstance(reference_pack, dict):
            assets = reference_pack.get("assets", [])
        roles: dict[str, int] = {}
        for asset in assets or []:
            role = getattr(asset, "role", None) or asset.get("role", "unknown")
            roles[role] = roles.get(role, 0) + 1
        return {"asset_count": len(assets or []), "roles": roles}

    def summarize_badcases_from_run_dir(self, run_dir: str) -> dict[str, Any]:
        return {"run_dir": run_dir, "notes": "Hook for reading score CSV / run manifest badcase records."}
