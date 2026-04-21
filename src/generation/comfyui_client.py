from __future__ import annotations

from typing import Any

import requests


class ComfyUIClient:
    """Minimal ComfyUI HTTP client used by submit mode."""

    def __init__(self, base_url: str, timeout_seconds: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def submit_prompt(
        self, prompt_graph: dict[str, Any], client_id: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"prompt": prompt_graph}
        if client_id:
            payload["client_id"] = client_id

        response = requests.post(
            f"{self.base_url}/prompt",
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected ComfyUI response format for /prompt")
        return data

    def get_queue(self) -> dict[str, Any]:
        response = requests.get(
            f"{self.base_url}/queue",
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected ComfyUI response format for /queue")
        return data
