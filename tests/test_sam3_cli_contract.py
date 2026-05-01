import numpy as np
import pytest
from pathlib import Path

from scripts.sam3_segment_cli import (
    build_candidate,
    build_local_sam3_model,
    candidates_from_predictor_outputs,
    collect_best_propagate_outputs,
    is_sam31_checkpoint,
    resolve_checkpoint_for_backend,
    resolve_local_model_paths,
    sam31_tune_for_reference_image,
    score_propagate_outputs,
    should_use_multiplex_predictor,
    start_predictor_session_compat,
)


def test_to_numpy_masks_accepts_cuda_bfloat16_like_dtype():
    torch = pytest.importorskip("torch")
    from scripts.sam3_segment_cli import _to_numpy_masks

    t = torch.tensor([[1.0, 0.0], [0.0, 1.0]], dtype=torch.bfloat16)
    out = _to_numpy_masks(t)
    assert len(out) == 1
    assert out[0].shape == (2, 2)


def test_sam3_cli_candidate_scoring_selects_valid_mask():
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[20:80, 30:70] = 1
    candidate = build_candidate(
        mask=mask,
        boxes=[],
        scores=[0.9],
        index=0,
        prompt="main subject",
        width=100,
        height=100,
        min_ratio=0.03,
        max_ratio=0.90,
    )
    assert candidate is not None
    assert candidate["prompt"] == "main subject"
    assert candidate["area_ratio"] > 0
    assert candidate["box_xyxy"] == [30, 20, 70, 80]


def test_sam3_cli_rejects_empty_mask():
    mask = np.zeros((100, 100), dtype=np.uint8)
    candidate = build_candidate(mask, [], [0.9], 0, "main subject", 100, 100, 0.03, 0.90)
    assert candidate is None


def test_sam3_cli_refuses_no_local_model_signature():
    def fake_builder():
        return object()

    with pytest.raises(RuntimeError, match="Refusing to call build_sam3_image_model"):
        build_local_sam3_model(fake_builder, {"model_root": "", "config_path": "", "checkpoint_path": ""}, "cuda")


def test_sam3_cli_uses_model_root_signature():
    captured = {}

    def fake_builder(model_root, device):
        captured["model_root"] = model_root
        captured["device"] = device
        return object()

    model = build_local_sam3_model(fake_builder, {"model_root": "F:/local/sam3", "config_path": "", "checkpoint_path": ""}, "cuda")
    assert model is not None
    assert captured == {"model_root": "F:/local/sam3", "device": "cuda"}


def test_sam3_cli_uses_checkpoint_and_disables_hf():
    captured = {}

    def fake_builder(checkpoint_path=None, load_from_HF=True, device="cpu"):
        captured["checkpoint_path"] = checkpoint_path
        captured["load_from_HF"] = load_from_HF
        captured["device"] = device
        return object()

    model = build_local_sam3_model(
        fake_builder,
        {"model_root": "F:/local/sam3", "config_path": "F:/local/sam3/config.json", "checkpoint_path": "F:/local/sam3/sam3.1_multiplex.pt"},
        "cuda",
    )
    assert model is not None
    assert captured == {
        "checkpoint_path": "F:/local/sam3/sam3.1_multiplex.pt",
        "load_from_HF": False,
        "device": "cuda",
    }


def test_sam3_cli_detects_sam31_multiplex_checkpoint():
    assert is_sam31_checkpoint("F:/local/sam3/sam3.1_multiplex.pt", "", "")
    assert is_sam31_checkpoint("", "F:/local/weights/segmentation/sam3.1", "")
    assert not is_sam31_checkpoint("F:/local/sam3/sam3.pt", "", "")


def test_should_use_multiplex_predictor_forced_backends():
    assert should_use_multiplex_predictor("multiplex", "F:/sam3/sam3.pt", "", "") is True
    assert should_use_multiplex_predictor("image", "F:/sam3/sam3.1_multiplex.pt", "", "") is False
    assert should_use_multiplex_predictor("auto", "F:/sam3/sam3.1_multiplex.pt", "", "") is True


