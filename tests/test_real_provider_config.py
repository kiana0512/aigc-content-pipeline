import inspect

import pytest

from aigc2d.providers import ProviderError, create_analysis_providers
from aigc2d.providers.sam_provider import ExternalSam3Provider


def test_default_provider_factory_is_real_and_strict():
    signature = inspect.signature(create_analysis_providers)
    assert signature.parameters["provider"].default == "real"
    assert signature.parameters["strict_real"].default is True


def test_mock_provider_must_be_explicit():
    providers = create_analysis_providers(provider="mock", device="cpu", strict_real=False)
    assert providers.provider == "mock"
    assert providers.strict_real is False
    assert providers.enable_detector is False


def test_strict_real_missing_model_raises(tmp_path):
    config = tmp_path / "analysis_profiles.yaml"
    config.write_text(
        """
analysis:
  enable_detector: false
segmentation:
  provider: external_sam3
matting:
  model_root: missing/BiRefNet
tagger:
  model_root: missing/wd14
vlm:
  model_root: missing/qwen
  fallback_model_root: missing/florence
""",
        encoding="utf-8",
    )
    with pytest.raises(ProviderError, match="BiRefNet"):
        create_analysis_providers(provider="real", device="cpu", strict_real=True, config_path=config)


def test_real_factory_does_not_require_detector_when_disabled(tmp_path):
    root = tmp_path / "weights"
    for rel in ["segmentation/sam3.1", "segmentation/sam3", "segmentation/BiRefNet", "tagger/wd14", "vlm/qwen", "vlm/florence"]:
        (root / rel).mkdir(parents=True)
    config = tmp_path / "analysis_profiles.yaml"
    config.write_text(
        f"""
analysis:
  enable_detector: false
segmentation:
  provider: external_sam3
  conda_env: sam3
  python_exe: D:/Program Files/anaconda3/envs/sam3/python.exe
  sam3_repo_dir: {tmp_path / "sam3"}
  cli_script: scripts/sam3_segment_cli.py
matting:
  model_root: {root / "segmentation" / "BiRefNet"}
tagger:
  model_root: {root / "tagger" / "wd14"}
vlm:
  model_root: {root / "vlm" / "qwen"}
  fallback_model_root: {root / "vlm" / "florence"}
""",
        encoding="utf-8",
    )
    providers = create_analysis_providers(provider="real", device="cpu", strict_real=True, config_path=config)
    assert providers.detector is None
    assert providers.enable_detector is False
    assert isinstance(providers.segmentation, ExternalSam3Provider)
    assert providers.segmentation.python_exe == "D:/Program Files/anaconda3/envs/sam3/python.exe"
    assert providers.segmentation.sam3_repo_dir == str(tmp_path / "sam3")
    assert providers.segmentation.offline is True


def test_skip_tagger_skips_without_wd14_root(tmp_path):
    root = tmp_path / "weights"
    for rel in ["segmentation/BiRefNet", "vlm/qwen", "vlm/florence"]:
        (root / rel).mkdir(parents=True)
    (tmp_path / "sam3").mkdir()
    config = tmp_path / "analysis_profiles.yaml"
    config.write_text(
        f"""
analysis:
  enable_detector: false
segmentation:
  provider: external_sam3
  conda_env: sam3
  python_exe: D:/Program Files/anaconda3/envs/sam3/python.exe
  sam3_repo_dir: {tmp_path / "sam3"}
  cli_script: scripts/sam3_segment_cli.py
matting:
  model_root: {root / "segmentation" / "BiRefNet"}
tagger:
  provider: none
vlm:
  model_root: {root / "vlm" / "qwen"}
  fallback_model_root: {root / "vlm" / "florence"}
""",
        encoding="utf-8",
    )
    providers = create_analysis_providers(provider="real", device="cpu", strict_real=True, config_path=config)
    assert providers.tagger.provider_name == "TaggerSkipped"
    tag_out = providers.tagger.tag("dummy.jpg")
    assert tag_out["mock"] is False
    assert tag_out["tags"] == []


def test_wd14_discovery_prefers_tags_info_over_inv_csv(tmp_path):
    from aigc2d.providers.wd14_provider import _find_wd_tags_csv

    sub = tmp_path / "SmilingWolf" / "wd-v1-4-convnextv2-tagger-v2"
    sub.mkdir(parents=True)
    (sub / "inv_experiments.csv").write_text("a,b\n", encoding="utf-8")
    (sub / "tags_info.csv").write_text("name,category\nfoo,0\n", encoding="utf-8")
    assert _find_wd_tags_csv(tmp_path) == sub / "tags_info.csv"


def test_wd14_discovery_finds_nested_onnx(tmp_path):
    from aigc2d.providers.wd14_provider import _find_wd_onnx, _find_wd_tags_csv

    (tmp_path / "nested").mkdir(parents=True)
    (tmp_path / "nested" / "model.onnx").write_bytes(b"\x08")
    (tmp_path / "tags.csv").write_text("name,category\r\nfoo,0\r\n", encoding="utf-8")
    assert _find_wd_onnx(tmp_path) == tmp_path / "nested" / "model.onnx"
    assert _find_wd_tags_csv(tmp_path) == tmp_path / "tags.csv"
