from aigc2d.config import write_json
from aigc2d.retrieval import RunManifestRetrieval


def test_run_manifest_retrieval_queries(tmp_path):
    run_dir = tmp_path / "run_1"
    write_json(
        run_dir / "run_manifest.json",
        {
            "run_id": "run_1",
            "task_type": "img2img",
            "workflow_name": "active_workflow",
            "resolved_positive_prompt": "firefly cinematic wallpaper",
            "resolved_models": {"checkpoint": "animagine-xl"},
            "scoring_summary": {"overall_mean": 0.9},
        },
    )
    retrieval = RunManifestRetrieval(tmp_path)
    assert retrieval.high_score_by_character("firefly")
    assert retrieval.best_config_for_workflow("active_workflow")
    assert retrieval.good_results_for_checkpoint("animagine")
    assert retrieval.best_prompt_bundles_by_style("cinematic")
