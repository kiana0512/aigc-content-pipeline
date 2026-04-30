from aigc2d.manifest import sample_task
from aigc2d.scoring import MockScoringProvider, aggregate_score_records


def test_mock_scoring_provider_returns_score_record():
    record = MockScoringProvider(default_score=0.8).score(
        task=sample_task(),
        output_image_path="out.png",
        run_id="run_1",
        reference_image_path="ref.png",
    )
    assert record.text_image_alignment_score is not None
    assert record.image_image_similarity_score is not None
    assert record.wallpaper_suitability_score is not None
    assert record.weighted_score is not None
    assert record.final_score is not None
    assert record.score_explanations["wallpaper_score"]
    assert record.warnings


def test_aggregate_score_records():
    record = MockScoringProvider(default_score=0.8).score(
        task=sample_task(),
        output_image_path="out.png",
        run_id="run_1",
    )
    summary = aggregate_score_records([record])
    assert summary["count"] == 1
    assert summary["fields"]["text_image_alignment_score"]["mean"] is not None
