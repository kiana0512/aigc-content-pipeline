# workflow-first 导入指南（中文）

本文说明如何把“已在 ComfyUI 中验证可运行的 API workflow JSON”导入本仓库，并走完 workflow-first v1 小闭环。

## 1. 为什么从“模型优先”切到“workflow 优先”

模型优先容易出现这些问题：

- 只知道模型名，不知道真实节点拓扑
- 不清楚具体可 patch 位点
- custom node 语义不透明
- patch 失败时难排查

workflow 优先的好处是：真实 API workflow JSON 直接描述执行图，是更可靠的事实来源。

## 2. API workflow JSON 为什么是单一事实来源

真实 API workflow JSON 包含：

- 节点 `class_type`
- 节点 `inputs`
- 节点间引用关系（node id + slot）

相比口头约定或手工猜测，它更接近真实运行状态。

## 3. 当前自动化链路

1. `workflow_inspector`：解析节点、参数、模型引用、未知节点
2. `model_resolver`：扫描本地模型目录并输出匹配报告
3. `mapping_suggester`：生成 node_map 建议与差异报告
4. `comfyui_adapter`：执行 patch（`manual_map` / `auto_detect`）

## 4. 如何自动匹配本地模型

`model_resolver` 会扫描配置中的目录（`comfyui_models`），并输出：

- resolved models（已匹配）
- missing models（缺失）
- duplicate candidates（多候选冲突）
- maybe matched candidates（近似匹配）

还支持两类手工兜底策略：

- `aliases`：模型名别名映射
- `path_overrides`：直接指定本地文件路径

示例：

```yaml
comfyui:
  model_resolution_policy:
    aliases:
      "qwen_image_unet_fp8.safetensors": "qwen_unet_fp8.safetensors"
    path_overrides:
      "special_clip.safetensors": "D:/ComfyUI/models/text_encoders/clip_final.safetensors"
```

## 5. 自动 mapping 建议与人工确认

`suggest_mapping` 会输出：

- `mapping_suggestion.yaml`
- `mapping_diff.md`
- `mapping_manual_review.yaml`

其中 `mapping_manual_review.yaml` 用于列出低置信位点，方便人工补齐。

## 6. auto patch vs manual patch

- `manual_map`：严格按手工 node_map patch，确定性高
- `auto_detect`：自动识别高置信字段并 patch，低置信项进入报告

推荐：先 `auto_detect` 快速起步，再对关键位点落地 `manual_map`。

## 7. 统一 run 输出目录

`workflow_import_pipeline` 会把结果统一输出到：

`results/runs/<run_name>/`

包含：

- `workflow_inspection.json`
- `model_resolution.json`
- `mapping_suggestion.yaml`
- `mapping_diff.md`
- `mapping_manual_review.yaml`
- `patch_report.json`
- `patch_report.md`
- `patched_workflow.json`
- `run_manifest.json`

## 8. 完整使用流程（推荐）

1. 在 ComfyUI 搭图并验证可运行
2. `File -> Export (API)` 导出 API workflow JSON
3. 放入仓库 `workflows/comfyui/`
4. 准备配置文件（workflow 路径、模型目录、prompt pack）
5. 执行一键 pipeline
6. 查看 run 目录报告并修正低置信项
7. 回到 ComfyUI 或 API 执行 patched workflow

示例命令：

```bash
python scripts/run_batch_generation.py \
  --config configs/qwen_image_example.yaml \
  --prompt-pack outputs/prompt_pack/character_concepts/prompt_pack.csv \
  --mode workflow_import_pipeline \
  --run-name qwen_round1 \
  --comfyui-root D:/ComfyUI
```

## 9. Qwen split-model 示例说明

仓库提供样例：

- `workflows/comfyui/qwen_image_api_example.json`
- `tests/fixtures/qwen_api_workflow.json`

该样例可回归验证以下识别能力：

- `UNETLoader`
- `CLIPLoader`
- `VAELoader`
- `LoraLoaderModelOnly`
- `KSampler`
- `SaveImage`
- 正负 prompt
- `width/height/seed/steps/cfg/sampler/scheduler`
- `split_model` family 检测

## 10. 当前已实现与未实现边界

已实现：

- workflow-first v1 小闭环
- API workflow 严格边界校验
- 模型匹配报告 + alias/path override
- mapping 建议 + manual review 清单

未实现（仅兼容预留）：

- 自动理解所有 custom node
- LoRA/ControlNet 完整训练与生产部署链路
- 视频/音频/3D 全链路自动化平台
- UE5 自动化联动
