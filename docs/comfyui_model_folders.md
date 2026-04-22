# ComfyUI 模型目录说明

本文用于说明本项目里的 ComfyUI 模型目录分层与用途。

说明：`classic_checkpoint / split_model / conditioning / postprocess / media_extension`  
是项目内部兼容抽象，不是 ComfyUI 官方术语。

## 1. 分层定义

- 当前主线：当前阶段高频且直接相关目录
- 常用扩展：下一阶段常见扩展目录
- 高级可选：特定工作流或高级场景使用

## 2. 当前主线目录

### `checkpoints`
- 用途：checkpoint 一体模型（常见 SDXL）
- 游戏资产流价值：UI icon / concept 基线快速落地
- 当前状态：主线支持（已实现）

### `diffusion_models`
- 用途：split-model 家族中的扩散主干
- 游戏资产流价值：支持 Qwen/FLUX 等分体模型链路
- 当前状态：兼容支持（已实现目录表达 + 检查）

### `text_encoders`
- 用途：split-model 文本编码器
- 游戏资产流价值：分体模型提示词理解核心组件
- 当前状态：兼容支持（已实现目录表达 + 检查）

### `vae`
- 用途：latent 与像素空间转换
- 游戏资产流价值：checkpoint 与 split-model 都需要
- 当前状态：主线支持（已实现）

## 3. 常用扩展目录

### `loras`
- 用途：轻量风格/角色适配
- 当前状态：接口预留（默认关闭）

### `controlnet`
- 用途：结构控制
- 当前状态：接口预留（默认关闭）
- 注意：必须与底模架构匹配（如 SDXL ControlNet 不能乱配 SD1.5）

### `embeddings`
- 用途：文本反演向量
- 当前状态：兼容支持

### `clip_vision`
- 用途：图像条件编码（参考图/风格参考）
- 当前状态：兼容支持

### `style_models`
- 用途：风格控制链路
- 当前状态：兼容预留

### `upscale_models`
- 用途：像素空间放大
- 当前状态：兼容预留

### `latent_upscale_models`
- 用途：潜空间放大
- 当前状态：兼容预留

### `photomaker`
- 用途：身份/参考风格增强
- 当前状态：兼容预留

### `gligen`
- 用途：区域/布局类条件控制
- 当前状态：兼容预留

### `hypernetworks`
- 用途：附加风格网络
- 当前状态：兼容预留

### `audio_encoders`
- 用途：音频条件工作流
- 当前状态：兼容预留

## 4. 高级可选目录

### `diffusers`
- 用途：工具链/布局相关目录
- 当前状态：高级可选

### `vae_approx`
- 用途：近似 VAE 组件
- 当前状态：高级可选

### `classifiers`
- 用途：特定条件引导或历史链路
- 当前状态：高级可选

### `model_patches`
- 用途：模型 patch/覆写
- 当前状态：高级可选

### `download_model_base`
- 用途：下载基础目录
- 当前状态：高级可选

## 5. 任务-目录矩阵

| 任务 | 典型 family（项目抽象） | 核心目录 | 扩展目录 |
| --- | --- | --- | --- |
| SDXL baseline 图片生成 | `classic_checkpoint` | `checkpoints`, `vae` | `loras`, `controlnet`, `embeddings` |
| split-model baseline（Qwen/FLUX） | `split_model` | `diffusion_models`, `text_encoders`, `vae` | `clip_vision`, `loras`, `controlnet` |
| 风格参考/条件控制 | `conditioning` | 依赖基础 family | `clip_vision`, `style_models`, `photomaker`, `gligen`, `hypernetworks` |
| 放大与后处理 | `postprocess` | 依赖基础 family | `upscale_models`, `latent_upscale_models` |
| 音视频扩展准备 | `media_extension` | 依赖基础 family | `audio_encoders` + 相关视频模型目录 |

## 6. 分层推进建议

1. 先跑通 SDXL baseline（当前主线）
2. 再引入 split-model baseline
3. 再做 LoRA / ControlNet
4. 最后扩展放大、音视频、复杂条件链
