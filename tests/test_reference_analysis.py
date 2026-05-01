from aigc2d.reference_analysis import ReferenceAnalyzer
from PIL import Image


def test_reference_analysis_writes_processed_artifacts(tmp_path):
    image = tmp_path / "selected" / "init" / "firefly.png"
    image.parent.mkdir(parents=True)
    Image.new("RGB", (64, 64), "white").save(image)

    result = ReferenceAnalyzer(provider="mock", device="cpu", strict_real=False).analyze_pack(tmp_path)

    wid = "selected_init_firefly.png"
    assert result["prompt_bundle"].positive_prompt
    assert result["prompt_bundle_path"].exists()
    assert (tmp_path / "processed" / "caption" / f"{wid}.json").exists()
    assert (tmp_path / "processed" / "tags" / f"{wid}.json").exists()
    assert (tmp_path / "processed" / "analysis" / f"{wid}.json").exists()
    assert (tmp_path / "processed" / "raw" / wid / "source.json").exists()
    assert (tmp_path / "processed" / "raw" / wid / "subject_mask.png").exists()
