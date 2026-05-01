from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
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

    def get_object_info(self) -> dict[str, Any]:
        response = requests.get(f"{self.base_url}/object_info", timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    def get_history(self, prompt_id: str) -> dict[str, Any]:
        response = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    def view_image_exists(
        self,
        filename: str,
        subfolder: str = "",
        *,
        image_type: str = "input",
    ) -> bool:
        """Return True if ComfyUI can serve /view for this input/output image."""
        response = requests.get(
            f"{self.base_url}/view",
            params={"filename": filename, "subfolder": subfolder, "type": image_type},
            timeout=self.timeout,
        )
        return response.ok

    def upload_image(
        self,
        image_path: str | Path,
        *,
        subfolder: str,
        image_type: str = "input",
        overwrite: bool = True,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """
        POST /upload/image (ComfyUI standard).
        Returns JSON with keys like name, subfolder, type.
        """
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"upload_image: file not found: {path}")
        upload_name = filename or path.name
        with path.open("rb") as fh:
            response = requests.post(
                f"{self.base_url}/upload/image",
                files={"image": (upload_name, fh)},
                data={
                    "type": image_type,
                    "subfolder": subfolder.replace("\\", "/"),
                    "overwrite": "true" if overwrite else "false",
                },
                timeout=max(self.timeout, 120),
            )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def load_image_value_from_upload_result(result: dict[str, Any]) -> str:
        """Build LoadImage `image` field from upload JSON."""
        name = str(result.get("name") or result.get("filename") or "").strip()
        subfolder = str(result.get("subfolder") or "").strip().replace("\\", "/")
        if subfolder:
            return f"{subfolder}/{name}".strip("/").replace("//", "/")
        return name

    def submit_prompt(
        self,
        workflow_json: dict[str, Any],
        debug_dir: str | Path | None = None,
        *,
        file_prefix: str = "",
    ) -> str:
        payload = {"prompt": workflow_json, "client_id": self.client_id}
        url = f"{self.base_url}/prompt"
        dbg = Path(debug_dir) if debug_dir else None
        pf = file_prefix.strip()
        stem = f"{pf}_" if pf else ""

        try:
            if dbg is not None:
                dbg.mkdir(parents=True, exist_ok=True)
                ppath = dbg / f"{stem}comfy_submit_payload.json"
                ppath.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            response = requests.post(url, json=payload, timeout=self.timeout)

            if response.ok:
                data = response.json()
                pid = data.get("prompt_id") if isinstance(data, dict) else None
                if not pid:
                    raise RuntimeError(f"ComfyUI /prompt succeeded but missing prompt_id: {data}")
                return str(pid)

            err_txt = response.text.strip() or "(empty body)"
            err_json_text = ""
            pj: dict[str, Any] | Any | None = None
            try:
                pj = response.json()
                err_json_text = json.dumps(pj, ensure_ascii=False, indent=2)
            except Exception:
                pj = None

            print("\n=== ComfyUI /prompt submit failed ===")
            print(f"URL: {url}")
            print(f"Status: {response.status_code}")
            print("Response body (text):")
            print(err_txt[:8000])
            if err_json_text:
                print("Response JSON (pretty):")
                print(err_json_text[:12000])

            if dbg:
                error_path = dbg / f"{stem}comfy_submit_error.json"
                error_bucket: dict[str, Any] = {
                    "url": url,
                    "status_code": response.status_code,
                    "text": response.text,
                }
                if isinstance(pj, dict):
                    error_bucket["parsed"] = pj
                elif pj is not None:
                    error_bucket["parsed_raw"] = pj
                error_path.write_text(json.dumps(error_bucket, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            core = err_json_text or err_txt
            suffix_lines: list[str] = []
            if dbg:
                suffix_lines.append(f"Payload saved to: {dbg / f'{stem}comfy_submit_payload.json'}")
                suffix_lines.append(f"Error saved to: {dbg / f'{stem}comfy_submit_error.json'}")
            suffix = ("\n" + "\n".join(suffix_lines)) if suffix_lines else ""

            raise RuntimeError(f"ComfyUI /prompt failed HTTP {response.status_code}: {core[:2000]}{suffix}")

        except requests.RequestException as exc:
            if dbg:
                dbg.mkdir(parents=True, exist_ok=True)
                (dbg / f"{stem}comfy_submit_payload.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                (dbg / f"{stem}comfy_submit_error.json").write_text(
                    json.dumps({"transport_error": repr(exc)}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            raise

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
        """Legacy shim: uploads to flat input folder (overwrite). Prefer upload_image(..., subfolder=...)."""
        with image_path.open("rb") as f:
            response = requests.post(
                f"{self.base_url}/upload/image",
                files={"image": (image_path.name, f)},
                data={"overwrite": "true"},
                timeout=self.timeout,
            )
        response.raise_for_status()
        return response.json()
