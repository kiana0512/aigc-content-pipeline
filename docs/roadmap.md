# Roadmap

## 项目定位

本项目面向游戏资产生成，目标是构建可复用、可追踪、可扩展的 AIGC 工作流，重点场景：

- 角色概念图
- UI icon
- 风格化概念图
- 可控生成与后续资产可用性验证

---

## 阶段 1：工程骨架

目标：

- 完成仓库结构与基础文档
- 建立配置、脚本、模块、测试的最小闭环

---

## 阶段 2：基线工作流接入

目标：

- 建立 UI icon / character concept 基线
- 接入 ComfyUI API workflow patch
- 支持批量任务与结果记录

---

## 阶段 3：数据与提示词资产化

目标：

- 组织小规模图文数据
- 建立可复用 prompt 模板与 metadata
- 为后续 LoRA 实验做准备

---

## 阶段 4：可控生成扩展

目标：

- 引入结构条件与预处理
- 对比有无控制条件下的质量与稳定性

---

## 阶段 5：轻量 LoRA 实验

目标：

- 小样本风格适配探索
- 建立最小训练-验证-记录闭环

---

## 阶段 6：评估与归档

目标：

- 让输出可比较、可复盘
- 支持参数/提示词迭代决策

---

## 阶段 7：UE5 下游验证（后续）

目标：

- 验证生成资产在 UE5 场景中的可用性
- 输出下游限制与优化方向

---

## Current Priority（当前优先级）

1. replace placeholder workflows with real ComfyUI API exports  
2. align real node ids in node mapping YAML files  
3. run first SDXL baseline rounds for UI icons and character concepts  
4. record baseline prompts, seeds, samplers, schedulers, and image sizes  
5. start first controlled baseline comparison and prompt iteration  