def test_resolve_checkpoint_prefers_standard_names_for_image_backend(tmp_path):
    (tmp_path / "sam3.1_multiplex.pt").write_bytes(b"x")
    direct = tmp_path / "sam3.pt"
    direct.write_bytes(b"y")
    assert resolve_checkpoint_for_backend(tmp_path, "", "image") == direct.resolve()


def test_resolve_checkpoint_multiplex_backend_prefers_multiplex_file(tmp_path):
    (tmp_path / "sam3.pt").write_bytes(b"x")
    mux = tmp_path / "sam3.1_multiplex.pt"
    mux.write_bytes(b"y")
    assert resolve_checkpoint_for_backend(tmp_path, "", "multiplex") == mux.resolve()


def test_resolve_local_model_paths_backend_image_skips_multiplex_under_auto_scan(tmp_path):
    (tmp_path / "sam3.1_multiplex.pt").write_bytes(b"x")
    only = tmp_path / "candidate.pt"
    only.write_bytes(b"y")
    out = resolve_local_model_paths(str(tmp_path), "", "", sam3_backend="image")
    assert Path(out["checkpoint_path"]) == only.resolve()


def test_sam3_cli_reads_predictor_outputs():
    mask = np.zeros((1, 100, 100), dtype=bool)
    mask[0, 20:80, 30:70] = True
    candidates = candidates_from_predictor_outputs(
        {"out_binary_masks": mask, "out_probs": [0.8], "out_boxes_xywh": [[30, 20, 40, 60]]},
        "person",
        100,
        100,
        0.03,
        0.90,
    )
    assert len(candidates) == 1
    assert candidates[0]["prompt"] == "person"


def test_sam3_cli_starts_predictor_session_with_supported_kwargs_only():
    captured = {}

    class FakeModel:
        def init_state(self, resource_path, offload_video_to_cpu=False, async_loading_frames=False):
            captured["resource_path"] = resource_path
            captured["offload_video_to_cpu"] = offload_video_to_cpu
            captured["async_loading_frames"] = async_loading_frames
            return {"ok": True}

    class FakePredictor:
        async_loading_frames = False

        def __init__(self):
            self.model = FakeModel()
            self._all_inference_states = {}

    predictor = FakePredictor()
    session_id = start_predictor_session_compat(predictor, "image.jpg")

    assert session_id in predictor._all_inference_states
    assert predictor._all_inference_states[session_id]["state"] == {"ok": True}
    assert captured == {
        "resource_path": "image.jpg",
        "offload_video_to_cpu": False,
        "async_loading_frames": False,
    }


def test_sam31_tune_disables_masklet_confirmation():
    class DummyModel:
        masklet_confirmation_enable = True

    class DummyPredictor:
        def __init__(self) -> None:
            self.model = DummyModel()

    predictor = DummyPredictor()
    sam31_tune_for_reference_image(predictor, enabled=True)
    assert predictor.model.masklet_confirmation_enable is False

    predictor2 = DummyPredictor()
    sam31_tune_for_reference_image(predictor2, enabled=False)
    assert predictor2.model.masklet_confirmation_enable is True


def test_collect_propagate_picks_best_nonempty_masks():
    masks_a = np.zeros((1, 10, 10), dtype=bool)
    masks_b = np.zeros((2, 10, 10), dtype=bool)
    masks_b[0, 2:8, 2:8] = True

    class FakePredictor:
        def handle_stream_request(self, request):
            assert request["type"] == "propagate_in_video"
            assert request["propagation_direction"] == "forward"
            assert abs(request["output_prob_thresh"] - 0.11) < 1e-9
            yield {"frame_index": 0, "outputs": {"out_binary_masks": masks_a}}
            yield {"frame_index": 0, "outputs": {"out_binary_masks": masks_b}}

    predictor = FakePredictor()
    out = collect_best_propagate_outputs(predictor, "sid", 0.11, debug=False)
    assert np.asarray(out["out_binary_masks"]).sum() > 0


def test_score_propagate_prioritizes_multi_instance():
    tiny = np.zeros((1, 4, 4), dtype=bool)
    tiny[0, :, :] = True
    two = np.zeros((2, 4, 4), dtype=bool)
    two[0, 0:2, 0:2] = True
    two[1, 2:4, 2:4] = True
    assert score_propagate_outputs({"out_binary_masks": two}) > score_propagate_outputs({"out_binary_masks": tiny})
