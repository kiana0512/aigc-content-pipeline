from aigc2d.comfy_workflow_analyzer import ComfyWorkflowAnalyzer


def img2img_ipadapter_workflow():
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
        "2": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
        "3": {"class_type": "LoraLoader", "inputs": {"model": ["1", 0], "clip": ["1", 1], "lora_name": "style.safetensors", "strength_model": 0.8, "strength_clip": 0.8}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "positive", "clip": ["3", 1]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative", "clip": ["3", 1]}},
        "6": {"class_type": "LoadImage", "inputs": {"image": "init.png"}},
        "7": {"class_type": "VAEEncode", "inputs": {"pixels": ["6", 0], "vae": ["2", 0]}},
        "8": {"class_type": "LoadImage", "inputs": {"image": "ref.png"}},
        "9": {"class_type": "IPAdapterAdvanced", "inputs": {"image": ["8", 0], "model": ["3", 0]}},
        "10": {"class_type": "KSampler", "inputs": {"model": ["9", 0], "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["7", 0], "seed": 1, "steps": 20, "cfg": 5.5, "sampler_name": "euler", "scheduler": "normal", "denoise": 0.6}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["2", 0]}},
        "12": {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": "out"}},
    }


def test_analyzer_maps_core_img2img_fields():
    analysis = ComfyWorkflowAnalyzer(img2img_ipadapter_workflow()).analyze()
    node_inputs = analysis["patch_contract"]["node_inputs"]

    assert analysis["node_inventory"]["1"]["class_type"] == "CheckpointLoaderSimple"
    assert analysis["detected_modules"]["lora"] is True
    assert analysis["workflow_type"] == "img2img_ipadapter"
    assert node_inputs["ckpt_name"]["node_id"] == "1"
    assert node_inputs["vae_name"]["node_id"] == "2"
    assert node_inputs["lora_name"]["node_id"] == "3"
    assert node_inputs["positive_prompt"]["node_id"] == "4"
    assert node_inputs["negative_prompt"]["node_id"] == "5"
    assert node_inputs["init_image"]["node_id"] == "6"
    assert node_inputs["identity_ref_image"]["node_id"] == "8"
    assert node_inputs["seed"]["node_id"] == "10"
    assert node_inputs["output_prefix"]["node_id"] == "12"


def test_analyzer_keeps_ambiguous_prompt_nodes():
    workflow = {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "a"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "b"}},
    }
    analysis = ComfyWorkflowAnalyzer(workflow).analyze()
    assert analysis["ambiguous_candidates"]["prompt_roles"]
    assert analysis["warnings"]
