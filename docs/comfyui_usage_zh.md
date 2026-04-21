# ComfyUI 使用指南（中文）

本文档面向 `game-aigc-asset-workflow` 仓库使用者，目标是帮助你把仓库从“工程准备态”顺利推进到“真实 ComfyUI workflow 对接态”。

## B1. ComfyUI 的定位

ComfyUI 是一个**节点式生成工作流平台**，不是单一“文生图”工具。  
它可以承载多类生成链路，例如：

- 图片生成与编辑
- 视频相关节点链
- 音频条件输入节点
- 3D / API / 插件类节点

本项目当前主线依然是**图片 baseline**，重点是游戏资产方向的 UI icon 与角色概念图。

## B2. 当前仓库与 ComfyUI 的关系

本仓库不是 ComfyUI 本体，而是“游戏 AIGC 资产生产流实验仓库”。  
当前通过以下机制与 ComfyUI 对接：

- workflow JSON（ComfyUI API 导出）
- node mapping（节点注入映射）
- `patch_workflow`（批量注入生成 patched workflow）
- config（模型目录、family、参数、策略）

当前主线任务：

- SDXL baseline
- UI icon baseline
- character concept baseline

## B3. ComfyUI 常见模型目录说明

下面按“目录用途 + 游戏资产用途 + 当前状态”说明。

### 主线必需 / 高频常用

1. `checkpoints`
- 用途：checkpoint 家族底模（如 SDXL 常见加载方式）
- 游戏资产用途：baseline 图像生成
- 当前状态：主线已接入

2. `diffusion_models`
- 用途：split model 家族的 diffusion 主体
- 游戏资产用途：为 Qwen/FLUX 类路径预留
- 当前状态：兼容预留 + 配置表达 + 校验支持

3. `vae`
- 用途：latent 与像素空间转换
- 游戏资产用途：基础生成链路
- 当前状态：主线建议目录

4. `text_encoders`
- 用途：split model 文本编码组件
- 游戏资产用途：复杂模型家族 prompt 编码
- 当前状态：兼容预留 + 校验支持

5. `clip_vision`
- 用途：图像参考编码
- 游戏资产用途：风格/参考图条件
- 当前状态：扩展兼容

6. `loras`
- 用途：轻量风格/角色适配
- 游戏资产用途：风格一致性增量训练/加载
- 当前状态：接口预留，非完整平台

7. `controlnet`
- 用途：结构可控条件
- 游戏资产用途：轮廓/姿态/布局可控
- 当前状态：接口预留，非完整平台

8. `embeddings`
- 用途：文本反演类 embedding token
- 游戏资产用途：风格或语义补强
- 当前状态：兼容预留

9. `upscale_models`
- 用途：像素空间放大/增强
- 游戏资产用途：产物清晰度提升
- 当前状态：扩展兼容

### 常用扩展

1. `style_models`
- 用途：风格模型链路
- 游戏资产用途：跨批次风格稳定
- 当前状态：扩展兼容

2. `latent_upscale_models`
- 用途：latent 空间放大
- 游戏资产用途：保结构的放大链路
- 当前状态：扩展兼容

3. `photomaker`
- 用途：身份/参考一致性相关链路
- 游戏资产用途：角色一致性探索
- 当前状态：扩展兼容

4. `gligen`
- 用途：布局/区域约束类条件
- 游戏资产用途：UI 元素位置约束探索
- 当前状态：扩展兼容

5. `hypernetworks`
- 用途：额外风格适配组件
- 游戏资产用途：风格强化
- 当前状态：扩展兼容

6. `audio_encoders`
- 用途：音频条件编码
- 游戏资产用途：音频驱动媒体链路前置准备
- 当前状态：扩展兼容

### 高级可选

1. `diffusers`
2. `vae_approx`
3. `classifiers`
4. `model_patches`
5. `download_model_base`

这些目录当前以“高级可选”表达，不作为当前主线落地目标。

## B4. checkpoints 与 diffusion_models 的区别

### classic checkpoint family（项目抽象）
- 常见于 SDXL 基线路径
- 典型依赖：`checkpoints`（通常配合 `vae`）
- 特点：路径直观，适合先跑通 baseline

### split model family（项目抽象）
- 常见于部分新模型家族（如 Qwen/FLUX 思路）
- 典型依赖：`diffusion_models + text_encoders + vae`
- 特点：组件拆分，更灵活但配置要求更严格

`text_encoders` 在 split family 中很关键：没有它通常无法稳定完成 prompt 编码链路。

## B5. 当前项目支持的工作模式

1. `manifest`
- 用途：生成运行清单，不执行 ComfyUI
- 输入：config + prompt_pack
- 输出：manifest JSON
- 适用：实验准备、参数审查
- 限制：不 patch workflow

2. `patch_workflow`
- 用途：按 node mapping 注入真实 API workflow
- 输入：config + prompt_pack + workflow JSON + node map
- 输出：patched workflow JSON 批次文件
- 适用：真实对接前的核心模式
- 限制：必须是 API workflow JSON，placeholder/UI JSON 会失败

3. `submit`（实验性）
- 用途：把 patched prompt 提交到 ComfyUI HTTP API
- 输入：同 patch_workflow + base_url
- 输出：提交响应日志
- 适用：联调 smoke test
- 限制：实验性，不是生产调度系统

## B6. 如何与真实 ComfyUI workflow 对接

