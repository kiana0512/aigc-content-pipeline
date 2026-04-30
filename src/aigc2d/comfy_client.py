from __future__ import annotations

from pathlib import Path
import time
import uuid
from typing import Any

import requests


class ComfyClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188", timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client_id = str(uuid.uuid4())

    def get_system_stats(self) -> dict[str, Any]:
        response = requests.get(f"{self.base_url}/system_stats", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def submit_prompt(self, workflow_json: dict[str, Any]) -> str:
        payload = {
            "prompt": workflow_json,
            "client_id": self.client_id,
        }
        response = requests.post(f"{self.base_url}/prompt", json=payload, timeout=self.timeout)
        response.raise_for_status()
        return str(response.json()["prompt_id"])

    def submit_workflow(self, workflow: dict[str, Any], run_id: str) -> dict[str, Any]:
        prompt_id = self.submit_prompt(workflow)
        return {"prompt_id": prompt_id, "run_id": run_id}

    def poll_history(
        self,
        prompt_id: str,
        timeout_sec: int = 600,
        poll_interval: float = 2.0,
    ) -> dict[str, Any]:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            response = requests.get(
                f"{self.base_url}/history/{prompt_id}",
                timeout=self.timeout,
            )
            response.raise_for_status()
            history = response.json()
            if prompt_id in history:
                return history[prompt_id]
            time.sleep(poll_interval)
        raise TimeoutError(f"ComfyUI job timed out: {prompt_id}")

    def poll_job_status(
        self,
        prompt_id: str,
        poll_interval: float = 2.0,
        timeout_seconds: int = 600,
    ) -> dict[str, Any]:
        return self.poll_history(prompt_id, timeout_sec=timeout_seconds, poll_interval=poll_interval)

    def fetch_output_images(self, history_payload: dict[str, Any]) -> list[dict[str, Any]]:
        images: list[dict[str, Any]] = []
        entry = history_payload
        if "outputs" not in entry and len(history_payload) == 1:
            entry = next(iter(history_payload.values()))
        for node_id, node_output in entry.get("outputs", {}).items():
            for image in node_output.get("images", []):
                item = dict(image)
                item["node_id"] = node_id
                images.append(item)
        return images

    def collect_output_paths(self, history_entry: dict[str, Any]) -> list[str]:
        outputs: list[str] = []
        for image in self.fetch_output_images(history_entry):
            filename = image.get("filename")
            if not filename:
                continue
            subfolder = image.get("subfolder") or ""
            outputs.append(f"{subfolder}/{filename}".lstrip("/"))
        return outputs

    def download_image(
        self,
        filename: str,
        subfolder: str,
        type_: str,
        save_path: Path,
    ) -> Path:
        response = requests.get(
            f"{self.base_url}/view",
            params={"filename": filename, "subfolder": subfolder, "type": type_},
            timeout=self.timeout,
        )
        response.raise_for_status()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(response.content)
        return save_path

    def upload_input_image(self, image_path: Path) -> dict[str, Any]:
        with image_path.open("rb") as f:
            response = requests.post(
                f"{self.base_url}/upload/image",
                files={"image": (image_path.name, f)},
                data={"overwrite": "true"},
                timeout=self.timeout,
            )
        response.raise_for_status()
        return response.json()
