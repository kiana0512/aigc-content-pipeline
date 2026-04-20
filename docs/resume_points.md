# Resume Points

## Project Name Candidates

Recommended Chinese name:
- 游戏 AIGC 资产生成实验工作流

Recommended English name:
- Game AIGC Asset Generation Experimental Workflow
- Game-Oriented AIGC Asset Generation Workflow
- Controllable Game Asset Generation Workflow

---

## Core Keywords

- ComfyUI
- Stable Diffusion
- SDXL / SD3.5
- LoRA
- ControlNet
- IP-Adapter
- OpenCV
- PyTorch
- diffusers
- Prompt Engineering
- Image Preprocessing
- Data Preparation
- Workflow Reuse
- UE5 Validation

---

## Project Positioning

This project is positioned as a practical engineering workflow for game-oriented AIGC asset generation.

It focuses on:
- character concept generation
- UI icon generation
- stylized concept art generation
- controllable diffusion workflow design
- small-scale data preparation and lightweight fine-tuning
- downstream usability validation for UE5-related scenarios

---

## Resume Description (Chinese)

围绕游戏场景下的角色立绘、UI Icon 与概念设定图生成需求，搭建基于 ComfyUI 与 Stable Diffusion 的图像生成实验工作流，完成提示词模板、模型组合、参数预设、批量出图与结果归档流程设计。结合 LoRA、ControlNet、参考图驱动与 OpenCV 预处理方法，探索风格保持、构图约束、角色一致性与资产可复用能力；进一步设计小规模图文数据整理、训练测试与质量评估闭环，并结合 UE5 素材使用场景验证生成结果的可用性，沉淀可复用的 workflow 配置、prompt 模板与 AIGC 内容生产辅助方案。

---

## Resume Description (English)

Built an experimental AIGC workflow for game-oriented asset generation targeting character concepts, UI icons, and stylized concept art. Designed reusable prompt templates, parameter presets, batch generation pipelines, and result organization workflows based on ComfyUI and Stable Diffusion. Explored controllable generation with LoRA, ControlNet, reference-guided methods, and OpenCV-based preprocessing for style consistency, structural control, and asset reusability. Further organized small-scale image-text data preparation, experiment evaluation, and UE5-oriented usability validation to support practical game content production.

---

## Short Resume Version

Built a game-oriented AIGC asset generation workflow based on ComfyUI, Stable Diffusion, LoRA, and ControlNet, covering prompt engineering, OpenCV-based preprocessing, small-scale data preparation, controllable generation experiments, and UE5-oriented asset usability validation.

---

## Highlight Directions

### 1. Engineering Highlights
- built a reusable workflow instead of isolated image generation demos
- organized configs, prompts, scripts, workflows, and evaluation notes in a structured repository
- supported batch generation, output indexing, and experiment traceability
- emphasized practical iteration efficiency for game content production

### 2. Model / Algorithm Highlights
- explored diffusion-based image generation for game asset scenarios
- compared baseline generation with controllable generation strategies
- introduced LoRA for lightweight style adaptation
- introduced ControlNet and reference-guided methods for structural control
- used OpenCV preprocessing to generate controllable guidance signals

### 3. Data Highlights
- organized small-scale image-text data for generation and fine-tuning experiments
- designed prompt templates and metadata structures for reusable experiments
- supported caption cleanup, split preparation, and result comparison

### 4. Application Highlights
- focused on practical scenarios such as character concepts, UI icons, and stylized concept art
- evaluated outputs from style consistency, readability, and downstream usability perspectives
- connected generation results with UE5-side usage validation

---

## Interview Talking Points

### What problem does this project solve?
It aims to improve the controllability, reusability, and practical usability of diffusion-based image generation in game content production scenarios.

### Why is this project not just “using a model to generate images”?
Because the project emphasizes workflow construction, prompt reuse, configuration management, preprocessing, controllable generation, evaluation, and downstream validation, rather than isolated one-off demos.

### Why add OpenCV?
OpenCV is used to generate structural guidance signals such as edges, masks, or other preprocessing outputs, which can be connected to controllable generation workflows like ControlNet.

### Why add LoRA?
LoRA is used to explore lightweight style adaptation under limited data conditions, which is closer to real production constraints than full-scale retraining.

### Why add UE5 validation?
Because the usefulness of generated assets should be judged not only by visual quality, but also by whether they are usable in downstream game production scenarios.

---

## Possible Resume Bullet Points

### Version A
- 搭建面向游戏角色立绘、UI Icon 与概念设定图生成的 AIGC 实验工作流，基于 ComfyUI 与 Stable Diffusion 完成提示词模板、参数预设、批量出图与结果归档流程设计。
- 结合 LoRA、ControlNet、参考图驱动与 OpenCV 预处理方法，探索风格一致性、结构可控性与资产复用能力，支持小规模图文数据整理、训练测试与效果评估。
- 面向 UE5 素材使用场景，对生成结果从角色设定一致性、图标可读性与整体风格统一性等维度进行验证，沉淀可复用的 workflow 配置与 prompt 资产库。

### Version B
- 设计并实现游戏 AIGC 资产生成实验工作流，覆盖 Prompt Engineering、Diffusion 模型调用、OpenCV 结构预处理、LoRA 微调与 ControlNet 可控生成。
- 构建小规模图文数据整理与实验评估闭环，支持角色设定图、UI Icon 与风格化概念图生成任务的配置化管理与结果对比。
- 结合 UE5 下游使用需求，对生成内容的可读性、风格一致性与生产可用性进行验证，提升 AIGC 内容生产辅助效率。

### Version C
- 基于 ComfyUI、Stable Diffusion、LoRA 与 ControlNet 搭建游戏资产生成工作流，完成 prompt 模板化、参数配置化、结果记录化与流程可复用化。
- 利用 OpenCV 进行边缘/结构预处理，结合参考图驱动方法提升扩散生成的构图约束与风格控制能力。
- 面向游戏 UI 与概念设计场景开展小规模实验，整理可复用 workflow、prompt 模板及评估记录，用于后续项目展示与研究探索。

---

## What This Project Demonstrates

This project can demonstrate the following abilities on a resume:

- understanding of diffusion-based image generation workflows
- practical experience with ComfyUI and Stable Diffusion ecosystem
- ability to organize small-scale data and reusable prompt assets
- familiarity with LoRA and controllable generation methods
- ability to combine traditional CV preprocessing with generative workflows
- engineering awareness for documentation, reproducibility, and modularity
- application awareness for UE5-oriented downstream usage scenarios

---

## Future Strengthening Directions

To make the project stronger on a resume, future additions can include:
- more complete batch generation scripts
- clearer result indexing and comparison reports
- at least one runnable OpenCV + ControlNet demo chain
- one small LoRA fine-tuning record
- one UE5 validation case with screenshots
- one concise project summary PPT or project page