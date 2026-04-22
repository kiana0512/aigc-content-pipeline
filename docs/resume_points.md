# Resume Points

## 项目名称建议

中文：
- 游戏 AIGC 资产生成实验工作流

英文：
- Game AIGC Asset Generation Experimental Workflow
- Game-Oriented AIGC Asset Workflow

## 关键词

- ComfyUI
- Stable Diffusion / SDXL
- Prompt Engineering
- Workflow Patching
- Model Resolution
- Batch Generation
- Experiment Tracking
- LoRA / ControlNet (interface-ready)
- UE5 downstream validation planning

## 项目定位

本项目是一个面向游戏资产生产场景的工程化实验仓库，重点在：

- 基线工作流可复用
- 参数与提示词可追踪
- 批量任务可管理
- 输出结果可归档与对比

## Resume Description（中文）

围绕 UI icon 与角色概念图场景，搭建了基于 ComfyUI + Stable Diffusion/SDXL 的 baseline-focused 资产生成工作流。完成了提示词模板、参数配置、批量出图入口、workflow patch、结果索引与实验记录机制。针对 LoRA / ControlNet / 参考图条件链路完成接口预留与接入准备，并面向 UE5 下游使用场景规划了验证维度与检查项，用于后续分阶段验证与扩展。

## Resume Description（English）

Built a baseline-focused game asset generation workflow using ComfyUI and Stable Diffusion/SDXL for UI icon and character concept scenarios. Implemented reusable prompt templates, parameterized batch generation, workflow patching, result indexing, and experiment logging for reproducible iteration. Prepared interface-ready hooks for LoRA/ControlNet and reference-conditioned extensions, and planned downstream validation dimensions for UE5-oriented usage.

## Short Resume Version

Built a baseline-focused game AIGC workflow on ComfyUI + SDXL, covering prompt templates, configurable batch generation, workflow patching, and experiment tracking, with interface-ready preparation for LoRA/ControlNet and planned UE5 downstream validation.

## 可选简历要点（Bullet Points）

### Version A
- 搭建游戏资产生成 baseline 工作流（UI icon / character concept），实现 prompt 模板化、参数化配置、批量 patch 出图与结果归档。  
- 以 workflow-first 方式引入真实 ComfyUI API workflow，对节点参数、模型引用、映射建议与 patch 报告进行自动化处理。  
- 对 LoRA / ControlNet 完成接口预留与实验准备，面向 UE5 下游使用场景规划验证维度与检查项。  

### Version B
- 设计并实现 AIGC 资产实验仓库的核心链路：配置管理、prompt 资产化、批量任务组织、实验日志与结果索引。  
- 建立 API workflow 严格边界（拒绝 placeholder / UI workflow），提升 patch 流程稳定性与可追溯性。  
- 在保持基线可用的前提下，完成 split-model 兼容准备与模型目录解析能力扩展。  

### Version C
- 基于 ComfyUI + SDXL 构建可复用的游戏资产生成流程，支持从 baseline 到 workflow-first 自动化的阶段性升级。  
- 实现 workflow 检查、模型匹配、映射建议与自动 patch 的小闭环，降低手工对齐 node id 的成本。  
- 采用“baseline-first + validation-oriented”推进策略，为后续 LoRA / ControlNet / UE5 验证预留扩展路径。  

## 面试可讲点（简版）

- 为什么不是“直接调模型出图”：重点在流程工程化、可复现、可迭代。  
- 为什么先 baseline：先保证可控小闭环，再逐步扩展复杂能力。  
- LoRA/ControlNet 当前状态：接口准备完成，处于实验准备阶段，不夸大为全链路已落地。  
- UE5 当前状态：已规划验证维度与检查项，后续做下游可用性验证。  
