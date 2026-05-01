from __future__ import annotations

import gc
import json
import time
from pathlib import Path
from typing import Any

from PIL import Image

from .base import ProviderContext, ProviderError, provider_payload, require_path


def _balanced_json_fragment(s: str, start: int) -> str | None:
    if start < 0 or start >= len(s) or s[start] != "{":
        return None
    depth = 0
    i = start
    in_string = False
    escape = False
    quote = ""
    while i < len(s):
        ch = s[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
        else:
            if ch == '"':
                in_string = True
                quote = '"'
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
        i += 1
    return None


def _strip_markdown_fence(blob: str) -> str:
    t = blob.strip()
    if "```" not in t:
        return t
    rebuilt: list[str] = []
    for part in t.split("```"):
        p = part.strip()
        if p.lower().startswith("json"):
            p = p[4:].lstrip("\r\n ").strip()
        rebuilt.append(p)
    return "\n".join(rebuilt).strip()


def _json_candidate_slices(text: str) -> list[str]:
    body = _strip_markdown_fence(text)
    cand: list[str] = []
    pos = 0
    while True:
        idx = body.find("{", pos)
        if idx < 0:
            break
        frag = _balanced_json_fragment(body, idx)
        if frag:
            cand.append(frag)
        pos = idx + 1
    if not cand:
        lo, hi = body.find("{"), body.rfind("}")
        if 0 <= lo < hi:
            cand.append(body[lo : hi + 1])
    return cand


class LocalVLMProvider:
    def __init__(
        self,
        provider_name: str = "Qwen2.5-VL-7B-Instruct",
        model_root: str | Path = "weights/vlm/Qwen2.5-VL-7B-Instruct",
        fallback_provider: str = "Florence-2-large-PromptGen-v2.0",
        fallback_model_root: str | Path = "weights/vlm/Florence-2-large-PromptGen-v2.0",
        allow_fallback: bool = False,
        max_new_tokens: int = 512,
        min_pixels: int | None = None,
        max_pixels: int | None = None,
        attn_implementation: str = "",
        context: ProviderContext | None = None,
    ) -> None:
        self.context = context or ProviderContext()
        self.provider_name = provider_name
        self.model_root = Path(model_root)
        self.fallback_provider = fallback_provider
        self.fallback_model_root = Path(fallback_model_root)
        self.allow_fallback = allow_fallback
        self.max_new_tokens = max_new_tokens
        self.min_pixels = min_pixels
        self.max_pixels = max_pixels
        ai = str(attn_implementation or "").strip().lower()
        self.attn_implementation = "" if ai in {"", "none", "off"} else ai
        self._model: Any = None
        self._processor: Any = None
        self._torch: Any = None

    def describe(
        self,
        image_path: str,
        role: str = "raw",
        *,
        raw_reply_path: Path | None = None,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        model_root = self._resolve_model_root()
        self._ensure_loaded(model_root)
        caption: dict[str, Any] | None = None
        last_raw = ""
        base_budget = max(64, int(self.max_new_tokens))
        token_budgets = [base_budget]
        expanded = min(2048, max(768, base_budget * 2))
        if expanded > base_budget:
            token_budgets.append(expanded)
        try:
            for mt in token_budgets:
                for strict in (False, True):
                    last_raw = self._generate(
                        image_path,
                        role,
                        strict_json_instruction=strict,
                        max_new_tokens=mt,
                    )
                    caption = self._coerce_structured_caption(last_raw, role)
                    if caption is not None:
                        warns = caption.setdefault("warnings", [])
                        if isinstance(warns, list):
                            if strict:
                                warns.append("vlm_reply_coerced_via_strict_json_instructions")
                            if mt != base_budget:
                                warns.append(f"vlm_used_expanded_max_new_tokens={mt}")
                        break
                if caption is not None:
                    break
        finally:
            if raw_reply_path is not None:
                try:
                    raw_reply_path.write_text(last_raw or "", encoding="utf-8")
                except OSError:
                    pass
        if caption is None:
            snippet = last_raw.strip().replace("\r", " ").replace("\n", " ")
            snippet = snippet[:1400] + ("…" if len(snippet) > 1400 else "")
            raise ProviderError(
                self.provider_name,
                f"VLM 输出无法解析为可用 JSON（已自动重试严约束提示 + 扩大 max_new_tokens）。"
                f"完整原文已写入 raw_reply_path（若调用方传入）。终端仅预览 1400 字。截取: {snippet}",
            )
        return provider_payload(
            mock=False,
            provider_name=self.provider_name,
            model_path=model_root,
            device=self.context.device,
            start=start,
            results=caption,
            **caption,
        )

    def _resolve_model_root(self) -> Path:
        if self.model_root.exists():
            return self.model_root
        if self.allow_fallback and not self.context.strict_real and self.fallback_model_root.exists():
            self.provider_name = self.fallback_provider
            return self.fallback_model_root
        raise ProviderError(self.provider_name, f"model_root not found: {self.model_root}")

    def _ensure_loaded(self, model_root: Path) -> None:
        if self._model is not None:
            return
        require_path(self.provider_name, model_root)
        try:
            import torch
            import transformers as trf
            from transformers import AutoModelForCausalLM, AutoProcessor
        except Exception as exc:
            raise ProviderError(
                self.provider_name,
                "missing dependency torch/transformers "
                f"({exc!s}). Upgrade with: pip install -U torch transformers ; "
                "Qwen2.5-VL needs a recent transformers (e.g. >=4.51).",
            ) from exc
        try:
            proc_init: dict[str, Any] = {"trust_remote_code": True, "local_files_only": True}
            if self.min_pixels is not None:
                proc_init["min_pixels"] = self.min_pixels
            if self.max_pixels is not None:
                proc_init["max_pixels"] = self.max_pixels
            self._processor = AutoProcessor.from_pretrained(str(model_root), **proc_init)
            dt = torch.float16 if self.context.device == "cuda" else torch.float32
            load_common: dict[str, Any] = {"trust_remote_code": True, "local_files_only": True}

            def load_pretrained(cls_obj: Any) -> Any:
                option_lists: list[dict[str, Any]] = []
                if self.attn_implementation and self.context.device == "cuda":
                    option_lists.append({**load_common, "attn_implementation": self.attn_implementation})
                option_lists.append(dict(load_common))
                last_exc: BaseException | None = None
                for extra in option_lists:
                    for dtype_kw in ("dtype", "torch_dtype"):
                        kw = dict(extra)
                        kw[dtype_kw] = dt
                        try:
                            return cls_obj.from_pretrained(str(model_root), **kw)
                        except Exception as err:
                            last_exc = err
                            continue
                if last_exc is not None:
                    raise last_exc
                raise RuntimeError("failed to instantiate model class")

            optional_loaders: list[Any] = []
            for name in ("AutoModelForImageTextToText", "AutoModelForVision2Seq"):
                cls = getattr(trf, name, None)
                if cls is not None:
                    optional_loaders.append(cls)
            last_err: BaseException | None = None
            self._model = None
            for cls in optional_loaders:
                try:
                    self._model = load_pretrained(cls).to(self.context.device)
                    break
                except Exception as err:
                    last_err = err
                    self._model = None
            if self._model is None:
                try:
                    from transformers import AutoModel

                    self._model = load_pretrained(AutoModel).to(self.context.device)
                except Exception as err:
                    last_err = err
                    try:
                        self._model = load_pretrained(AutoModelForCausalLM).to(self.context.device)
                    except Exception as err2:
                        raise ProviderError(
                            self.provider_name,
                            f"failed to load VLM from {model_root} (tried multimodal autos + AutoModel + CausalLM): {last_err!s} / {err2!s}",
                        ) from err2
            self._model.eval()
            self._torch = torch
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(self.provider_name, f"failed to load VLM from {model_root}: {exc}") from exc

    def unload_from_device(self) -> None:
        """Free VRAM; describe() will reload on next call."""
        model = self._model
        self._model = None
        if model is not None:
            try:
                del model
            except Exception:
                pass
        gc.collect()
        try:
            torch_mod = self._torch
            if self.context.device == "cuda" and torch_mod is not None and hasattr(torch_mod.cuda, "empty_cache"):
                torch_mod.cuda.empty_cache()
        except Exception:
            pass

    @staticmethod
    def _json_response_suffix(strict_json_instruction: bool) -> str:
        if strict_json_instruction:
            return (
                "\nRespond with ONLY one JSON object. Use ASCII double quotes for strings. "
                "No markdown fences, no keys in single quotes, no commentary before or after the JSON."
            )
        return "\nRespond with a single JSON object only (no markdown code fences, minimal prose)."

    def _generate(
        self,
        image_path: str,
        role: str,
        *,
        strict_json_instruction: bool = False,
        max_new_tokens: int | None = None,
    ) -> str:
        prompt = self._prompt_for_role(role) + self._json_response_suffix(strict_json_instruction)
        image = Image.open(image_path).convert("RGB")
        budget = int(self.max_new_tokens if max_new_tokens is None else max_new_tokens)
        try:
            if self._is_qwen_vl_family():
                return self._generate_qwen_vl(prompt, image, max_new_tokens=budget)
            inputs = self._processor(text=prompt, images=image, return_tensors="pt").to(self.context.device)
            with self._torch.inference_mode():
                generated = self._model.generate(**inputs, max_new_tokens=budget)
            return self._processor.batch_decode(generated, skip_special_tokens=True)[0]
        except Exception as exc:
            raise ProviderError(self.provider_name, f"inference failed for {image_path}: {exc}") from exc

    def _is_qwen_vl_family(self) -> bool:
        proc_name = self._processor.__class__.__name__.lower()
        if "qwen" in proc_name:
            return True
        tok = getattr(self._processor, "tokenizer", None)
        if tok is not None and "qwen" in str(getattr(tok, "name_or_path", "")).lower():
            return True
        cfg = getattr(self._model, "config", None)
        if cfg is not None and "qwen" in str(getattr(cfg, "model_type", "")).lower():
            return True
        root = str(getattr(self._processor, "name_or_path", "") or "").lower()
        return "qwen" in root

    def _qwen_user_messages(self, prompt: str, image: Image.Image) -> list[dict[str, Any]]:
        """ChatML layout expected by Qwen2.5-VL processor + optional qwen_vl_utils.process_vision_info."""
        return [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ],
            },
        ]

    def _fallback_process_vision_info(self, messages: list[dict[str, Any]]) -> tuple[list[Any], Any]:
        images: list[Any] = []
        for msg in messages:
            blocks = msg.get("content") or []
            if isinstance(blocks, str):
                continue
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "image" and block.get("image") is not None:
                    images.append(block["image"])
        return images, None

    def _generate_qwen_vl(self, prompt: str, image: Image.Image, *, max_new_tokens: int) -> str:
        messages = self._qwen_user_messages(prompt, image)
        text = self._processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs: Any
        video_inputs: Any
        try:
            from qwen_vl_utils import process_vision_info

            image_inputs, video_inputs = process_vision_info(messages)
        except Exception:
            image_inputs, video_inputs = self._fallback_process_vision_info(messages)

        proc_kw: dict[str, Any] = {
            "text": [text],
            "images": image_inputs,
            "padding": True,
            "return_tensors": "pt",
        }
        proc_kw["videos"] = video_inputs
        inputs = self._processor(**proc_kw)
        inputs = inputs.to(self.context.device)
        input_ids = inputs["input_ids"]
        seq_len = int(input_ids.shape[1])
        with self._torch.inference_mode():
            out_ids = self._model.generate(**inputs, max_new_tokens=max_new_tokens)
        new_tokens = out_ids[:, seq_len:]
        decoded = self._processor.batch_decode(
            new_tokens,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )
        return decoded[0] if decoded else ""

    def _prompt_for_role(self, role: str) -> str:
        if role == "screenshot":
            return (
                "Analyze this game/anime screenshot as composition and action reference. Return JSON with summary, "
                "appearance.hair, appearance.eyes, appearance.face, appearance.outfit, appearance.mecha, "
                "appearance.accessories, pose, action, camera_angle, composition, background, scene, "
                "effects_lighting, mood, combat_atmosphere, style.medium, style.lineart, style.color_palette, "
                "style.lighting, style.rendering, keywords, prompt_phrases."
            )
        if role in {"official", "identity", "init"}:
            return (
                "Analyze this official/canonical anime game character reference. Return JSON with summary, "
                "appearance.gender_presentation, appearance.hair, appearance.eyes, appearance.face, appearance.body, "
                "appearance.outfit, appearance.mecha, appearance.accessories, appearance.weapon, iconic_elements, "
                "pose, composition, background, style.medium, style.lineart, style.color_palette, style.lighting, "
                "style.rendering, keywords, prompt_phrases."
            )
        if role == "fanart":
            return (
                "Analyze this fanart reference. Return JSON with summary, appearance, style_tendency, "
                "composition_tendency, alternate_design_elements, reusable_style_elements, elements_to_avoid_overbinding, "
                "composition, background, style.medium, style.lineart, style.color_palette, style.lighting, "
                "style.rendering, keywords, prompt_phrases."
            )
        if role == "style":
            return (
                "Analyze this anime/game style reference. Return JSON with summary, style.medium, style.lineart, "
                "style.color_palette, style.lighting, style.rendering, brushwork, composition, mood, "
                "wallpaper_suitability, negative_style_risks, keywords, prompt_phrases."
            )
        return (
            "Analyze this anime/game character reference. Return JSON with summary, appearance.gender_presentation, "
            "appearance.hair, appearance.eyes, appearance.face, appearance.body, appearance.outfit, appearance.mecha, "
            "appearance.accessories, pose, composition, background, style.medium, style.lineart, style.color_palette, "
            "style.lighting, style.rendering, keywords, prompt_phrases."
        )

    def _extract_json_best(self, text: str) -> dict[str, Any] | None:
        for chunk in _json_candidate_slices(text):
            try:
                payload = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        return None

    @staticmethod
    def _normalize_flat_visual_keys(data: dict[str, Any]) -> None:
        """Merge top-level appearance_* / style_* keys into nested appearance/style dicts."""
        from_ap: dict[str, Any] = {}
        from_st: dict[str, Any] = {}
        removals: list[str] = []
        aprefix, sprefix = "appearance_", "style_"
        for k, v in list(data.items()):
            if not isinstance(k, str):
                continue
            if k.startswith(aprefix) and k != "appearance":
                sub = k[len(aprefix) :].strip("_")
                if sub:
                    from_ap[sub] = v
                removals.append(k)
            elif k.startswith(sprefix) and k != "style":
                sub = k[len(sprefix) :].strip("_")
                if sub:
                    from_st[sub] = v
                removals.append(k)
        for rk in removals:
            data.pop(rk, None)
        if from_ap:
            base = dict(data["appearance"]) if isinstance(data.get("appearance"), dict) else {}
            data["appearance"] = {**base, **from_ap}
        if from_st:
            base = dict(data["style"]) if isinstance(data.get("style"), dict) else {}
            data["style"] = {**base, **from_st}

    def _synthetic_summary(self, data: dict[str, Any]) -> str:
        kws = data.get("keywords")
        bits: list[str] = []
        if isinstance(kws, list):
            for item in kws[:16]:
                if isinstance(item, str) and item.strip():
                    bits.append(item.strip())
                elif isinstance(item, dict):
                    tag = item.get("tag") or item.get("name")
                    if tag:
                        bits.append(str(tag).strip())
        if bits:
            return ", ".join(bits[:12])
        appearance = data.get("appearance")
        if isinstance(appearance, dict):
            for key in ("hair", "eyes", "face", "outfit"):
                val = appearance.get(key)
                if isinstance(val, str) and val.strip():
                    return f"{key}: {val.strip()}"[:400]
        pp = data.get("prompt_phrases")
        if isinstance(pp, list) and pp and isinstance(pp[0], str):
            return pp[0].strip()[:400]
        return ""

    def _coerce_structured_caption(self, text: str, _role: str) -> dict[str, Any] | None:
        data = self._extract_json_best(text)
        if not data:
            return None
        self._normalize_flat_visual_keys(data)
        data.setdefault("summary", "")
        data.setdefault("appearance", {})
        data.setdefault("pose", "")
        data.setdefault("composition", "")
        data.setdefault("background", "")
        data.setdefault("style", {})
        data.setdefault("keywords", [])
        data.setdefault("prompt_phrases", [])
        data.setdefault("warnings", [])
        summary = str(data.get("summary") or "").strip()
        if not summary:
            data["summary"] = self._synthetic_summary(data)
        if not str(data.get("summary") or "").strip():
            return None
        return data
