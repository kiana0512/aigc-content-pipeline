from pathlib import Path

from aigc2d.comfy_client import ComfyClient


class FakeResponse:
    def __init__(self, payload=None, content: bytes = b"image") -> None:
        self.payload = payload or {}
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def test_comfy_client_submit_and_poll(monkeypatch):
    def fake_post(url, json=None, timeout=0):
        assert url.endswith("/prompt")
        return FakeResponse({"prompt_id": "abc"})

    def fake_get(url, timeout=0, params=None):
        if url.endswith("/history/abc"):
            return FakeResponse({"abc": {"outputs": {"9": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}})
        return FakeResponse({"ok": True})

    monkeypatch.setattr("aigc2d.comfy_client.requests.post", fake_post)
    monkeypatch.setattr("aigc2d.comfy_client.requests.get", fake_get)
    client = ComfyClient("http://127.0.0.1:8188")
    prompt_id = client.submit_prompt({"1": {"inputs": {}}})
    history = client.poll_history(prompt_id, timeout_sec=1, poll_interval=0)
    images = client.fetch_output_images(history)
    assert prompt_id == "abc"
    assert images[0]["filename"] == "out.png"


def test_comfy_client_download(monkeypatch, tmp_path):
    def fake_get(url, timeout=0, params=None):
        return FakeResponse(content=b"png")

    monkeypatch.setattr("aigc2d.comfy_client.requests.get", fake_get)
    path = ComfyClient().download_image("a.png", "", "output", tmp_path / "a.png")
    assert Path(path).read_bytes() == b"png"
