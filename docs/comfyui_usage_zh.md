# ComfyUI 使用指南（中文）

本文面向 `game-aigc-asset-workflow` 当前阶段（baseline integration preparation + workflow-first v1 收口）。

## B1. ComfyUI 的定位

ComfyUI 是节点式生成工作流平台，不只是文生图工具。它可以承载图片、视频、音频条件、3D/API 扩展节点等不同类型工作流。  
本仓库当前主线仍是图片基线（UI icon / character concept）。

## B2. 当前仓库与 ComfyUI 的关系

本仓库不是 ComfyUI 本体，而是游戏 AIGC 资产生产流实验仓库。  
当前通过以下方式与 ComfyUI 对接：

- 真实 API workflow JSON
- node mapping（手工映射 + 自动建议）
- workflow patch（`manual_map` / `auto_detect`）
- 配置驱动（`configs/*.yaml`）

## B3. 当前支持的模式

`scripts/run_batch_generation.py` 支持：

1. `manifest`：生成 `run_manifest.json`
2. `inspect_workflow`：解析 workflow 节点结构与关键参数
3. `resolve_models`：扫描本地模型目录并做匹配报告
4. `suggest_mapping`：生成 node_map 建议与差异报告
5. `patch_workflow`：按映射批量 patch
6. `auto_patch_workflow`：强制 `auto_detect` patch
7. `workflow_import_pipeline` / `prepare_workflow_import`：一键小闭环
8. `submit`：实验性提交 ComfyUI API

## B4. 关键边界（必须遵守）

1. 只接受真实 API workflow JSON
2. UI workflow JSON（含 `nodes` 列表）会拒绝
3. placeholder workflow JSON 会拒绝
4. 未知 custom node 不会假装理解，会进入 unresolved 报告
5. LoRA / ControlNet 目前是接口预留，默认关闭
6. submit 模式是实验性能力
7. 当前不做 UE5 自动化

## B5. workflow-first 是什么

workflow-first 的核心是：把“真实可运行 workflow JSON”作为单一事实来源（source of truth）。

流程是：

1. 先检查 workflow（inspect）
2. 再检查模型匹配（resolve）
3. 再给映射建议（suggest）
4. 最后 patch（manual 或 auto）

## B6. family 术语说明

`classic_checkpoint / split_model / conditioning / postprocess / media_extension`  
是本项目内部兼容抽象，不是 ComfyUI 官方术语。

常见关系：

- `classic_checkpoint`：checkpoint 单体加载（常见 SDXL 基线）
- `split_model`：`diffusion_models + text_encoders + vae`
- `conditioning`：controlnet / clip_vision / style 链路
- `postprocess`：放大与后处理链路
- `media_extension`：音频等扩展链路

## B7. 参数与配置怎么选（当前主线）

UI icon / character concept 首轮建议：

- `workflow_model_family`：先选 `classic_checkpoint`
- 分辨率：先固定 `1024x1024`
- `steps`：先 25~35
- `cfg`：先 5~8 区间
- `sampler/scheduler`：先固定组合再对比
- LoRA / ControlNet：基线稳定前先关闭
- `strict_model_dir_check`：
  - 调试期 `false`（先出报告）
  - 稳定期/CI `true`（缺失即失败）

## B8. 与真实 ComfyUI workflow 对接流程

1. 在 ComfyUI 中搭并跑通真实图
2. 使用 `File -> Export (API)` 导出 API JSON
3. 用导出文件替换仓库中的 placeholder workflow
4. 修改对应 node map（或先跑自动建议）
5. 执行 patch 并检查 patch report
6. 回到 ComfyUI 或通过 API 执行

## B9. 已自动完成 / 自动建议 / 人工确认

已自动完成：

- API workflow 边界校验
- 常见节点识别（prompt/sampler/latent/save/loader）
- 模型扫描与匹配报告
- 高置信字段自动 patch

自动建议：

- node_map 建议 YAML
- mapping diff 报告
- 模型 alias / path override 后的匹配建议

仍需人工确认：

- custom node 语义
- 低置信映射位点
- 多候选模型冲突
- 业务层参数策略（风格一致性、结构可控性）

## B10. 常见错误

1. 把 UI workflow JSON 当 API JSON 使用
2. placeholder workflow 未替换就 patch
3. baseline 未稳定就同时改太多变量
4. 模型文件名不一致但未看 `model_resolution` 报告
5. 忽略 `mapping_manual_review.yaml` 直接批量跑

## B11. 最小实操清单（今天/明天可直接照做）

1. 在 ComfyUI 搭最小 baseline 图：  
   `CheckpointLoaderSimple -> CLIPTextEncode(positive/negative) -> EmptyLatentImage -> KSampler -> VAEDecode -> SaveImage`
2. 用 SDXL base 至少跑通 1 张 UI icon 或 character concept
3. 用 `File -> Export (API)` 导出真实 API workflow JSON
4. 用导出的 JSON 覆盖仓库对应 placeholder workflow
5. 填写真实 node id 到对应 node_map YAML（或先用 `suggest_mapping`）
6. 执行 patch 生成 patched workflow
7. 固定并记录本轮：
   - prompt / negative prompt
   - seed
   - sampler / scheduler
   - image size
8. 把实验信息补到 `docs/experiment_log.md`
9. baseline 稳定前不要急着叠加 LoRA / ControlNet
10. 第一轮目标是“小闭环跑通”，不是追求最强效果

提示：

- 今天目标：完成 baseline 小闭环  
- 明天目标：进入正式资产生成流程与第一轮参数/提示词迭代

## B12. workflow-first v1 一键闭环（推荐）

使用 `workflow_import_pipeline`：

```bash
python scripts/run_batch_generation.py \
  --config configs/qwen_image_example.yaml \
  --prompt-pack outputs/prompt_pack/character_concepts/prompt_pack.csv \
  --mode workflow_import_pipeline \
  --run-name qwen_round1
```

输出目录：

`results/runs/qwen_round1/`

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
