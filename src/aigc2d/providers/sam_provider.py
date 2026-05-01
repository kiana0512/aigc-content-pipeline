from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from ..config import PROJECT_ROOT
from .base import ProviderError


class ExternalSam3Provider:
    provider_name = "SAM3.1-external-conda"

    def __init__(
        self,
        conda_env: str = "sam3",
        python_exe: str | None = None,
        cli_script: str | Path = "scripts/sam3_segment_cli.py",
        sam3_repo_dir: str | Path = "",
        sam3_model_root: str | Path = "",
        sam3_config_path: str | Path = "",
        sam3_checkpoint_path: str | Path = "",
        offline: bool = True,
        device: str = "cuda",
        min_mask_area_ratio: float = 0.03,
        max_mask_area_ratio: float = 0.90,
        output_prob_thresh: float = 0.2,
        sam31_image_mode: bool = True,
        sam3_backend: str = "auto",
        timeout_sec: int = 600,
        strict_real: bool = True,
        prompts: list[str] | None = None,
    ) -> None:
        self.conda_env = conda_env
        self.python_exe = python_exe
        self.cli_script = Path(cli_script)
        self.sam3_repo_dir = str(sam3_repo_dir or "")
        self.sam3_model_root = str(sam3_model_root or "")
        self.sam3_config_path = str(sam3_config_path or "")
        self.sam3_checkpoint_path = str(sam3_checkpoint_path or "")
        self.offline = offline
        self.device = device
        self.min_mask_area_ratio = min_mask_area_ratio
        self.max_mask_area_ratio = max_mask_area_ratio
        self.output_prob_thresh = output_prob_thresh
        self.sam31_image_mode = sam31_image_mode
        self.sam3_backend = str(sam3_backend).strip().lower() or "auto"
        self.timeout_sec = timeout_sec
        self.strict_real = strict_real
        self.prompts = prompts or ["person", "anime character", "main subject", "girl", "character"]

    def segment(self, image_path: str, out_dir: str | Path, prompts: list[str] | None = None) -> dict[str, Any]:
        output_dir = Path(out_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        command = self._command(image_path, output_dir, prompts or self.prompts)
        print(f"  external command: {' '.join(str(part) for part in command)}")
        try:
            completed = subprocess.run(
                command,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                check=False,
                env=self._env(),
            )
        except FileNotFoundError as exc:
            raise self._error(
                image_path,
                command,
                "",
                str(exc),
                self._conda_missing_message(),
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise self._error(
                image_path,
                command,
                exc.stdout or "",
                exc.stderr or "",
                f"SAM3 external provider timed out after {self.timeout_sec}s.",
            ) from exc
        if completed.returncode != 0:
            stderr = completed.stderr or ""
            if any(token in stderr for token in ["EnvironmentNameNotFound", "EnvironmentLocationNotFound", "Could not find conda environment"]):
                message = self._conda_missing_message()
            elif "No module named 'sam3'" in stderr or "No module named sam3" in stderr or "not importable" in stderr:
                message = self._sam3_missing_message()
            else:
                message = "SAM3 external CLI returned non-zero exit code."
            raise self._error(image_path, command, completed.stdout, completed.stderr, message)
        segmentation_path = output_dir / "segmentation.json"
        mask_path = output_dir / "subject_mask.png"
        if not segmentation_path.exists() or not mask_path.exists():
            raise self._error(image_path, command, completed.stdout, completed.stderr, "SAM3 external CLI did not produce segmentation.json and subject_mask.png.")
        data = json.loads(segmentation_path.read_text(encoding="utf-8"))
        if data.get("mock") is not False:
            raise self._error(image_path, command, completed.stdout, completed.stderr, "SAM3 external CLI returned a mock payload in strict real mode.")
        masks = data.get("masks", {})
        subject = masks.get("subject", {})
        if not subject.get("mask_path") or not Path(subject["mask_path"]).exists():
            raise self._error(image_path, command, completed.stdout, completed.stderr, "SAM3 external CLI subject mask path is missing or invalid.")
        data.setdefault("results", {"masks": masks})
        return data

    def _command(self, image_path: str, out_dir: Path, prompts: list[str]) -> list[str]:
        script = self.cli_script if self.cli_script.is_absolute() else PROJECT_ROOT / self.cli_script
        if self.python_exe:
            command = [self.python_exe, str(script)]
        else:
            command = ["conda", "run", "-n", self.conda_env, "python", str(script)]
        command.extend(
            [
                "--image",
                str(image_path),
                "--out-dir",
                str(out_dir),
                "--device",
                self.device,
                "--min-mask-area-ratio",
                str(self.min_mask_area_ratio),
                "--max-mask-area-ratio",
                str(self.max_mask_area_ratio),
                "--output-prob-thresh",
                str(self.output_prob_thresh),
                "--conda-env",
                self.conda_env,
            ]
        )
        if self.sam3_repo_dir:
            command.extend(["--sam3-repo-dir", self.sam3_repo_dir])
        if self.sam3_model_root:
            command.extend(["--sam3-model-root", self.sam3_model_root])
        if self.sam3_config_path:
            command.extend(["--sam3-config-path", self.sam3_config_path])
        if self.sam3_checkpoint_path:
            command.extend(["--sam3-checkpoint-path", self.sam3_checkpoint_path])
        command.extend(["--sam3-backend", self.sam3_backend])
        # Multiplex-only; image backend ignores these (avoids implying SAM3.1 in logs).
        if self.sam3_backend != "image":
            if self.sam31_image_mode:
                command.append("--sam31-image-mode")
            else:
                command.append("--no-sam31-image-mode")
        if self.offline:
            command.append("--offline")
        command.extend(["--prompts", *prompts])
        return command

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.sam3_repo_dir:
            current = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = self.sam3_repo_dir if not current else f"{self.sam3_repo_dir}{os.pathsep}{current}"
        if self.offline:
            env["HF_HUB_OFFLINE"] = "1"
            env["TRANSFORMERS_OFFLINE"] = "1"
            env["HF_DATASETS_OFFLINE"] = "1"
        return env

    def _error(self, image_path: str, command: list[str], stdout: str, stderr: str, message: str) -> ProviderError:
        return ProviderError(
            self.provider_name,
            "\n".join(
                [
                    message,
                    f"conda env: {self.conda_env}",
                    f"sam3 repo dir: {self.sam3_repo_dir or '<not set>'}",
                    f"sam3 model root: {self.sam3_model_root or '<not set>'}",
                    f"image path: {image_path}",
                    f"cli command: {' '.join(str(part) for part in command)}",
                    f"stdout:\n{stdout or '<empty>'}",
                    f"stderr:\n{stderr or '<empty>'}",
                ]
            ),
        )

    def _conda_missing_message(self) -> str:
        return (
            f"SAM3 external provider failed: conda env '{self.conda_env}' is not available.\n"
            "Please create it first:\n"
            f"  conda create -n {self.conda_env} python=3.12\n"
            f"  conda activate {self.conda_env}\n"
            "  pip install torch torchvision --index-url <your CUDA torch index>\n"
            "  cd weights/segmentation/sam3\n"
            "  pip install -e ."
        )

    def _sam3_missing_message(self) -> str:
        return (
            f"SAM3 external provider failed: Python package 'sam3' is not importable inside conda env '{self.conda_env}'.\n"
            "Please install local SAM3 repo in that env:\n"
            f"  conda activate {self.conda_env}\n"
            "  cd weights/segmentation/sam3\n"
            "  pip install -e ."
        )

    def _select_boxes(self, boxes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        if not boxes:
            raise ProviderError(self.provider_name, "no detection boxes provided")
        sorted_boxes = sorted(boxes, key=lambda item: float(item.get("score", 0.0)), reverse=True)
        selected = {"subject": sorted_boxes[0]}
        for item in sorted_boxes:
            label = str(item.get("label", "")).lower()
            if "face" in label or "head" in label:
                selected.setdefault("face", item)
            if any(token in label for token in ["mecha", "armor", "weapon", "mechanical"]):
                selected.setdefault("mecha", item)
        return selected
