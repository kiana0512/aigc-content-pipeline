from __future__ import annotations

from src.generation.comfyui_adapter import WorkflowPatchParams, patch_workflow
from src.generation.workflow_runner import build_run_manifest


def test_prompt_pack_overrides_workflow_default() -> None:
    workflow = {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "workflow default A"}},
        "2": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512}},
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 1,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
            },
        },
    }
    mapping = {
        "required": {
            "positive_prompt": {"node_id": "1", "input_key": "text"},
            "negative_prompt": {"node_id": "", "input_key": ""},
            "latent_size": {"node_id": "2", "width_key": "width", "height_key": "height"},
            "sampler": {
                "node_id": "3",
                "seed_key": "seed",
                "steps_key": "steps",
                "cfg_key": "cfg",
                "sampler_key": "sampler_name",
                "scheduler_key": "scheduler",
            },
        }
    }
    config = {
        "project": {"name": "test"},
        "task": {"type": "baseline", "asset_type": "icon", "scenario": "smoke"},
        "model": {"family": "split", "base_model_name": "mock"},
        "runtime": {"seed": 1},
        "generation": {
            "prompt": "config prompt C",
            "negative_prompt": "",
            "width": 512,
            "height": 512,
            "batch_size": 1,
            "num_inference_steps": 20,
            "guidance_scale": 7.0,
            "sampler": "euler",
            "scheduler": "normal",
            "filename_prefix": "test",
        },
    }
    prompt_rows = [
        {
            "id": "1",
            "prompt_row_index": 1,
            "prompt_row_id": "1",
            "subject": "hero",
            "style": "",
            "attributes": "",
            "positive_prompt": "prompt pack B",
            "positive_prompt_source": "prompt_pack.positive_prompt_text",
            "negative_prompt": "",
            "negative_prompt_explicit": False,
            "negative_prompt_source": "",
            "filename_prefix": "item_001",
            "filename_prefix_source": "prompt_pack.filename_prefix",
        }
    ]
    manifest = build_run_manifest(
        config,
        prompt_rows,
        workflow_defaults={"positive_prompt": "workflow default A"},
    )
    item = manifest["items"][0]
    params = WorkflowPatchParams(
        positive_prompt=item["positive_prompt"],
        negative_prompt=item["negative_prompt"],
        seed=int(manifest["seed"]),
        width=int(manifest["width"]),
        height=int(manifest["height"]),
        steps=int(manifest["num_inference_steps"]),
        cfg=float(manifest["guidance_scale"]),
        sampler=str(manifest["sampler"]),
        scheduler=str(manifest["scheduler"]),
        filename_prefix=str(item["filename_prefix"]),
    )

    patched = patch_workflow(workflow, mapping, params)
    assert item["positive_prompt_source"] == "prompt_pack.positive_prompt_text"
    assert patched["1"]["inputs"]["text"] == "prompt pack B"
    assert patched["1"]["inputs"]["text"] != "workflow default A"