1. 在 ComfyUI UI 里搭好真实 workflow。
2. 用 **File -> Export (API)** 导出 API workflow JSON。
3. 不要使用 UI workflow JSON（通常带 `nodes` 列表）。
4. 用导出的 API JSON 覆盖仓库对应 placeholder 文件。
5. 按真实节点 id 修改 `configs/comfyui_*_node_map.yaml`。
6. 执行 `patch_workflow` 生成 patched workflow JSON。
7. 用 patched JSON 交给 ComfyUI（或通过 submit 模式实验性提交）。

## B7. 当前推荐使用流程（路线）

### 路线 1：SDXL baseline（当前主线）
1. 先使用 `classic_checkpoint` family。
2. 跑通 UI icon / character concept baseline。
3. 验证稳定后再进入扩展能力。

### 路线 2：split model baseline（Qwen / FLUX 思路）
1. 把 `workflow_model_family` 设为 `split_model`。
2. 明确声明 `diffusion_models/text_encoders/vae`。
3. 当前仓库提供兼容层与校验，不是自动全适配。

### 路线 3：后续扩展
顺序建议：
1. LoRA
2. ControlNet
3. 风格参考与一致性链路
4. 放大后处理
5. 视频与音频驱动链路
6. API/3D 节点链路

## B8. 参数怎么选（结合游戏资产生产流）

1. `workflow_model_family` 怎么选
- SDXL baseline：`classic_checkpoint`
- 新拆分家族探索：`split_model`
- 仅条件增强：`conditioning`
- 后处理主导：`postprocess`
- 媒体扩展探索：`media_extension`

2. `comfyui_models` 目录声明怎么选
- baseline 阶段先保证 required/recommended
- optional 逐步补齐，不要一次堆满

3. checkpoints vs diffusion_models 怎么选
- 优先 checkpoint 跑通主线
- 确有模型家族需求再切 split 模式

4. prompt 模板怎么选
- UI icon 用 `prompts/ui_icons/*`
- character concept 用 `prompts/character_concepts/*`
- 先固定模板形成可比较基线

5. width / height 怎么选
- UI icon：先 `1024x1024`
- concept：先与训练/基线一致尺寸，避免变量过多

6. steps 怎么选
- baseline 先 25-35 区间稳定化
- 以可重复性和成本平衡为主

7. cfg / guidance scale 怎么选
- baseline 先 6-8 区间
- UI 可读性下降时先小幅调参再改 prompt

8. sampler / scheduler 怎么选
- 先固定一组可重复的 baseline 组合
- 不要在同轮实验同时改 sampler、scheduler、prompt

9. 什么时候先不开 LoRA / ControlNet
- baseline 尚未稳定时
- 输出指标和评估口径尚未固定时

10. 什么时候适合打开 LoRA
- 已明确风格目标
- baseline 可重复
- 数据和评估流程已基本定型

11. 什么时候适合做 ControlNet
- 结构可控性成为主要问题（轮廓、姿态、布局）
- baseline 风格稳定但结构漂移较大时

12. `strict_model_dir_check` 什么时候开
- 本地探索阶段：`false`（先提示）
- 团队协作/CI：`true`（缺 required 直接失败）

## B9. 当前实现边界与注意事项

- 只接受 API workflow JSON
- placeholder workflow 不能 patch
- LoRA / ControlNet 当前是接口预留
- submit 模式是实验性
- 当前不是完整支持所有模型家族的平台
- 当前不是完整视频平台
- 当前不是 UE5 自动化平台

## B10. 推荐实践与常见错误

推荐实践：

1. 从 baseline 小闭环开始
2. 每轮只改少量变量
3. 先稳定，再扩展

常见错误：

1. 把 UI workflow JSON 当 API JSON
2. 混用不兼容模型家族（如 SDXL + SD1.5 ControlNet）
3. baseline 未跑通就叠加 LoRA/ControlNet
4. 没有固定评估口径就频繁换参数
5. 一次性堆太多模型目录和插件链路

## B11. 最小实操清单

下面这份清单面向“今天就要开始动手、明天进入正式资产流程”的当前阶段，按顺序执行即可。

1. 在 ComfyUI 里先搭一个最小 baseline 图，至少包含以下节点：
   - CheckpointLoaderSimple
   - CLIPTextEncode（positive）
   - CLIPTextEncode（negative）
   - EmptyLatentImage
   - KSampler
   - VAEDecode
   - SaveImage
2. 用 SDXL base 先跑通至少 1 张图（UI icon 或 character concept 任一即可）。
3. 在 ComfyUI 使用 `File -> Export (API)` 导出真实 API workflow JSON。
4. 用导出的 JSON 覆盖仓库中对应的 placeholder workflow 文件（`workflows/comfyui/*.json`）。
5. 打开对应 `configs/comfyui_*_node_map.yaml`，把真实节点 id 填进去，并核对 input key。
6. 执行 `patch_workflow` 模式，为 prompt pack 生成 patched workflow JSON 批次文件。
7. 固定并记录本轮关键参数：
   - prompt
   - negative prompt
   - seed
   - sampler
   - scheduler
   - image size
8. 把本轮实验信息写入 `docs/experiment_log.md`（至少记录配置、参数、输出路径和主观观察）。
9. baseline 稳定前，不要急着叠加 LoRA / ControlNet。
10. 第一轮只追求“小闭环跑通”，不要追求最强画质或最复杂链路。

简短目标提示：今天先完成 baseline 小闭环；明天再正式进入资产生成流程和第一轮参数/提示词迭代。
