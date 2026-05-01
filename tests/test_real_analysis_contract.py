import json
import os
from pathlib import Path

import pytest
from PIL import Image

from aigc2d.reference_analysis import ReferenceAnalyzer


def test_mock_analysis_contract_is_explicit_and_marked(tmp_path):
    image = tmp_path / "selected" / "init" / "firefly.png"
    image.parent.mkdir(parents=True)
    Image.new("RGB", (96, 96), "white").save(image)

    result = ReferenceAnalyzer(provider="mock", device="cpu", strict_real=False).analyze_pack(tmp_path)
    analyses = result.get("analyses") or []
    assert analyses, "expected at least one analysis record"
    analysis_path = Path(analyses[0]["analysis_path"])
    bundle_path = result["prompt_bundle_path"]
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))

    assert analysis["mock"] is True
    assert analysis["detections"] == []
    assert analysis["providers"]["detector"] == "disabled"
    assert analysis["segmentation"]["masks"]["subject"]["source_mode"] == "auto_subject"
    assert analysis["quality_checks"]["face_crop_mode"] in {"heuristic", "unavailable"}
    assert analysis["tags"]["tags"]
    assert analysis["caption"]["summary"]
    assert bundle["source_analysis_used"]
    assert bundle["mock"] is True


@pytest.mark.skipif(os.environ.get("RUN_REAL_ANALYSIS_TESTS") != "1", reason="real model integration test is opt-in")
def test_real_analysis_contract(tmp_path):
    image = tmp_path / "selected" / "init" / "firefly.png"
    image.parent.mkdir(parents=True)
    Image.new("RGB", (256, 256), "white").save(image)

    ReferenceAnalyzer(provider="real", device=os.environ.get("REAL_ANALYSIS_DEVICE", "cuda"), strict_real=True).analyze_pack(
        tmp_path
    )
    pack_summary_candidates = sorted((tmp_path / "processed" / "analysis").glob("*.json"))
    assert pack_summary_candidates, "expected processed/analysis/*.json"
    analysis_path = pack_summary_candidates[0]
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))

    assert analysis["mock"] is False
    assert analysis["quality_checks"]["mask_area_ratio"] > 0
    assert analysis["tags"]["tags"]
    assert analysis["caption"]["summary"]
