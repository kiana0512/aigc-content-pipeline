# Workflow Notes

## 1. 当前状态

`workflows/comfyui/*.json` 中仍有占位文件。  
占位文件用于路径契约，不代表可直接运行。

## 2. 格式边界

不要混用两种 JSON：

- UI workflow JSON（编辑器图格式，常见 `nodes` 列表）
- API workflow JSON（执行 prompt 格式，node-id 字典）

`patch_workflow` 仅支持 API workflow JSON。

## 3. 替换步骤

1. 在 ComfyUI 中搭图并跑通  
2. `File -> Export (API)` 导出真实 API JSON  
3. 覆盖仓库对应 workflow 文件  
4. 更新 node mapping 中的真实 node id  

## 4. 当前基线优先级

1. `sdxl_ui_icon_base.json`  
2. `sdxl_concept_base.json`  

## 5. 后续兼容方向（不仅 SDXL）

后续将逐步支持 split-model workflow（如 Qwen / FLUX / 视频家族思路），其常见目录需求为：

- `diffusion_models`
- `text_encoders`
- `vae`

## 6. 术语说明

`classic_checkpoint / split_model / conditioning / postprocess / media_extension`  
是项目内部兼容抽象，不是 ComfyUI 官方术语。

## 7. patch 范围（当前实现）

- positive / negative prompt
- seed / width / height / steps / cfg / sampler / scheduler
- `SaveImage.filename_prefix`

LoRA / ControlNet 目前仅接口预留，不是完整端到端平台。
