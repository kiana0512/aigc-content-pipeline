# ComfyUI 基线接入说明

## 1. 当前阶段定位

当前仓库阶段是：

- baseline integration preparation
- compatibility layer
- workflow patching / mapping framework

当前仓库不是：

- ComfyUI 全家桶平台
- 完整视频平台
- 完整 LoRA / ControlNet 自动化平台

## 2. API workflow 边界（必须）

只接受真实 **API workflow JSON**。  
不接受：

- placeholder workflow JSON
- UI workflow JSON（通常包含 `nodes` 列表）

placeholder 报错提示：

`Current workflow JSON is still a placeholder and cannot be patched. Please replace it with an actual ComfyUI-exported workflow first.`

## 3. 如何导出可用 workflow

1. 在 ComfyUI 中搭图并跑通
2. 使用 `File -> Export (API)` 导出 JSON
3. 覆盖仓库对应 `workflows/comfyui/*.json`
4. 用真实 node id 更新 `configs/*node_map*.yaml`

## 4. 最小基线节点结构

推荐最小链路：

1. `CheckpointLoaderSimple`
2. `CLIPTextEncode`（positive）
3. `CLIPTextEncode`（negative）
4. `EmptyLatentImage`
5. `KSampler`
6. `VAEDecode`
7. `SaveImage`

## 5. UI icon / concept 基线建议

UI icon：

- 先 SDXL base
- 先固定 `1024x1024`
- 先固定 sampler/scheduler 组合
- 先不启用 LoRA/ControlNet

character concept：

- 先 SDXL base
- 先固定一组 prompt 模板
- 先做参数小范围对比
- 先不启用 LoRA/ControlNet

## 6. SaveImage patch 策略

当前默认仅 patch：

- `SaveImage.filename_prefix`

`output_dir` patch 仅作为 optional / experimental 能力，不建议作为基线依赖。

## 7. 模型目录与 family 说明

`classic_checkpoint / split_model / conditioning / postprocess / media_extension`  
是项目内部兼容抽象，不是 ComfyUI 官方术语。

## 8. strict_model_dir_check

- `false`：缺目录声明仅告警（适合调试/迁移期）
- `true`：缺必需目录直接失败（适合稳定团队/CI）

## 9. 常用命令

```bash
# 检查 workflow
python scripts/run_batch_generation.py --config configs/sdxl_icon.yaml --mode inspect_workflow

# 模型解析
python scripts/run_batch_generation.py --config configs/sdxl_icon.yaml --mode resolve_models --comfyui-root D:/ComfyUI

# 生成 mapping 建议
python scripts/run_batch_generation.py --config configs/sdxl_icon.yaml --mode suggest_mapping

# patch（手工映射）
python scripts/run_batch_generation.py \
  --config configs/sdxl_icon.yaml \
  --prompt-pack outputs/prompt_pack/ui_icons/prompt_pack.csv \
  --mode patch_workflow \
  --mapping-mode manual_map
```

## 10. 关联文档

- `docs/comfyui_usage_zh.md`
- `docs/comfyui_model_folders.md`
- `docs/workflow_import_zh.md`
