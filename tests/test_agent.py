from aigc2d.agent import ExperimentAgent


def test_agent_recommends_plan_and_workflow():
    agent = ExperimentAgent()
    plan = agent.recommend_generation_plan(
        character_id="firefly",
        task_goal="4k wallpaper",
        reference_pack={"assets": [{"role": "identity"}]},
    )
    assert plan["workflow"] == "active_workflow"
    assert agent.suggest_best_workflow("upscale_4k", {}) == "active_workflow"


def test_agent_retry_plan_uses_scores_and_badcases():
    agent = ExperimentAgent()
    retry = agent.recommend_retry_plan(
        {"run_id": "run_1"},
        {"overall_mean": 0.5},
        {"category_counts": {"identity_drift": 2}},
    )
    assert retry["rerun"] is True
    assert retry["badcase_focus"]["identity_drift"] == 2
