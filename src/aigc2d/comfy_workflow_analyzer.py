from __future__ import annotations

from collections import deque
from typing import Any


MODEL_FIELD_RULES = {
    ("CheckpointLoaderSimple", "ckpt_name"): "ckpt_name",
    ("VAELoader", "vae_name"): "vae_name",
    ("LoraLoader", "lora_name"): "lora_name",
    ("LoraLoader", "strength_model"): "lora_strength_model",
    ("LoraLoader", "strength_clip"): "lora_strength_clip",
    ("LoraLoaderModelOnly", "lora_name"): "lora_name",
    ("LoraLoaderModelOnly", "strength_model"): "lora_strength_model",
    ("CLIPVisionLoader", "clip_name"): "clip_vision_name",
    ("IPAdapterModelLoader", "ipadapter_file"): "ipadapter_file",
    ("ControlNetLoader", "control_net_name"): "control_net_name",
    ("UpscaleModelLoader", "model_name"): "upscale_model_name",
}

SAMPLER_FIELDS = {
    "seed": "seed",
    "steps": "steps",
    "cfg": "cfg",
    "sampler_name": "sampler_name",
    "scheduler": "scheduler",
    "denoise": "denoise",
}

SECOND_SAMPLER_FIELDS = {
    "seed": "second_seed",
    "steps": "second_steps",
    "cfg": "second_cfg",
    "sampler_name": "second_sampler_name",
    "scheduler": "second_scheduler",
    "denoise": "second_denoise",
}


