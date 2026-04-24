from __future__ import annotations

from pathlib import Path

from src.generation.workflow_runner import build_run_manifest, load_prompt_pack_csv


def _write_csv(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _base_config() -> dict:
    return {
        "project": {"name": "test"},
        "task": {"type": "baseline", "asset_type": "icon", "scenario": "smoke"},
        "model": {"family": "split", "base_model_name": "mock"},
        "runtime": {"seed": 1},
        "generation": {
            "prompt": "config prompt",
            "negative_prompt": "config neg",
            "width": 512,
            "height": 512,
            "batch_size": 1,
            "num_inference_steps": 20,
            "guidance_scale": 5.0,
            "sampler": "euler",
            "scheduler": "normal",
            "denoise": 1.0,
            "filename_prefix": "from_config",
        },
    }


def test_prompt_aliases_and_filename_alias_are_normalized(tmp_path: Path) -> None:
    csv_path = _write_csv(
        tmp_path / "prompt_pack.csv",
        "\n".join(
            [
                "id,subject,style,attributes,positive_prompt_text,negative_prompt_text,output_prefix",
                '1,hero,stylized,armor,"csv positive","csv negative","csv/prefix"',
            ]
        )
        + "\n",
    )
    rows = load_prompt_pack_csv(csv_path)
    manifest = build_run_manifest(_base_config(), rows)
    item = manifest["items"][0]

    assert item["positive_prompt"] == "csv positive"
    assert item["positive_prompt_source"] == "prompt_pack.positive_prompt_text"
    assert item["negative_prompt"] == "csv negative"
    assert item["negative_prompt_source"] == "prompt_pack.negative_prompt_text"
    assert item["filename_prefix"] == "csv/prefix"
    assert item["filename_prefix_source"] == "prompt_pack.output_prefix"


def test_subject_style_attributes_only_used_when_no_explicit_positive_prompt(
    tmp_path: Path,
) -> None:
    csv_path = _write_csv(
        tmp_path / "prompt_pack.csv",
        "\n".join(
            [
                "id,subject,style,attributes,negative_prompt",
                "1,female ranger,painterly,forest ruins,bad anatomy",
            ]
        )
        + "\n",
    )
    rows = load_prompt_pack_csv(csv_path)
    manifest = build_run_manifest(_base_config(), rows)
    item = manifest["items"][0]

    assert item["positive_prompt"] == "female ranger, painterly, forest ruins"
    assert item["positive_prompt_source"] == "prompt_pack.composed(subject,style,attributes)"
    assert item["negative_prompt"] == "bad anatomy"
    assert item["negative_prompt_source"] == "prompt_pack.negative_prompt"

