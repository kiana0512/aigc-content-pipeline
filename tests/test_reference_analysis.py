from aigc2d.reference_analysis import ReferenceAnalyzer


def test_reference_analysis_writes_processed_artifacts(tmp_path):
    image = tmp_path / "selected" / "init" / "firefly.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"fake")

    result = ReferenceAnalyzer().analyze_pack(tmp_path)

    assert result["prompt_bundle"].positive_prompt
    assert result["prompt_bundle_path"].exists()
    assert (tmp_path / "processed" / "caption" / "firefly.json").exists()
    assert (tmp_path / "processed" / "tags" / "firefly.json").exists()
    assert (tmp_path / "processed" / "analysis" / "firefly.json").exists()
    assert (tmp_path / "processed" / "masks" / "firefly_mask.png").exists()
    assert (tmp_path / "processed" / "raw" / "firefly" / "source.json").exists()
    assert (tmp_path / "processed" / "raw" / "firefly" / "subject_mask.png").exists()
