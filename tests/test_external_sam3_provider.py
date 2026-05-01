import json
import subprocess
import sys

import pytest
from PIL import Image

from aigc2d.providers import ProviderError
from aigc2d.providers.sam_provider import ExternalSam3Provider


def test_external_sam3_provider_builds_conda_command(tmp_path, monkeypatch):
    image = tmp_path / "image.png"
    Image.new("RGB", (32, 32), "white").save(image)
    out_dir = tmp_path / "out"

    def fake_run(command, **kwargs):
        assert command[:5] == ["conda", "run", "-n", "sam3", "python"]
        assert command[5].replace("\\", "/").endswith("scripts/sam3_segment_cli.py")
        assert "--sam3-backend" in command
        idx = command.index("--sam3-backend")
        assert command[idx + 1] == "auto"
        assert "--sam31-image-mode" in command
        assert "--prompts" in command
        out_dir.mkdir(exist_ok=True)
        mask = out_dir / "subject_mask.png"
        Image.new("L", (32, 32), 255).save(mask)
        (out_dir / "segmentation.json").write_text(
            json.dumps(
                {
                    "mock": False,
                    "provider_name": "SAM3.1-external-conda",
                    "masks": {"subject": {"mask_path": str(mask), "area_ratio": 0.5}},
                    "warnings": [],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("aigc2d.providers.sam_provider.subprocess.run", fake_run)
    result = ExternalSam3Provider(conda_env="sam3").segment(str(image), out_dir, ["person"])
    assert result["provider_name"] == "SAM3.1-external-conda"


def test_external_sam3_provider_uses_python_exe_and_repo_dir(tmp_path, monkeypatch):
    image = tmp_path / "image.png"
    repo_dir = tmp_path / "sam3"
    Image.new("RGB", (32, 32), "white").save(image)
    repo_dir.mkdir()
    out_dir = tmp_path / "out"
    python_exe = "D:/Program Files/anaconda3/envs/sam3/python.exe"

    def fake_run(command, **kwargs):
        assert command[0] == python_exe
        assert command[1].replace("\\", "/").endswith("scripts/sam3_segment_cli.py")
        assert "--sam3-backend" in command
        idx = command.index("--sam3-backend")
        assert command[idx + 1] == "auto"
        assert "--sam31-image-mode" in command
        assert "--sam3-repo-dir" in command
        assert "--sam3-model-root" in command
        assert "--offline" in command
        assert str(repo_dir) in command
        assert str(repo_dir) in kwargs["env"]["PYTHONPATH"]
        assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
        out_dir.mkdir(exist_ok=True)
        mask = out_dir / "subject_mask.png"
        Image.new("L", (32, 32), 255).save(mask)
        (out_dir / "segmentation.json").write_text(
            json.dumps(
                {
                    "mock": False,
                    "provider_name": "SAM3.1-external-conda",
                    "masks": {"subject": {"mask_path": str(mask), "area_ratio": 0.5}},
                    "warnings": [],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("aigc2d.providers.sam_provider.subprocess.run", fake_run)
    result = ExternalSam3Provider(
        python_exe=python_exe,
        sam3_repo_dir=str(repo_dir),
        sam3_model_root=str(tmp_path / "weights" / "sam3.1"),
        offline=True,
    ).segment(str(image), out_dir, ["person"])
    assert result["provider_name"] == "SAM3.1-external-conda"


def test_external_sam3_provider_failure_includes_stdout_stderr(tmp_path, monkeypatch):
    image = tmp_path / "image.png"
    Image.new("RGB", (32, 32), "white").save(image)

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 2, stdout="stdout text", stderr="stderr text")

    monkeypatch.setattr("aigc2d.providers.sam_provider.subprocess.run", fake_run)
    with pytest.raises(ProviderError) as exc:
        ExternalSam3Provider(conda_env="sam3").segment(str(image), tmp_path / "out", ["person"])
    message = str(exc.value)
    assert "stdout text" in message
    assert "stderr text" in message
    assert "conda env: sam3" in message


def test_external_sam3_image_backend_omits_sam31_image_mode(tmp_path, monkeypatch):
    image = tmp_path / "image.png"
    Image.new("RGB", (32, 32), "white").save(image)
    out_dir = tmp_path / "out"

    def fake_run(command, **kwargs):
        assert "--sam3-backend" in command
        i = command.index("--sam3-backend")
        assert command[i + 1] == "image"
        assert "--sam31-image-mode" not in command
        assert "--no-sam31-image-mode" not in command
        out_dir.mkdir(exist_ok=True)
        mask = out_dir / "subject_mask.png"
        Image.new("L", (32, 32), 255).save(mask)
        (out_dir / "segmentation.json").write_text(
            json.dumps(
                {
                    "mock": False,
                    "provider_name": "SAM3.1-external-conda",
                    "masks": {"subject": {"mask_path": str(mask), "area_ratio": 0.5}},
                    "warnings": [],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("aigc2d.providers.sam_provider.subprocess.run", fake_run)
    ExternalSam3Provider(sam3_backend="image").segment(str(image), out_dir, ["person"])


def test_external_sam3_provider_does_not_reference_sam2():
    import inspect
    import aigc2d.providers.sam_provider as sam_provider

    source = inspect.getsource(sam_provider)
    assert "sam2" not in source


def test_check_sam3_env_failure_has_install_hint(monkeypatch, capsys):
    from scripts import check_sam3_env

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="missing env")

    monkeypatch.setattr("scripts.check_sam3_env.subprocess.run", fake_run)
    monkeypatch.setattr(sys, "argv", ["check_sam3_env.py", "--conda-env", "sam3", "--sam3-repo-dir", "F:/repo/sam3"])
    with pytest.raises(SystemExit):
        check_sam3_env.main()
    output = capsys.readouterr().out
    assert "conda create -n sam3" in output
    assert "cd F:/repo/sam3" in output