class ComfyWorkflowAnalyzer:
    def __init__(self, workflow: dict[str, Any]) -> None:
        self.workflow = {str(node_id): node for node_id, node in workflow.items() if isinstance(node, dict)}
        self.upstream_map: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in self.workflow}
        self.downstream_map: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in self.workflow}

    def analyze(self) -> dict[str, Any]:
        self._build_graph()
        inventory = self._node_inventory()
        classified = self._classified_nodes()
        reachable = self._reachable_to_save_nodes(classified["save_image"])
        warnings: list[str] = []
        ambiguous = {"image_roles": [], "prompt_roles": [], "sampler_roles": []}

        patch_contract: dict[str, Any] = {"node_inputs": {}}
        candidates = {
            "prompt_nodes": self._candidate_records(classified["prompt"]),
            "image_nodes": self._candidate_records(classified["load_image"]),
            "sampler_nodes": self._candidate_records(classified["sampler"]),
            "save_nodes": self._candidate_records(classified["save_image"]),
            "model_nodes": self._candidate_records(classified["model_loader"]),
            "size_nodes": self._size_candidates(),
        }

        self._map_model_fields(patch_contract, candidates, ambiguous, reachable)
        self._map_prompt_fields(patch_contract, ambiguous, warnings)
        image_role_records = self._map_image_fields(patch_contract, ambiguous, warnings)
        self._map_sampler_fields(patch_contract, candidates, warnings)
        self._map_save_fields(patch_contract)
        workflow_type = self._workflow_type(classified, image_role_records)
        self._map_size_fields(patch_contract, workflow_type, candidates, ambiguous)

        detected_modules = {
            "checkpoint": bool(classified["checkpoint"]),
            "vae": bool(classified["vae"]),
            "lora": bool(classified["lora"]),
            "clip_vision": bool(classified["clip_vision"]),
            "ipadapter": bool(classified["ipadapter"]),
            "controlnet": bool(classified["controlnet"]),
            "preprocessors": sorted({self._class_type(node_id) for node_id in classified["preprocessor"]}),
            "sampler": bool(classified["sampler"]),
            "upscale": bool(classified["upscale"]),
            "video": bool(classified["video"]),
        }

        return {
            "workflow_type": workflow_type,
            "node_inventory": inventory,
            "graph": {
                "upstream_map": self.upstream_map,
                "downstream_map": self.downstream_map,
            },
            "detected_modules": detected_modules,
            "model_loader_candidates": self._candidate_records(classified["model_loader"]),
            "prompt_candidates": candidates["prompt_nodes"],
            "image_input_candidates": candidates["image_nodes"],
            "sampler_candidates": candidates["sampler_nodes"],
            "save_image_candidates": candidates["save_nodes"],
            "controlnet_candidates": self._candidate_records(classified["controlnet"]),
            "ipadapter_candidates": self._candidate_records(classified["ipadapter"]),
            "upscale_candidates": self._candidate_records(classified["upscale"]),
            "video_candidates": self._candidate_records(classified["video"]),
            "auto_patch_candidates": patch_contract["node_inputs"],
            "patch_contract": patch_contract,
            "candidates": candidates,
            "ambiguous_candidates": ambiguous,
            "warnings": warnings,
        }

    def _build_graph(self) -> None:
        for dst_id, node in self.workflow.items():
            inputs = node.get("inputs", {})
            if not isinstance(inputs, dict):
                continue
            for input_name, value in inputs.items():
                ref = self._node_ref(value)
                if not ref:
                    continue
                src_id, output_index = ref
                edge = {"node_id": dst_id, "input": input_name, "output_index": output_index}
                reverse = {"node_id": src_id, "input": input_name, "output_index": output_index}
                self.downstream_map.setdefault(src_id, []).append(edge)
                self.upstream_map.setdefault(dst_id, []).append(reverse)

    def _node_ref(self, value: Any) -> tuple[str, int] | None:
        if (
            isinstance(value, list)
            and len(value) >= 2
            and str(value[0]) in self.workflow
            and isinstance(value[1], int)
        ):
            return str(value[0]), value[1]
        return None

    def _node_inventory(self) -> dict[str, dict[str, Any]]:
        inventory: dict[str, dict[str, Any]] = {}
        for node_id in self._topological_order():
            node = self.workflow[node_id]
            inputs = node.get("inputs", {}) if isinstance(node.get("inputs"), dict) else {}
            inventory[node_id] = {
                "class_type": node.get("class_type", ""),
                "title": (node.get("_meta") or {}).get("title", ""),
                "input_keys": list(inputs.keys()),
                "upstream_node_refs": self.upstream_map.get(node_id, []),
                "downstream_node_refs": self.downstream_map.get(node_id, []),
            }
        return inventory

    def _classified_nodes(self) -> dict[str, list[str]]:
        groups = {
            "model_loader": [],
            "checkpoint": [],
            "vae": [],
            "lora": [],
            "clip_vision": [],
            "prompt": [],
            "load_image": [],
            "save_image": [],
            "sampler": [],
            "controlnet": [],
            "preprocessor": [],
            "ipadapter": [],
            "upscale": [],
            "video": [],
            "empty_latent": [],
            "vae_encode": [],
            "vae_decode": [],
            "image_scale": [],
            "latent_upscale": [],
        }
        for node_id in self._topological_order():
            class_type = self._class_type(node_id)
            lowered = class_type.lower()
            inputs = self._inputs(node_id)
            if class_type in {
                "CheckpointLoaderSimple",
                "UNETLoader",
                "DualCLIPLoader",
                "TripleCLIPLoader",
                "CLIPLoader",
                "VAELoader",
                "LoraLoader",
                "LoraLoaderModelOnly",
                "ControlNetLoader",
                "CLIPVisionLoader",
                "IPAdapterModelLoader",
                "UpscaleModelLoader",
            }:
                groups["model_loader"].append(node_id)
            if class_type == "CheckpointLoaderSimple":
                groups["checkpoint"].append(node_id)
            if class_type in {"VAELoader", "VAEEncode", "VAEDecode"}:
                groups["vae"].append(node_id)
            if class_type in {"LoraLoader", "LoraLoaderModelOnly"}:
                groups["lora"].append(node_id)
            if class_type == "CLIPVisionLoader":
                groups["clip_vision"].append(node_id)
            if class_type in {"CLIPTextEncode", "CLIPTextEncodeSDXL", "CLIPTextEncodeFlux"} or (
                "text" in inputs and any(token in lowered for token in ["clip", "text", "prompt"])
            ):
                groups["prompt"].append(node_id)
            if class_type in {"LoadImage", "LoadImageMask"}:
                groups["load_image"].append(node_id)
            if class_type == "SaveImage":
                groups["save_image"].append(node_id)
            if class_type in {"KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced"}:
                groups["sampler"].append(node_id)
            if class_type in {"ControlNetApply", "ControlNetApplyAdvanced", "ControlNetLoader"} or "controlnet" in lowered:
                groups["controlnet"].append(node_id)
            if class_type in {"DepthAnythingPreprocessor", "Canny", "LineArt", "Openpose", "DWPreprocessor"} or any(
                token in lowered for token in ["preprocessor", "depth", "canny", "lineart", "pose"]
            ):
                groups["preprocessor"].append(node_id)
            if "ipadapter" in lowered:
                groups["ipadapter"].append(node_id)
            if class_type in {"ImageUpscaleWithModel", "ImageScale", "UltimateSDUpscale", "UpscaleModelLoader"} or any(
                token in lowered for token in ["upscale", "scale"]
            ):
                groups["upscale"].append(node_id)
            if any(token in lowered for token in ["vhs", "videocombine", "animatediff", "svd", "wan", "video", "animate", "frame"]):
                groups["video"].append(node_id)
            if class_type == "EmptyLatentImage":
                groups["empty_latent"].append(node_id)
            if class_type == "VAEEncode":
                groups["vae_encode"].append(node_id)
            if class_type == "VAEDecode":
                groups["vae_decode"].append(node_id)
            if class_type == "ImageScale":
                groups["image_scale"].append(node_id)
            if class_type in {"LatentUpscale", "LatentUpscaleBy"}:
                groups["latent_upscale"].append(node_id)
        return groups

    def _map_model_fields(
        self,
        patch_contract: dict[str, Any],
        candidates: dict[str, Any],
        ambiguous: dict[str, Any],
        reachable_to_save: set[str],
    ) -> None:
        by_field: dict[str, list[dict[str, Any]]] = {}
        for node_id, node in self.workflow.items():
            class_type = str(node.get("class_type", ""))
            for input_name in self._inputs(node_id):
                field_name = MODEL_FIELD_RULES.get((class_type, input_name))
                if field_name:
                    by_field.setdefault(field_name, []).append(self._mapping(field_name, node_id, input_name, optional=True))
        for field_name, records in by_field.items():
            selected = self._prefer_reachable(records, reachable_to_save)
            patch_contract["node_inputs"][field_name] = selected
            if len(records) > 1:
                ambiguous.setdefault("model_fields", {})[field_name] = records
        candidates["model_fields"] = by_field

    def _map_prompt_fields(self, patch_contract: dict[str, Any], ambiguous: dict[str, Any], warnings: list[str]) -> None:
        roles: dict[str, list[dict[str, Any]]] = {"positive_prompt": [], "negative_prompt": []}
        prompt_nodes = [
            node_id
            for node_id, node in self.workflow.items()
            if "text" in self._inputs(node_id) and self._class_type(node_id).lower().startswith("cliptextencode")
        ]
        for node_id in prompt_nodes:
            immediate_inputs = {str(edge.get("input", "")) for edge in self.downstream_map.get(node_id, [])}
            seen_inputs = immediate_inputs or self._downstream_input_names(node_id)
            has_positive = "positive" in seen_inputs
            has_negative = "negative" in seen_inputs
            if has_positive and has_negative:
                ambiguous["prompt_roles"].append(self._node_summary(node_id))
                continue
            if has_positive:
                roles["positive_prompt"].append(self._mapping("positive_prompt", node_id, "text", optional=False))
            if has_negative:
                roles["negative_prompt"].append(self._mapping("negative_prompt", node_id, "text", optional=False))
        if not roles["positive_prompt"] and not roles["negative_prompt"] and len(prompt_nodes) == 2:
            ambiguous["prompt_roles"] = [self._node_summary(node_id) for node_id in prompt_nodes]
            warnings.append("Prompt nodes could not be classified from graph links; please verify positive/negative prompt mapping.")
        for field_name, records in roles.items():
            if len(records) == 1:
                patch_contract["node_inputs"][field_name] = records[0]
            elif len(records) > 1:
                patch_contract["node_inputs"][field_name] = records[0]
                ambiguous["prompt_roles"].extend(records[1:])
                warnings.append(f"Multiple {field_name} candidates found; first topological node was selected.")

    def _map_image_fields(
        self,
        patch_contract: dict[str, Any],
        ambiguous: dict[str, Any],
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        role_records: list[dict[str, Any]] = []
        ipadapter_images: list[dict[str, Any]] = []
        for node_id, node in self.workflow.items():
            if self._class_type(node_id) != "LoadImage" or "image" not in self._inputs(node_id):
                continue
            role = ""
            source = "auto"
            optional = True
            if self._load_image_is_init(node_id):
                role = "init_image"
                optional = False
            elif self._reaches_class(node_id, lambda c: "ipadapter" in c.lower()):
                ipadapter_images.append(self._mapping("", node_id, "image", optional=True, source="auto_order_inferred"))
                continue
            elif self._reaches_class(
                node_id,
                lambda c: any(token in c.lower() for token in ["controlnet", "preprocessor", "depth", "canny", "lineart", "pose"]),
            ):
                role = "control_image"
            elif self._only_reaches_preview_or_save(node_id):
                continue
            if role:
                record = self._mapping(role, node_id, "image", optional=optional, source=source)
                patch_contract["node_inputs"].setdefault(role, record)
                role_records.append(record)
            else:
                ambiguous["image_roles"].append(self._node_summary(node_id))
        if ipadapter_images:
            role_names = ["identity_ref_image", "style_ref_image", "composition_ref_image"]
            for index, record in enumerate(ipadapter_images):
                field = role_names[index] if index < len(role_names) else f"extra_ref_image_{index + 1}"
                record["field"] = field
                patch_contract["node_inputs"].setdefault(field, record)
                role_records.append(record)
            if len(ipadapter_images) > 1:
                warnings.append("IPAdapter image roles inferred by order; please verify identity/style/composition mapping.")
        return role_records

    def _map_sampler_fields(self, patch_contract: dict[str, Any], candidates: dict[str, Any], warnings: list[str]) -> None:
        sampler_nodes = [record["node_id"] for record in candidates["sampler_nodes"]]
        for sampler_index, node_id in enumerate(sampler_nodes[:2]):
            rules = SAMPLER_FIELDS if sampler_index == 0 else SECOND_SAMPLER_FIELDS
            for input_name, field_name in rules.items():
                if input_name in self._inputs(node_id):
                    patch_contract["node_inputs"][field_name] = self._mapping(field_name, node_id, input_name, optional=True)
        if len(sampler_nodes) > 2:
            warnings.append("More than two sampler nodes found; only primary and secondary sampler fields were auto-mapped.")

    def _map_save_fields(self, patch_contract: dict[str, Any]) -> None:
        save_nodes = [node_id for node_id, node in self.workflow.items() if self._class_type(node_id) == "SaveImage" and "filename_prefix" in self._inputs(node_id)]
        ordered = [node_id for node_id in self._topological_order() if node_id in save_nodes]
        if len(ordered) == 1:
            patch_contract["node_inputs"]["output_prefix"] = self._mapping("output_prefix", ordered[0], "filename_prefix", optional=True)
            return
        prefix_names = ["first_pass_prefix", "second_pass_prefix", "upscale_prefix"]
        for index, node_id in enumerate(ordered):
            field = prefix_names[index] if index < len(prefix_names) else f"extra_prefix_{index + 1}"
            if self._has_upstream_class(node_id, lambda c: "upscale" in c.lower()):
                field = "upscale_prefix"
            patch_contract["node_inputs"].setdefault(field, self._mapping(field, node_id, "filename_prefix", optional=True))

    def _map_size_fields(
        self,
        patch_contract: dict[str, Any],
        workflow_type: str,
        candidates: dict[str, Any],
        ambiguous: dict[str, Any],
    ) -> None:
        size_candidates = candidates.get("size_nodes", [])
        preferred_classes = ("EmptyLatentImage",) if workflow_type == "text2img" else ("ImageScale", "LatentUpscale", "LatentUpscaleBy")
        preferred = [item for item in size_candidates if item["class_type"] in preferred_classes]
        selected = preferred[0] if preferred else (size_candidates[0] if len(size_candidates) == 1 else None)
        if not selected:
            if size_candidates:
                ambiguous.setdefault("size_roles", size_candidates)
            return
        node_id = selected["node_id"]
        for field in ["width", "height"]:
            if field in self._inputs(node_id):
                patch_contract["node_inputs"][field] = self._mapping(field, node_id, field, optional=True)

    def _workflow_type(self, classified: dict[str, list[str]], image_role_records: list[dict[str, Any]]) -> str:
        has_init = any(record.get("field") == "init_image" for record in image_role_records)
        has_ip = bool(classified["ipadapter"])
        has_control = bool(classified["controlnet"])
        has_depth = any("depth" in self._class_type(node_id).lower() for node_id in classified["preprocessor"])
        has_lora = bool(classified["lora"])
        has_upscale = bool(classified["upscale"])
        if classified["video"]:
            return "video"
        if classified["load_image"] and classified["upscale"] and classified["save_image"] and not classified["sampler"]:
            return "upscale_only"
        if has_init and has_ip and has_control and has_depth and has_lora and has_upscale:
            return "img2img_ipadapter_depth_lora_upscale"
        if has_init and has_ip and has_control:
            return "img2img_ipadapter_controlnet"
        if has_init and has_ip:
            return "img2img_ipadapter"
        if has_init and has_control:
            return "img2img_controlnet"
        if has_init:
            return "img2img"
        if classified["empty_latent"] and classified["sampler"] and classified["vae_decode"] and classified["save_image"]:
            return "text2img"
        return "custom"

    def _size_candidates(self) -> list[dict[str, Any]]:
        records = []
        for node_id in self._topological_order():
            inputs = self._inputs(node_id)
            if "width" in inputs and "height" in inputs and self._class_type(node_id) in {
                "EmptyLatentImage",
                "ImageScale",
                "LatentUpscale",
                "LatentUpscaleBy",
            }:
                records.append(self._node_summary(node_id))
        return records

    def _load_image_is_init(self, node_id: str) -> bool:
        queue = deque([node_id])
        seen = {node_id}
        vae_encode_nodes: set[str] = set()
        while queue:
            current = queue.popleft()
            for edge in self.downstream_map.get(current, []):
                dst = edge["node_id"]
                class_type = self._class_type(dst)
                if class_type == "VAEEncode":
                    vae_encode_nodes.add(dst)
                    continue
                if class_type not in {"ImageScale", "LoadImageMask"}:
                    continue
                if dst not in seen:
                    seen.add(dst)
                    queue.append(dst)
        return any(
            self._has_downstream_sampler_input(vae_node, "latent_image")
            for vae_node in vae_encode_nodes
        )

    def _has_downstream_sampler_input(self, node_id: str, input_name: str) -> bool:
        queue = deque([node_id])
        seen = {node_id}
        while queue:
            current = queue.popleft()
            for edge in self.downstream_map.get(current, []):
                dst = edge["node_id"]
                if self._is_sampler(dst) and edge.get("input") == input_name:
                    return True
                if dst not in seen:
                    seen.add(dst)
                    queue.append(dst)
        return False

    def _downstream_input_names(self, node_id: str) -> set[str]:
        names: set[str] = set()
        queue = deque([node_id])
        seen = {node_id}
        while queue:
            current = queue.popleft()
            for edge in self.downstream_map.get(current, []):
                names.add(str(edge.get("input", "")))
                dst = edge["node_id"]
                if dst not in seen:
                    seen.add(dst)
                    queue.append(dst)
        return names

    def _reaches_class(self, node_id: str, predicate: Any) -> bool:
        queue = deque([node_id])
        seen = {node_id}
        while queue:
            current = queue.popleft()
            for edge in self.downstream_map.get(current, []):
                dst = edge["node_id"]
                if predicate(self._class_type(dst)):
                    return True
                if dst not in seen:
                    seen.add(dst)
                    queue.append(dst)
        return False

    def _only_reaches_preview_or_save(self, node_id: str) -> bool:
        downstream = self.downstream_map.get(node_id, [])
        if not downstream:
            return False
        allowed = {"PreviewImage", "SaveImage"}
        return all(self._class_type(edge["node_id"]) in allowed for edge in downstream)

    def _has_upstream_class(self, node_id: str, predicate: Any) -> bool:
        queue = deque([node_id])
        seen = {node_id}
        while queue:
            current = queue.popleft()
            for edge in self.upstream_map.get(current, []):
                src = edge["node_id"]
                if predicate(self._class_type(src)):
                    return True
                if src not in seen:
                    seen.add(src)
                    queue.append(src)
        return False

    def _reachable_to_save_nodes(self, save_nodes: list[str]) -> set[str]:
        reachable = set(save_nodes)
        queue = deque(save_nodes)
        while queue:
            current = queue.popleft()
            for edge in self.upstream_map.get(current, []):
                src = edge["node_id"]
                if src not in reachable:
                    reachable.add(src)
                    queue.append(src)
        return reachable

    def _prefer_reachable(self, records: list[dict[str, Any]], reachable: set[str]) -> dict[str, Any]:
        for record in records:
            if record["node_id"] in reachable:
                return record
        return records[0]

    def _topological_order(self) -> list[str]:
        def key(node_id: str) -> tuple[int, str]:
            return (int(node_id), node_id) if node_id.isdigit() else (10**9, node_id)

        return sorted(self.workflow, key=key)

    def _candidate_records(self, node_ids: list[str]) -> list[dict[str, Any]]:
        return [self._node_summary(node_id) for node_id in self._topological_order() if node_id in set(node_ids)]

    def _node_summary(self, node_id: str) -> dict[str, Any]:
        inputs = self._inputs(node_id)
        return {
            "node_id": node_id,
            "class_type": self._class_type(node_id),
            "title": (self.workflow[node_id].get("_meta") or {}).get("title", ""),
            "input_keys": list(inputs.keys()),
        }

    def _mapping(
        self,
        field: str,
        node_id: str,
        input_name: str,
        optional: bool,
        source: str = "auto",
    ) -> dict[str, Any]:
        return {
            "node_id": str(node_id),
            "input": input_name,
            "optional": optional,
            "source": source,
            "field": field,
        }

    def _inputs(self, node_id: str) -> dict[str, Any]:
        inputs = self.workflow[node_id].get("inputs", {})
        return inputs if isinstance(inputs, dict) else {}

    def _class_type(self, node_id: str) -> str:
        return str(self.workflow[node_id].get("class_type", ""))

    def _is_sampler(self, node_id: str) -> bool:
        return self._class_type(node_id) in {"KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced"}
