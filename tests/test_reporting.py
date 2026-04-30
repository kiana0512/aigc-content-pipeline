from aigc2d.reporting import build_markdown_report
from aigc2d.manifest import create_run_manifest, sample_task
from aigc2d.reporting import summarize_run


def test_build_markdown_report_contains_sections():
    report = build_markdown_report(
        "Demo",
        manifest_summary=[{"task_name": "case_01", "prompt_template": "portrait_default", "checkpoint_profile": "base"}],
        score_summary={"overall_mean": 4.0},
        badcase_summary={"category_counts": {"hands": 1}},
    )
    assert "# Demo" in report
    assert "Score Summary" in report
    assert "Badcase Summary" in report


def test_summarize_run():
    manifest = create_run_manifest("run_1", sample_task(), output_images=["out.png"])
    summary = summarize_run(manifest)
    assert summary["run_id"] == "run_1"
    assert summary["output_count"] == 1
    assert summary["score_summary"]["count"] == 0
