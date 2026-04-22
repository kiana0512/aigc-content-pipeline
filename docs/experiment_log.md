# Experiment Log（实验记录）

用于记录项目推进、参数选择、工作流变化、问题与结论。  
建议每次关键改动都留下最小可复盘记录。

---

## 2026-04-20

### 任务：项目初始化

- 完成仓库初始化与目录骨架
- 建立 README / roadmap / experiment_log
- 明确主线为游戏资产生成实验流程

---

## 2026-04-21

### 任务：从 scaffold 推进到 ComfyUI baseline integration preparation

- 新增 ComfyUI adapter（API workflow patch）
- 新增 node mapping YAML 机制（避免写死 node id）
- `run_batch_generation.py` 支持 `manifest / patch_workflow / submit(实验性)`
- 配置补充 ComfyUI 字段与 LoRA/ControlNet 预留接口
- 新增本地测试：patch 逻辑、placeholder 检测、mapping 校验

---

## 2026-04-22

### 任务：workflow-first v1 收口与落地增强

#### 关键变更

- 新增 workflow-first 检查链路：
  - `workflow_inspector`
  - `model_resolver`
  - `mapping_suggester`
- 新增 `workflow_import_pipeline / prepare_workflow_import` 一键小闭环模式
- 统一 run 输出目录为 `results/runs/<run_name>/`
- 增加模型解析别名与路径覆盖：
  - `model_resolution_policy.aliases`
  - `model_resolution_policy.path_overrides`
- 增加低置信映射人工确认清单：
  - `mapping_manual_review.yaml`
- 固化 Qwen API workflow 为黄金测试样例：
  - `tests/fixtures/qwen_api_workflow.json`

#### 当前边界

- 仅支持真实 API workflow JSON
- placeholder / UI workflow JSON 明确拒绝
- LoRA / ControlNet 仍为接口预留
- submit 仍为实验性能力

#### 下一步

1. 用真实项目 workflow 替换占位文件  
2. 跑首轮 UI icon / concept 基线对比  
3. 固化参数与提示词记录模板  

---

## 记录模板（建议）

### 日期
YYYY-MM-DD

### 任务类型
例如：baseline、prompt 迭代、workflow patch、模型目录整理、评估记录

### 目标
这次改动/实验要验证什么？

### 输入
workflow、配置、prompt、参数、模型版本

### 操作
实际执行了什么命令/改动？

### 输出
生成了哪些文件、图像或报告？

### 观察
效果、问题、异常、风险

### 下一步
下一轮要做什么
