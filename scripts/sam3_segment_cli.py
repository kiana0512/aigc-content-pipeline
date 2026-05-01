from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SAM3/SAM3.1 segmentation in the dedicated sam3 conda env.")
    parser.add_argument("--image", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--prompts", nargs="+", default=["person", "anime character", "main subject", "girl", "character"])
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--min-mask-area-ratio", type=float, default=0.03)
    parser.add_argument("--max-mask-area-ratio", type=float, default=0.90)
    parser.add_argument(
        "--output-prob-thresh",
        type=float,
        default=0.2,
        help="Probability threshold forwarded to SAM3.1 predictor add_prompt/propagate (lower keeps more tentative masks)",
    )
    parser.add_argument("--model-root", default="")
    parser.add_argument("--sam3-model-root", default="")
    parser.add_argument("--sam3-config-path", default="")
    parser.add_argument("--sam3-checkpoint-path", default="")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--conda-env", default="sam3")
    parser.add_argument("--sam3-repo-dir", default="")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--sam31-image-mode",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="SAM3.1 multiplex only: disable masklet confirmation + forward-only propagate.",
    )
    parser.add_argument(
        "--sam3-backend",
        choices=("auto", "image", "multiplex"),
        default="auto",
        help="'image' uses build_sam3_image_model + Sam3Processor (few reference stills). "
        "'multiplex' uses SAM3.1 predictor. 'auto' picks multiplex if paths look like sam3.1/multiplex.",
    )
    parser.add_argument(
        "--sam3-image-bf16-autocast",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="SAM3 image on CUDA: use TF32 + persistent autocast(bfloat16) when torch.cuda.is_bf16_supported() is True "
        "(matches sam3/examples/sam3_image_predictor_example.ipynb); otherwise FP32 weights. "
        "If BF16 autocast hits an unsupported op, the CLI retries without autocast. "
        "Use --no-sam3-image-bf16-autocast to force the FP32 path.",
    )
    args = parser.parse_args()
    add_sam3_repo_to_path(args.sam3_repo_dir)
    if args.offline:
        set_offline_env()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    try:
        result = run_sam3(
            image_path=Path(args.image),
            out_dir=out_dir,
            prompts=args.prompts,
            device=args.device,
            min_mask_area_ratio=args.min_mask_area_ratio,
            max_mask_area_ratio=args.max_mask_area_ratio,
            output_prob_thresh=args.output_prob_thresh,
            model_root=args.sam3_model_root or args.model_root,
            config_path=args.sam3_config_path,
            checkpoint_path=args.sam3_checkpoint_path,
            offline=args.offline,
            sam3_repo_dir=args.sam3_repo_dir,
            conda_env=args.conda_env,
            sam31_image_mode=args.sam31_image_mode,
            debug=args.debug,
            sam3_backend=args.sam3_backend,
            sam3_image_bf16_autocast=args.sam3_image_bf16_autocast,
            started=started,
        )
    except Exception as exc:
        error_payload = {
            "mock": False,
            "provider_name": "SAM3.1-external-conda",
            "source_mode": "external_conda_sam3_text_prompt",
            "image_path": str(args.image),
            "device": args.device,
            "conda_env": args.conda_env,
            "runtime_ms": int((time.perf_counter() - started) * 1000),
            "errors": [str(exc)],
            "warnings": [],
        }
        (out_dir / "segmentation.json").write_text(json.dumps(error_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"SAM3 segmentation failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    (out_dir / "segmentation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(out_dir / "segmentation.json"))


def run_sam3(
    image_path: Path,
    out_dir: Path,
    prompts: list[str],
    device: str,
    min_mask_area_ratio: float,
    max_mask_area_ratio: float,
    output_prob_thresh: float,
    model_root: str,
    config_path: str,
    checkpoint_path: str,
    offline: bool,
    sam3_repo_dir: str,
    conda_env: str,
    sam31_image_mode: bool,
    debug: bool,
    sam3_backend: str,
    sam3_image_bf16_autocast: bool,
    started: float,
) -> dict[str, Any]:
    try:
        from sam3.model.sam3_image_processor import Sam3Processor
        from sam3.model_builder import build_sam3_image_model
    except Exception as exc:
        raise RuntimeError(
            "Python package 'sam3' or required SAM3 APIs are not importable in this environment.\n"
            f"{sam3_import_diagnostics(sam3_repo_dir)}\n"
            "Please install or expose the local SAM3 repo inside the dedicated conda env with:\n"
            "  conda activate sam3\n"
            "  cd F:/python_project/game-aigc-asset-workflow/sam3\n"
            "  pip install -e ."
        ) from exc

    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    try:
        resolved = resolve_local_model_paths(model_root, config_path, checkpoint_path, sam3_backend=sam3_backend)
        print(f"SAM3 repo dir: {sam3_repo_dir or '<not provided>'}", file=sys.stderr)
        print(f"SAM3 model root: {resolved['model_root'] or '<not provided>'}", file=sys.stderr)
        print(f"SAM3 backend: {sam3_backend}", file=sys.stderr)
        print(f"SAM3 config path: {resolved['config_path'] or '<auto/not used>'}", file=sys.stderr)
        print(f"SAM3 checkpoint path: {resolved['checkpoint_path'] or '<auto/not used>'}", file=sys.stderr)
        print(f"offline: {str(offline).lower()}", file=sys.stderr)
        multiplex = should_use_multiplex_predictor(sam3_backend, resolved["checkpoint_path"], resolved["model_root"], resolved["config_path"])
        if multiplex:
            candidates = run_sam31_predictor(
                image_path=image_path,
                prompts=prompts,
                checkpoint_path=resolved["checkpoint_path"],
                output_prob_thresh=output_prob_thresh,
                min_mask_area_ratio=min_mask_area_ratio,
                max_mask_area_ratio=max_mask_area_ratio,
                width=width,
                height=height,
                sam31_image_mode=sam31_image_mode,
                debug=debug,
            )
            return finalize_result(
                candidates=candidates,
                out_dir=out_dir,
                image_path=image_path,
                device=device,
                conda_env=conda_env,
                prompts=prompts,
                started=started,
            )
        want_bf16 = bool(sam3_image_bf16_autocast and _sam3_cuda_bf16_autocast_allowed(device))
        if sam3_image_bf16_autocast and device.lower().split(":")[0] == "cuda" and not want_bf16:
            print(
                "sam3 image: skipping bfloat16 autocast (this GPU reports no usable CUDA bfloat16; using FP32 weights).",
                file=sys.stderr,
            )
        amp_ctx = _sam3_enter_official_cuda_bf16_inference(device, want_bf16)
        if amp_ctx is not None:
            print(
                "sam3 image CUDA: TF32 + bfloat16 autocast (parity with sam3/examples/sam3_image_predictor_example.ipynb)",
                file=sys.stderr,
            )

        def _make_image_stack(*, fp32_weights: bool) -> tuple[Any, Any, dict[str, Any]]:
            m = build_local_sam3_model(build_sam3_image_model, resolved, device)
            if hasattr(m, "to"):
                m = m.to(device)
            if fp32_weights:
                m = m.float()
            p = Sam3Processor(m, device=device)
            st = p.set_image(image)
            return m, p, st

        try:
            _, processor, state = _make_image_stack(fp32_weights=amp_ctx is None)
        except RuntimeError as first_exc:
            if amp_ctx is not None and _should_retry_sam3_image_without_bf16_autocast(first_exc):
                _sam3_exit_cuda_bf16_inference(amp_ctx)
                amp_ctx = None
                print(
                    "sam3 image: bfloat16 autocast hit an unsupported op on this stack; retrying without autocast and with FP32 weights.",
                    file=sys.stderr,
                )
                _, processor, state = _make_image_stack(fp32_weights=True)
            else:
                if amp_ctx is not None:
                    _sam3_exit_cuda_bf16_inference(amp_ctx)
                raise first_exc from first_exc
    except Exception as exc:
        message = str(exc)
        if any(token in message.lower() for token in ["huggingface.co", "facebook/sam3", "gated repo", "401 client error"]):
            raise RuntimeError(
                "SAM3 tried to access HuggingFace. This is forbidden in offline local mode. "
                "Please set sam3_model_root / sam3_config_path / sam3_checkpoint_path to local files."
            ) from exc
        raise RuntimeError(f"failed to initialize SAM3 image model: {exc}") from exc

    candidates: list[dict[str, Any]] = []
    for prompt in prompts:
        try:
            output = processor.set_text_prompt(state=state, prompt=prompt)
        except Exception as exc:
            candidates.append({"prompt": prompt, "error": str(exc), "score": 0.0})
            continue
        masks = output.get("masks", [])
        boxes = output.get("boxes", [])
        scores = output.get("scores", [])
        for index, mask in enumerate(_to_numpy_masks(masks)):
            candidate = build_candidate(mask, boxes, scores, index, prompt, width, height, min_mask_area_ratio, max_mask_area_ratio)
            if candidate:
                candidates.append(candidate)
    valid = [item for item in candidates if "mask" in item]
    if not valid:
        raise RuntimeError(
            "no valid SAM3 subject mask candidates matched area and foreground constraints. "
            "Tune --min-mask-area-ratio / --max-mask-area-ratio and text prompts; for SAM3.1 multiplex also try "
            "a lower --output-prob-thresh and keep --sam31-image-mode (default: disables masklet confirmation on single images)."
        )
    return finalize_result(
        candidates=candidates,
        out_dir=out_dir,
        image_path=image_path,
        device=device,
        conda_env=conda_env,
        prompts=prompts,
        started=started,
    )


def run_sam31_predictor(
    image_path: Path,
    prompts: list[str],
    checkpoint_path: str,
    output_prob_thresh: float,
    min_mask_area_ratio: float,
    max_mask_area_ratio: float,
    width: int,
    height: int,
    sam31_image_mode: bool,
    debug: bool,
) -> list[dict[str, Any]]:
    from sam3.model_builder import build_sam3_predictor

    if not checkpoint_path:
        raise RuntimeError("SAM3.1 multiplex mode requires a local sam3.1_multiplex.pt checkpoint.")
    predictor = build_sam3_predictor(
        checkpoint_path=checkpoint_path,
        version="sam3.1",
        compile=False,
        warm_up=False,
        async_loading_frames=False,
    )
    sam31_tune_for_reference_image(predictor, enabled=sam31_image_mode)
    session_id = start_predictor_session_compat(predictor, str(image_path))
    print(f"sam3.1 output_prob_thresh: {output_prob_thresh}", file=sys.stderr)
    if sam31_image_mode:
        print("sam3.1 image mode: masklet_confirmation disabled, propagate forward-only", file=sys.stderr)

    candidates: list[dict[str, Any]] = []
    try:
        for index, prompt in enumerate(prompts):
            try:
                if index > 0:
                    predictor.handle_request({"type": "reset_session", "session_id": session_id})
                response = predictor.handle_request(
                    {
                        "type": "add_prompt",
                        "session_id": session_id,
                        "frame_index": 0,
                        "text": prompt,
                        "output_prob_thresh": output_prob_thresh,
                    }
                )
                propagated = collect_best_propagate_outputs(
                    predictor,
                    session_id,
                    output_prob_thresh=output_prob_thresh,
                    debug=debug,
                )
                from_propagate = candidates_from_predictor_outputs(
                    propagated,
                    prompt,
                    width,
                    height,
                    min_mask_area_ratio,
                    max_mask_area_ratio,
                )
                from_add_prompt = candidates_from_predictor_outputs(
                    response.get("outputs", {}),
                    prompt,
                    width,
                    height,
                    min_mask_area_ratio,
                    max_mask_area_ratio,
                )
                candidates.extend(from_propagate if from_propagate else from_add_prompt)
            except Exception as exc:
                candidates.append({"prompt": prompt, "error": str(exc), "score": 0.0})
    finally:
        try:
            predictor.handle_request({"type": "close_session", "session_id": session_id})
        except Exception:
            pass
    return candidates


def sam31_tune_for_reference_image(predictor: Any, *, enabled: bool) -> None:
    """SAM3.1 multiplex defaults target video tracking; still images never satisfy masklet_confirmation."""
    if not enabled:
        return
    model = getattr(predictor, "model", None)
    if model is None:
        return
    if hasattr(model, "masklet_confirmation_enable"):
        model.masklet_confirmation_enable = False


def score_propagate_outputs(outputs: dict[str, Any]) -> float:
    """Prefer outputs with more instance masks / foreground pixels (empty tensor -> 0)."""
    bm = first_present(outputs, ["out_binary_masks", "masks", "pred_masks"], None)
    if bm is None:
        return 0.0
    arr = _torch_to_numpy_f32(bm) if hasattr(bm, "detach") else np.asarray(bm)
    if arr.size == 0:
        return 0.0
    if arr.ndim == 2:
        return float(arr.sum())
    if arr.ndim == 3:
        n_inst = sum(bool(arr[i].any()) for i in range(arr.shape[0]))
        return float(n_inst * 1_000_000_000 + arr.sum())
    if arr.ndim == 4:
        n_inst = sum(bool(arr[i].any()) for i in range(arr.shape[0]))
        return float(n_inst * 1_000_000_000 + arr.sum())
    return float(arr.sum())


def collect_best_propagate_outputs(predictor: Any, session_id: str, output_prob_thresh: float, *, debug: bool) -> dict[str, Any]:
    """Run propagate_in_video forward-only (single-image safe) and pick the richest mask output."""
    best: dict[str, Any] = {}
    best_score = -1.0
    n_msg = 0
    req: dict[str, Any] = {
        "type": "propagate_in_video",
        "session_id": session_id,
        "output_prob_thresh": output_prob_thresh,
        "propagation_direction": "forward",
    }
    for response in predictor.handle_stream_request(req):
        n_msg += 1
        out = response.get("outputs") or {}
        score = score_propagate_outputs(out)
        if score > best_score:
            best_score = score
            best = out
        if debug:
            fid = response.get("frame_index")
            bm = first_present(out, ["out_binary_masks"], None)
            shape = getattr(bm, "shape", None)
            print(f"debug propagate chunk frame_index={fid} score={score} mask_shape={shape}", file=sys.stderr)
    if debug:
        print(f"debug propagate total_chunks={n_msg} best_score={best_score}", file=sys.stderr)
    return best if best_score > 0 else {}


def start_predictor_session_compat(predictor: Any, resource_path: str) -> str:
    """Start a SAM3 predictor session while tolerating local API signature drift."""
    init_kwargs: dict[str, Any] = {
        "resource_path": resource_path,
        "offload_video_to_cpu": False,
        "offload_state_to_cpu": False,
    }
    if hasattr(predictor, "async_loading_frames"):
        init_kwargs["async_loading_frames"] = predictor.async_loading_frames
    if hasattr(predictor, "video_loader_type"):
        init_kwargs["video_loader_type"] = predictor.video_loader_type
    sig = inspect.signature(predictor.model.init_state)
    filtered_kwargs = {key: value for key, value in init_kwargs.items() if key in sig.parameters}
    inference_state = predictor.model.init_state(**filtered_kwargs)
    session_id = str(uuid.uuid4())
    predictor._all_inference_states[session_id] = {
        "state": inference_state,
        "session_id": session_id,
        "start_time": time.time(),
        "last_use_time": time.time(),
    }
    return session_id


def candidates_from_predictor_outputs(
    outputs: dict[str, Any],
    prompt: str,
    width: int,
    height: int,
    min_mask_area_ratio: float,
    max_mask_area_ratio: float,
) -> list[dict[str, Any]]:
    masks = first_present(outputs, ["out_binary_masks", "masks", "pred_masks"], [])
    boxes = first_present(outputs, ["out_boxes_xywh", "boxes", "pred_boxes"], [])
    scores = first_present(outputs, ["out_probs", "scores", "pred_scores"], [])
    candidates: list[dict[str, Any]] = []
    for index, mask in enumerate(_to_numpy_masks(masks)):
        candidate = build_candidate(mask, boxes, scores, index, prompt, width, height, min_mask_area_ratio, max_mask_area_ratio)
        if candidate:
            candidates.append(candidate)
    return candidates


def first_present(mapping: dict[str, Any], keys: list[str], default: Any) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def finalize_result(
    candidates: list[dict[str, Any]],
    out_dir: Path,
    image_path: Path,
    device: str,
    conda_env: str,
    prompts: list[str],
    started: float,
) -> dict[str, Any]:
    valid = [item for item in candidates if "mask" in item]
    if not valid:
        raise RuntimeError(
            "no valid SAM3 subject mask candidates matched area and foreground constraints. "
            "Tune --min-mask-area-ratio / --max-mask-area-ratio and text prompts; for SAM3.1 multiplex also try "
            "a lower --output-prob-thresh and keep --sam31-image-mode (default: disables masklet confirmation on single images)."
        )
    selected = max(valid, key=lambda item: item["combined_score"])
    mask_path = out_dir / "subject_mask.png"
    save_mask(selected["mask"], mask_path)
    selected_public = {key: value for key, value in selected.items() if key != "mask"}
    public_candidates = [{key: value for key, value in item.items() if key not in {"mask"}} for item in candidates]
    return {
        "mock": False,
        "provider_name": "SAM3.1-external-conda",
        "source_mode": "external_conda_sam3_text_prompt",
        "image_path": str(image_path),
        "device": device,
        "conda_env": conda_env,
        "prompts_used": prompts,
        "selected_prompt": selected["prompt"],
        "runtime_ms": int((time.perf_counter() - started) * 1000),
        "masks": {
            "subject": {
                "mask_path": str(mask_path),
                "area_ratio": selected["area_ratio"],
                "score": selected["score"],
                "source_prompt": selected["prompt"],
                "box_xyxy": selected["box_xyxy"],
                "source_mode": "external_conda_sam3_text_prompt",
            }
        },
        "results": {"masks": {"subject": {"mask_path": str(mask_path)}}},
        "candidates": public_candidates,
        "selected_candidate": selected_public,
        "warnings": [],
        "errors": [],
    }


def is_sam31_checkpoint(checkpoint_path: str, model_root: str, config_path: str) -> bool:
    haystack = " ".join([checkpoint_path, model_root, config_path]).lower()
    return "sam3.1" in haystack or "multiplex" in haystack


def should_use_multiplex_predictor(backend: str, checkpoint_path: str, model_root: str, config_path: str) -> bool:
    mode = str(backend).strip().lower()
    if mode == "multiplex":
        return True
    if mode == "image":
        return False
    if mode == "auto":
        return is_sam31_checkpoint(checkpoint_path, model_root, config_path)
    raise RuntimeError(f"unknown sam3 backend: {backend!r}; expected auto|image|multiplex")


def build_candidate(
    mask: np.ndarray,
    boxes: Any,
    scores: Any,
    index: int,
    prompt: str,
    width: int,
    height: int,
    min_ratio: float,
    max_ratio: float,
) -> dict[str, Any] | None:
    binary = (mask > 0).astype(np.uint8)
    area_ratio = float(binary.sum() / binary.size)
    if area_ratio <= 0.0 or area_ratio >= 1.0 or area_ratio < min_ratio or area_ratio > max_ratio:
        return None
    ys, xs = np.where(binary > 0)
    x1, y1, x2, y2 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    cx = float(xs.mean()) / max(width, 1)
    cy = float(ys.mean()) / max(height, 1)
    center_score = 1.0 - min(1.0, abs(cx - 0.5) + abs(cy - 0.45))
    area_score = 1.0 - min(1.0, abs(area_ratio - 0.35) / 0.35)
    score = _score_at(scores, index)
    combined = score * 0.65 + center_score * 0.25 + area_score * 0.10
    return {
        "prompt": prompt,
        "score": score,
        "area_ratio": area_ratio,
        "center_score": center_score,
        "area_score": area_score,
        "combined_score": combined,
        "box_xyxy": _box_at(boxes, index) or [x1, y1, x2, y2],
        "mask": binary * 255,
    }


def _torch_to_numpy_f32(t: Any) -> np.ndarray:
    """NumPy arrays cannot carry bfloat16; SAM3 under CUDA BF16 autocast returns BF16/FP16 tensors."""
    import torch

    x = t.detach().cpu()
    if x.dtype in (torch.bfloat16, torch.float16):
        x = x.float()
    return np.asarray(x)


def _to_numpy_masks(masks: Any) -> list[np.ndarray]:
    if hasattr(masks, "detach"):
        array = _torch_to_numpy_f32(masks)
    else:
        array = np.asarray(masks)
    if array.ndim == 2:
        return [array]
    if array.ndim == 3:
        return [array[index] for index in range(array.shape[0])]
    if array.ndim == 4:
        return [array[index, 0] for index in range(array.shape[0])]
    return []


def _score_at(scores: Any, index: int) -> float:
    if hasattr(scores, "detach"):
        scores = _torch_to_numpy_f32(scores)
    array = np.asarray(scores).reshape(-1)
    return float(array[index]) if len(array) > index else 0.0


def _box_at(boxes: Any, index: int) -> list[float]:
    if hasattr(boxes, "detach"):
        boxes = _torch_to_numpy_f32(boxes)
    array = np.asarray(boxes)
    if array.ndim >= 2 and len(array) > index and array.shape[-1] >= 4:
        return [float(value) for value in array[index][:4]]
    return []


def save_mask(mask: np.ndarray, path: Path) -> None:
    from PIL import Image

    Image.fromarray(mask.astype(np.uint8)).convert("L").save(path)


def set_offline_env() -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"


def _sam3_cuda_bf16_autocast_allowed(device: str) -> bool:
    """True when CUDA bfloat16 is expected to work for torchvision + SAM3 forwards on this GPU."""
    import torch

    if device.lower().split(":")[0] != "cuda" or not torch.cuda.is_available():
        return False
    if hasattr(torch.cuda, "is_bf16_supported"):
        return bool(torch.cuda.is_bf16_supported())
    try:
        idx = int(device.split(":")[-1]) if ":" in device else torch.cuda.current_device()
    except (ValueError, RuntimeError):
        idx = torch.cuda.current_device()
    major, _ = torch.cuda.get_device_capability(idx)
    return major >= 8


def _sam3_exit_cuda_bf16_inference(ctx: Any) -> None:
    if ctx is None:
        return
    ctx.__exit__(None, None, None)


def _should_retry_sam3_image_without_bf16_autocast(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return ("unsupported" in msg and ("bfloat16" in msg or "bf16" in msg)) or "scalartype bfloat16" in msg.replace(
        " ", ""
    )


def _sam3_enter_official_cuda_bf16_inference(device: str, enabled: bool) -> Any:
    """Match ``examples/sam3_image_predictor_example.ipynb``: TF32 + persistent ``torch.autocast(bfloat16)`` on CUDA."""
    import torch

    if not enabled:
        return None
    if device.lower().split(":")[0] != "cuda" or not torch.cuda.is_available():
        return None
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    ctx = torch.autocast("cuda", dtype=torch.bfloat16)
    ctx.__enter__()
    return ctx


def resolve_checkpoint_for_backend(root: Path | None, explicit_checkpoint: str, sam3_backend: str) -> Path | None:
    backend = str(sam3_backend).strip().lower()
    if explicit_checkpoint:
        cand = Path(explicit_checkpoint).resolve()
        if not cand.exists():
            raise RuntimeError(f"SAM3 checkpoint path does not exist: {cand}")
        return cand
    if root is None:
        return None
    if not root.exists():
        raise RuntimeError(f"SAM3 local model root does not exist: {root}")

    if backend == "image":
        for name in ("sam3.pt", "SAM3.pt", "checkpoint.pt"):
            direct = root / name
            if direct.exists():
                return direct.resolve()
        for pattern in ("*.safetensors", "*.pt", "*.pth", "*.bin"):
            for path in sorted(root.rglob(pattern)):
                if "multiplex" in path.name.lower():
                    continue
                return path.resolve()
        return None

    if backend == "multiplex":
        for pattern in ("*.safetensors", "*.pt", "*.pth", "*.bin"):
            ranked = sorted(root.rglob(pattern))
            multiplex_first = [p for p in ranked if "multiplex" in p.name.lower()]
            if multiplex_first:
                return multiplex_first[0].resolve()
            if ranked:
                return ranked[0].resolve()
        return None

    return find_first(root, ["*.safetensors", "*.pt", "*.pth", "*.bin"])


def resolve_local_model_paths(
    model_root: str, config_path: str, checkpoint_path: str, *, sam3_backend: str = "auto"
) -> dict[str, str]:
    root = Path(model_root).resolve() if model_root else None
    if root and not root.exists():
        raise RuntimeError(f"SAM3 local model root does not exist: {root}")
    resolved_config = Path(config_path).resolve() if config_path else find_first(root, ["config.json", "*.yaml", "*.yml"])
    resolved_checkpoint = resolve_checkpoint_for_backend(root, checkpoint_path, sam3_backend)
    if config_path and resolved_config is not None and not resolved_config.exists():
        raise RuntimeError(f"SAM3 config path does not exist: {resolved_config}")
    if checkpoint_path and resolved_checkpoint is not None and not resolved_checkpoint.exists():
        raise RuntimeError(f"SAM3 checkpoint path does not exist: {resolved_checkpoint}")
    return {
        "model_root": str(root) if root else "",
        "config_path": str(resolved_config) if resolved_config else "",
        "checkpoint_path": str(resolved_checkpoint) if resolved_checkpoint else "",
    }


def find_first(root: Path | None, patterns: list[str]) -> Path | None:
    if not root:
        return None
    for pattern in patterns:
        direct = root / pattern
        if "*" not in pattern and direct.exists():
            return direct.resolve()
        matches = sorted(root.rglob(pattern))
        if matches:
            return matches[0].resolve()
    return None


def build_local_sam3_model(build_sam3_image_model: Any, resolved: dict[str, str], device: str) -> Any:
    sig = inspect.signature(build_sam3_image_model)
    params = sig.parameters
    kwargs: dict[str, Any] = {}
    config_path = resolved["config_path"]
    checkpoint_path = resolved["checkpoint_path"]
    model_root = resolved["model_root"]
    if "device" in params:
        kwargs["device"] = device
    if "config_path" in params and "checkpoint_path" in params:
        if not config_path or not checkpoint_path:
            raise RuntimeError("SAM3 local loading requires config_path and checkpoint_path, but local files were not found.")
        kwargs.update({"config_path": config_path, "checkpoint_path": checkpoint_path})
    elif "config_file" in params and "checkpoint_file" in params:
        if not config_path or not checkpoint_path:
            raise RuntimeError("SAM3 local loading requires config_file and checkpoint_file, but local files were not found.")
        kwargs.update({"config_file": config_path, "checkpoint_file": checkpoint_path})
    elif "model_path" in params:
        if not model_root:
            raise RuntimeError("SAM3 local loading requires model_path, but sam3_model_root was not provided.")
        kwargs["model_path"] = model_root
    elif "model_root" in params:
        if not model_root:
            raise RuntimeError("SAM3 local loading requires model_root, but sam3_model_root was not provided.")
        kwargs["model_root"] = model_root
    elif "model_id" in params:
        if not model_root:
            raise RuntimeError("SAM3 local loading requires model_id, but sam3_model_root was not provided.")
        kwargs["model_id"] = model_root
    elif "checkpoint_path" in params:
        if not checkpoint_path:
            raise RuntimeError("SAM3 local loading requires checkpoint_path, but no local checkpoint was found.")
        kwargs["checkpoint_path"] = checkpoint_path
        if "load_from_HF" in params:
            kwargs["load_from_HF"] = False
    else:
        raise RuntimeError(
            "SAM3 local loading failed: build_sam3_image_model signature does not expose local model path arguments. "
            "Refusing to call build_sam3_image_model() without local paths because it would access HuggingFace facebook/sam3."
        )
    return build_sam3_image_model(**kwargs)


def add_sam3_repo_to_path(sam3_repo_dir: str) -> None:
    if not sam3_repo_dir:
        return
    repo_dir = str(Path(sam3_repo_dir).resolve())
    if repo_dir not in sys.path:
        sys.path.insert(0, repo_dir)


def sam3_import_diagnostics(sam3_repo_dir: str) -> str:
    return "\n".join(
        [
            f"python executable: {sys.executable}",
            f"sam3_repo_dir: {sam3_repo_dir or '<not provided>'}",
            f"sys.path[:10]: {sys.path[:10]}",
            f"find_spec('sam3'): {importlib.util.find_spec('sam3')}",
            f"find_spec('sam3.model_builder'): {_safe_find_spec('sam3.model_builder')}",
            f"find_spec('sam3.model.sam3_image_processor'): {_safe_find_spec('sam3.model.sam3_image_processor')}",
        ]
    )


def _safe_find_spec(name: str) -> Any:
    try:
        return importlib.util.find_spec(name)
    except Exception as exc:
        return f"<error: {exc}>"


if __name__ == "__main__":
    main()
