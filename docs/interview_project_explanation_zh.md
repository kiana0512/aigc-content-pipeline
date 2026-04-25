# 游戏 AIGC 资产生成自动化工作流：面试项目深度说明（可口述版）

## 1. 项目一句话介绍（面试开场）

### 1.1 10 秒版
我做的是一个基于 ComfyUI API workflow 的游戏资产批量生成工具链，把手动点图变成了可配置、可批量、可复盘的流程。

### 1.2 30 秒版
这个项目的核心是：用 `scripts/run_batch_generation.py` 把 ComfyUI API workflow 和 CSV prompt pack 串起来。  
流程是 `scaffold_workflow -> workflow_import_pipeline -> submit`：先接入 workflow，再按 CSV 每行生成独立 patched workflow，最后批量提交到 ComfyUI `/prompt`。  
它主要服务游戏前期资产探索，比如角色概念图、场景参考图、UI icon，并且每轮都有 `run_manifest.json`、`patch_report.md`、`comfyui_submit_results.json`，便于复盘。

### 1.3 2 分钟版
这个仓库不是 ComfyUI 本体，而是 ComfyUI 的外部调度层。  
我先在 ComfyUI 里把单图流程跑通，再导出 API JSON，放进仓库进行工程化：  

1. 用 `scaffold_workflow` 自动生成 config、node map、默认 prompt pack；  
2. 用 prompt pack（CSV）管理“要生成什么”；  
3. 用 workflow JSON 管理“怎么生成”；  
4. 用 `workflow_import_pipeline` 把每行任务变成独立 patched workflow；  
5. 用 `submit` 批量提交到 ComfyUI；  
6. 用结果文件记录每张图的来源与参数。  

这样我不是在“凭感觉调图”，而是在做可比较、可追溯的生成实验。  
当前已实现的是 2D 资产生成自动化；3D/UE5 部分是下游衔接和扩展规划，不会夸大成完整 3D 生成系统。

---

## 2. 项目背景与痛点（先讲为什么做）

游戏研发前期常见问题是：要快速探索很多视觉方向，但“手动点图”很难管理。

具体痛点：

- 概念图/UI icon/道具草图迭代快，手工重复操作耗时。
- 同一批实验参数分散在节点图里，过几天就复现不出来。
- 每接一个新 workflow，都要手动找 node id、写映射、写 CSV，容易错。
- 多轮结果没有统一记录，难回答“这张图为什么更好”。
- 如果后面要进入 UE5/3D流程，需要更规范的命名、归档、筛选。

本项目就是针对这组痛点：把“单次出图”变成“有输入、有输出、有证据链的批量流程”。

---

## 3. 从 ComfyUI 模板到批量出图：完整流程

这一章按真实仓库和真实命令来讲，面试官通常最关心这一段。

### 3.1 在 ComfyUI 中手动搭建并验证 workflow

**问题是什么**  
如果一开始就做自动化，可能把一个本来就不稳定的 workflow 自动化，最后问题更难查。

**为什么这样设计**  
先保证“单张图可跑通”，再做“批量稳定化”。

**我具体怎么做**

1. 在 ComfyUI 里选模型、连节点、写 prompt、调采样参数。  
2. 跑一张图，确认：
   - 模型能加载；
   - 节点连接无报错；
   - 基本质量可用。
3. 常见起点是：
   - Z-Image Turbo（快，适合 smoke test）；
   - Qwen Illustration LoRA（风格化角色探索）。

**面试时怎么说**  
“我不是一上来就写脚本，而是先把 ComfyUI 里的最小可用流程跑通，确认这条 workflow 值得工程化。”

### 3.2 Export(API) 导出真实 API workflow JSON

**问题是什么**  
ComfyUI 有 UI workflow 和 API workflow，两者格式不同。

**为什么这样设计**  
本仓库只接受能直接提交到 `/prompt` 的 API 格式。

**我具体怎么做**

1. 在 ComfyUI 里用 Export(API) 导出。  
2. 放到 `workflows/comfyui/`。
3. 当前仓库真实文件：
   - `workflows/comfyui/image_z_image_turbo_api.json`
   - `workflows/comfyui/qwen_image_illustration_lora_api.json`

**成功怎么验证**  
`workflow_inspector` 能识别为 `comfyui_api_prompt` 或 `comfyui_api_prompt_wrapped`，不是 `nodes` 列表。

**失败怎么排查**  
如果报 UI 格式错误，重新在 ComfyUI 导出 API JSON。

### 3.3 使用 `scaffold_workflow` 自动生成配套文件

**问题是什么**  
每接一个新 workflow 都手写 YAML/node_map/CSV，重复且易错。

**为什么这样设计**  
把接入流程标准化，减少人工失误。

**命令**

```bash
python scripts/run_batch_generation.py --mode scaffold_workflow --workflow-json workflows/comfyui/my_new_workflow_api.json --slug my_new_workflow
```

**自动生成（真实行为）**

- `configs/<slug>_api.yaml`
- `configs/node_maps/<slug>_node_map.yaml`
- `examples/prompt_packs/<slug>_default_from_workflow.csv`
- `examples/prompt_packs/<slug>_prompt_pack.csv`
- `results/runs/scaffold_<slug>/scaffold_report.md`
- `results/runs/scaffold_<slug>/next_commands.md`

**每个文件在流程里的作用**

- `config YAML`：定义 workflow 路径、ComfyUI 地址、默认参数、默认 prompt pack。
- `node_map YAML`：定义业务字段写入哪个节点输入。
- `default_from_workflow.csv`：复现导入 workflow 的默认图。
- `prompt_pack.csv`：日常批量任务表。
- `scaffold_report`：记录识别到的节点、fallback、需人工确认项。

**成功怎么验证**

- 上述文件都已生成；
- `scaffold_report.md` 有 next commands；
- `default_from_workflow.csv` 的正负 prompt 与 workflow 默认值一致或有可解释 fallback。

**失败怎么排查**

- 报 UI workflow：重新导出 API 格式；
- 报文件已存在：用 `--force` 覆盖（脚本会备份）。

**面试时怎么说**  
“我把接入新 workflow 这件事工具化了，不是每次都手工抄节点 id。”

### 3.4 编辑 prompt pack，定义要批量生成什么

**问题是什么**  
如果任务内容写死在 workflow JSON，批量实验很难管理。

**为什么这样设计**  
把“生成内容”从“生成结构”中解耦。

**CSV 推荐字段**

`id,subject,style,attributes,positive_prompt,negative_prompt,filename_prefix`

**字段含义**

- `positive_prompt`：主体与风格内容。
- `negative_prompt`：减少低质、水印、畸形等问题。
- `filename_prefix`：结果命名，方便归档。
- `subject/style/attributes`：用于分组、筛选和后续复盘。

**关键规则（真实实现）**

- workflow JSON 的 prompt 是模板默认值；
- 只要传了 prompt pack，运行优先用 CSV；
- `workflow_runner.py` 支持 alias 归一化（`prompt`、`positive_prompt_text` 等）。

### 3.5 `workflow_import_pipeline`：每行 CSV -> 一个 patched workflow

**命令示例**

```bash
python scripts/run_batch_generation.py --config configs/z_image_turbo_api.yaml --prompt-pack examples/prompt_packs/z_image_turbo_prompt_pack.csv --mode workflow_import_pipeline --run-name z_image_turbo_round1
```

**它具体做了什么（步骤化）**

1. 读 config（workflow 路径、node map、参数默认值）。  
2. 读 CSV（多行任务）。  
3. 做字段归一化（含 prompt alias）。  
4. 构建 `run_manifest.json`（每个 item 的最终参数来源）。  
5. 依据 node_map patch workflow：
   - prompt -> `CLIPTextEncode.inputs.text`
   - steps/cfg/seed -> `KSampler.inputs.*`
   - width/height/batch_size -> latent 节点
   - filename_prefix -> `SaveImage`
6. 生成 per-item 文件和报告。

**输出文件**

- `results/runs/<run_name>/run_manifest.json`
- `results/runs/<run_name>/patched_workflows/item_0001_patched_workflow.json`
- `results/runs/<run_name>/patch_reports/item_0001_patch_report.json`
- `results/runs/<run_name>/patch_report.md`

### 3.6 `submit`：批量提交到 ComfyUI 出图

**命令示例**

```bash
python scripts/run_batch_generation.py --config configs/z_image_turbo_api.yaml --prompt-pack examples/prompt_packs/z_image_turbo_prompt_pack.csv --mode submit --run-name z_image_turbo_round1
```

**它具体做了什么**

1. 优先读取 `results/runs/<run_name>/patched_workflows/item_*_patched_workflow.json`；  
2. 逐条 POST 到 ComfyUI `/prompt`；  
3. 记录每条提交的 `prompt_id` 和状态。

**输出**

- `results/runs/<run_name>/comfyui_submit_results.json`

**必须条件**

- ComfyUI 在线可访问；
- 当前配置默认 `http://127.0.0.1:8000`（见 `configs/*.yaml`）。

### 3.7 如何确认本轮跑图是正确的（检查清单）

1. 看 `run_manifest.json`  
   - 每个 item 的 `positive_prompt`、`negative_prompt`、`seed`、`filename_prefix` 是否符合预期。
2. 看 `patched_workflows/item_xxxx_patched_workflow.json`  
   - 目标节点文本/参数是否真的被替换。
3. 看 `patch_report.md`  
   - 字段来源是否来自 `prompt_pack` 或 `config`，而不是意外 fallback。
4. 看 `comfyui_submit_results.json`  
   - `total_items`、`submitted_items`、`failed_items`、每条 `prompt_id`。
5. 看 ComfyUI 生成面板  
   - 是否出现对应 `filename_prefix` 的图。

---

## 4. 真实案例：用 Z-Image Turbo 做一轮角色 + 场景批量生成

这一章给你一个可以在面试里从头讲到尾的贯穿案例，避免只讲概念。

### 4.1 prompt pack 长什么样

先准备两条任务：一条角色概念图，一条场景概念图。

CSV 片段（可口述）：

```csv
id,subject,style,attributes,positive_prompt,negative_prompt,filename_prefix
1,z_turbo_character,concept,portrait,"female fantasy ranger, short silver hair, leather armor, standing in forest ruins, full body character concept art, clean silhouette, cinematic lighting, high quality game art","low quality, blurry, bad anatomy, distorted face, extra fingers, watermark",character
2,z_turbo_environment,concept,environment,"ancient ruin environment, glowing crystal gate, overgrown forest, fantasy RPG level design, wide shot, atmospheric lighting, high detail concept art","low quality, blurry, messy composition, text, watermark",environment
```

你可以放在 `examples/prompt_packs/z_image_turbo_prompt_pack.csv`（或同结构新文件）。

### 4.2 跑 pipeline

```bash
python scripts/run_batch_generation.py --config configs/z_image_turbo_api.yaml --prompt-pack examples/prompt_packs/z_image_turbo_prompt_pack.csv --mode workflow_import_pipeline --run-name z_image_turbo_case_round1
```

### 4.3 pipeline 生成了什么

会得到：

- `results/runs/z_image_turbo_case_round1/run_manifest.json`
- `results/runs/z_image_turbo_case_round1/patched_workflows/item_0001_patched_workflow.json`
- `results/runs/z_image_turbo_case_round1/patched_workflows/item_0002_patched_workflow.json`
- `results/runs/z_image_turbo_case_round1/patch_report.md`

解释要点：

- `item_0001` 对应角色 prompt；
- `item_0002` 对应场景 prompt；
- 两个 item 的 `filename_prefix` 不同（`character` / `environment`），所以后续 ComfyUI 输出文件名前缀也会不同。

### 4.4 跑 submit

```bash
python scripts/run_batch_generation.py --config configs/z_image_turbo_api.yaml --prompt-pack examples/prompt_packs/z_image_turbo_prompt_pack.csv --mode submit --run-name z_image_turbo_case_round1
```

### 4.5 submit 后怎么看结果

- ComfyUI Generated 面板应看到 `character_*.png` 和 `environment_*.png`。
- `comfyui_submit_results.json` 应看到 `total_items=2`、`submitted_items=2`。
- 如果只提交一条，优先怀疑 batch submit 链路或 run 目录不完整。
- 如果 filename_prefix 不对，先看 patched workflow 的 SaveImage 节点是否 patch 正确。
- 如果图内容不对，先看 patched workflow 的 `CLIPTextEncode.inputs.text`。

### 4.6 面试时怎么讲这个案例（1 分钟）

“我可以用 Z-Image Turbo 举个具体例子：我在 prompt pack 里放两行任务，一行是角色概念图，一行是场景概念图。先跑 `workflow_import_pipeline`，它会生成 `run_manifest` 和两个 per-item patched workflow。`item_0001` 是角色，`item_0002` 是场景，而且我给了不同 `filename_prefix`，所以输出文件也能自动分组。然后我跑 `submit`，脚本会把两个 patched workflow 都发给 ComfyUI `/prompt`。最后我看 `comfyui_submit_results.json`，确认总提交数是 2，再到 ComfyUI 里看 `character_*.png` 和 `environment_*.png`。这样我能完整证明：不是只会手工点图，而是能做一轮可追踪的批量生成。”

---

## 5. 当前目录结构和每个目录在流程中的位置

### 4.1 目录总览（真实）

- `configs/`
- `configs/node_maps/`
- `workflows/comfyui/`
- `examples/prompt_packs/`
- `scripts/run_batch_generation.py`
- `src/generation/`
- `tests/`
- `results/runs/`

### 4.2 按“输入 -> 处理 -> 输出”解释

1. **输入层**
   - `workflows/comfyui/*.json`：来自 ComfyUI Export(API)
   - `examples/prompt_packs/*.csv`：你要批量生成的任务
   - `configs/*.yaml`：运行配置
   - `configs/node_maps/*.yaml`：字段映射规则

2. **处理层**
   - `scripts/run_batch_generation.py` 调用 `src/generation/*`
   - 核心步骤：归一化 -> patch -> submit

3. **输出层**
   - `results/runs/<run_name>/...`（manifest、patched workflows、patch report、submit result）

### 4.3 当前两个实际 workflow

- Z-Image Turbo：
  - `workflows/comfyui/image_z_image_turbo_api.json`
  - `configs/z_image_turbo_api.yaml`
- Qwen LoRA：
  - `workflows/comfyui/qwen_image_illustration_lora_api.json`
  - `configs/qwen_image_illustration_lora_api.yaml`

---

## 6. 各模块之间如何配合（数据流视角）

### 5.1 模块职责

1. `workflow JSON`  
   - 输入：ComfyUI Export(API)  
   - 作用：定义节点拓扑和模型连接  
   - 输出：被 scaffold/pipeline 读取

2. `config YAML`  
   - 输入：用户配置  
   - 作用：指定 workflow、node map、ComfyUI 地址、默认参数  
   - 输出：给 `workflow_runner` 构建 items

3. `node_map YAML`  
   - 输入：scaffold 生成 + 人工确认  
   - 作用：把业务字段映射到具体节点 input  
   - 输出：给 `comfyui_adapter` patch 用

4. `prompt pack CSV`  
   - 输入：用户批量任务  
   - 作用：定义“生成什么”  
   - 输出：每行变成一个 item

5. `workflow_runner.py`  
   - 作用：读 config/CSV，做 alias 归一化，生成 manifest

6. `comfyui_adapter.py`  
   - 作用：按 node map patch workflow，产出 per-item JSON

7. `comfyui_client.py`  
   - 作用：将 patched workflow 提交到 ComfyUI `/prompt`

8. `results/runs`  
   - 作用：保存整轮证据链，支撑复盘和排错

### 5.2 完整数据流

```text
ComfyUI Export(API)
-> workflows/comfyui/*.json
-> scaffold_workflow
-> configs + node_maps + prompt_packs
-> workflow_import_pipeline
-> patched_workflows
-> submit
-> ComfyUI 生成图片
-> results/runs 保存记录
```

---

## 7. Prompt 多起来以后怎么调试和迭代

### 6.1 为什么 prompt pack 要拆字段

拆分字段不是为了“好看”，是为了能做实验管理：

- `subject`：主体是什么
- `style`：风格方向
- `attributes`：补充细节
- `positive_prompt`：最终主描述
- `negative_prompt`：排除项
- `filename_prefix`：结果标识

这样后面筛图时，你能按列过滤，而不是在一长段文本里猜。

### 6.2 推荐 prompt 模板（可直接用）

#### 角色概念图模板
主体 + 服装 + 姿态 + 风格 + 构图 + 光照 + 质量词  
示例：  
`female fantasy ranger, short silver hair, leather armor, standing in forest ruins, full body character concept art, clean silhouette, cinematic lighting, high quality game art`

#### 场景概念图模板
地点 + 主题 + 时代/风格 + 氛围 + 镜头 + 光照 + 质量词  
示例：  
`ancient ruin environment, glowing crystal gate, overgrown forest, fantasy RPG level design, wide shot, atmospheric lighting, high detail concept art`

#### UI icon 模板
物体 + 图标风格 + 背景 + 轮廓 + 可读性  
示例：  
`magic potion bottle icon, fantasy game UI, centered, clean silhouette, transparent background style, high readability`

#### 材质/贴图参考模板
材质类型 + 纹理属性 + 视角 + seamless + 用途  
示例：  
`stylized stone floor texture, hand-painted fantasy style, seamless tileable material, top-down orthographic view, game environment texture reference`

### 6.3 prompt 迭代方法（实操）

1. 固定 seed，只改 prompt。  
2. 固定 prompt，只改参数（cfg/steps/sampler）。  
3. 每次只改一个变量。  
4. 每轮设置独立 `run-name`。  
5. 用 `filename_prefix` 标记实验目标。  
6. 失败样本保留，不要删；失败样本是最好的调参证据。

### 6.4 A/B 对比命名建议

- `round1_character_style_a`
- `round1_character_style_b`
- `round2_cfg35`
- `round2_cfg50`
- `qwen_lora_strength07`
- `qwen_lora_strength10`

对比时按 `results/runs/<run_name>/run_manifest.json` + 实际图片一起看。

### 6.5 面试表达（可口述）

“我不是靠感觉改 prompt。我会把 prompt 当实验变量，和 seed、cfg、sampler 一起记录，用 run-name 和 manifest 做 A/B 复盘。”

---

## 8. 关键参数怎么影响生成结果（通俗版）

| 参数 | 改大可能怎样 | 改小可能怎样 | 面试怎么解释 |
|---|---|---|---|
| `seed` | 结果换随机样式，多样性增加 | 固定时利于对比 | seed 是随机起点；固定 seed 才能做公平 A/B |
| `steps` | 细节可能更完整，但更慢，收益会递减 | 更快，但细节可能不够 | steps 是采样迭代次数，不是越大越好 |
| `cfg` | 更“听 prompt”，但可能僵硬或 artifact | 更自然但可能偏题 | cfg 是“服从提示词”和“自然感”之间的平衡 |
| `sampler_name` | 不同采样器会改变细节风格和稳定性 | 同左 | 我把 sampler 配置化，按场景做对比而不是拍脑袋选 |
| `scheduler` | 影响采样路径与收敛特性 | 同左 | scheduler 是采样节奏，常和 sampler 配套看 |
| `width/height` | 更大分辨率更清晰但更耗显存 | 更快但细节可能损失 | 尺寸先按用途定：icon 常 1:1，角色/场景按构图需求 |
| `batch_size` | 一次更多候选图，但显存压力更大 | 显存更稳，吞吐下降 | batch_size 是吞吐和资源之间的取舍 |
| `denoise` | 文生图一般保持 1；图生图时大值改动更强 | 图生图时小值更保留原图 | 当前文生图流程通常固定 1 |
| `lora_strength_model` | 风格更强，过高可能压制基模 | 风格更弱 | LoRA 强度控制“风格注入力度”，要在可识别和不过拟合间找平衡 |

补充：  
在当前仓库里，Z-Image Turbo 配置步数相对低（快测），Qwen LoRA 步数更高（更重视风格细节），这正好是“模型/任务不同，参数策略不同”的实际例子。

---

## 9. 生成结果质量评估：怎么判断图能不能用于游戏资产流程

### 8.1 为什么需要质量评估

批量生成不等于有效生成。  
游戏场景里，一张图“好看”还不够，还要看是否能被美术/策划/技术继续使用。

### 8.2 游戏资产质量评估维度

| 评估维度 | 看什么 | 常见问题 | 应对方式 |
|---|---|---|---|
| Prompt 对齐度 | 主体、服装、场景、道具是否符合描述 | 主体偏题、关键词被忽略 | 主体词前置，拆分描述，减少冲突词 |
| 构图可用性 | 是否适合裁剪和资产用途 | 主体太小、背景太乱、被裁切 | 增加 `centered composition`、`close-up`、`clean silhouette` |
| 风格一致性 | 多图是否像同一项目 | 写实/二次元/油画混杂 | 固定 style 模板、LoRA、sampler、seed 范围 |
| 结构与形体质量 | 人体/手部/脸/武器结构 | 手崩、脸崩、装备结构错乱 | negative prompt、提高 steps、换模型，后续接 ControlNet |
| 细节清晰度 | 边缘、纹理、可读性 | 模糊、材质不清 | 调尺寸/steps/cfg，必要时后处理 |
| 资产可落地性 | 能否作为 icon/概念/参考 | 好看但不可拆分、不可复用 | 按资产类型写模板，不同用途分组生成 |
| UE5/3D 参考价值 | 视角、结构、材质信息是否充分 | 视角不明确、结构不完整 | 增加 `front view/side view/orthographic/material reference` |

### 8.3 当前项目已实现 vs 未实现

**已实现（可演示）**

- 通过 `filename_prefix` + `run_manifest.json` 追踪每张图来源；
- 可回看 prompt、seed、workflow、参数；
- 可按 prompt pack 做 A/B 对比；
- 可按 run 维度比较不同实验轮次。

**尚未实现（不要夸大）**

- 自动 CLIP score；
- 自动美学评分；
- 自动人体/手部检测；
- 自动 UE5 可用性打分；
- 自动筛选排序系统。

**后续可补**

- 清晰度检测；
- prompt-image 对齐评分；
- aesthetic score；
- 人体/脸/手异常检测；
- 人工反馈 CSV；
- 形成“生成 -> 筛选 -> 复用 -> 再生成”闭环。

### 8.4 面试话术

“我不会把质量评估说成已经全自动。我现在先把可追踪性做好：每张图都能回到 prompt、seed、workflow、参数。这样人工筛图时能解释原因。后续我会把人工反馈结构化，再加自动评分做半自动质检。”

---

## 10. 质量评估如何落地成反馈表

当前最现实的方案不是“假装已经自动评分”，而是先做“人工评分 + 结构化 feedback CSV”。

推荐 feedback CSV schema：

```text
image_name,
run_name,
item_id,
asset_type,
positive_prompt,
seed,
prompt_alignment_score,
composition_score,
style_consistency_score,
structure_quality_score,
detail_clarity_score,
game_usability_score,
overall_score,
problem_tags,
notes,
next_action
```

字段解释（面试版）：

- `image_name`：图片文件名。
- `run_name`：来自哪一轮实验。
- `item_id`：对应哪条任务。
- `asset_type`：character/environment/icon/material 等。
- `positive_prompt`：本图主描述，便于回看。
- `seed`：复现实验必需字段。
- `prompt_alignment_score`：图和需求是否对齐。
- `composition_score`：构图是否可用。
- `style_consistency_score`：风格是否一致。
- `structure_quality_score`：结构是否崩坏（手脸武器等）。
- `detail_clarity_score`：清晰度与细节。
- `game_usability_score`：能否进入游戏资产流程。
- `overall_score`：综合评分。
- `problem_tags`：问题标签（可多标签）。
- `notes`：人工备注。
- `next_action`：下一轮修改建议。

评分建议 1~5：

- 1 = 不可用
- 3 = 可作为参考
- 5 = 可进入下一轮筛选或给美术参考

示例：

```text
character_00004.png,
z_image_turbo_case_round1,
1,
character,
"female fantasy ranger, short silver hair, leather armor, standing in forest ruins, full body character concept art, clean silhouette, cinematic lighting, high quality game art",
123456,
4,
3,
4,
2,
3,
3,
3.2,
"hand_error;composition_ok;style_good",
"整体风格可用，但手部结构崩坏",
"增强 negative prompt，减少手部细节，下一轮固定 seed 对比"
```

这个 feedback CSV 后续用途：

1. 统计哪些 prompt 模板更容易出好图。  
2. 聚合常见问题标签（比如手崩、构图乱）。  
3. 反推下一轮 prompt 模板与参数策略。  
4. 未来接自动评分模型时，可作为监督数据或评估集。

面试话术：

“我现在不是说已经全自动评分，而是先把人工评估结构化。这样才能形成‘生成-筛选-优化-再生成’的闭环。”

---

## 11. 生成效果不好时，我如何分析问题（排查树）

### 9.1 第一步：先确认 prompt 有没有真的生效

检查顺序：

1. `run_manifest.json` 看 `positive_prompt`；
2. `patched_workflows/item_xxxx_patched_workflow.json` 看 CLIPTextEncode 的 `inputs.text`；
3. `patch_report.md` 看 Prompt Override；
4. `comfyui_submit_results.json` 确认提交的是该 run 对应 patched workflow。

如果 prompt 没生效，常见原因与处理：

- CSV 字段名不对 -> 用 `positive_prompt` 或 alias；
- node_map 指错节点 -> 修 `configs/node_maps/*.yaml`；
- run-name 复用老结果 -> 换新 `--run-name` 重新跑。

### 9.2 prompt 生效了，但图还是不符合描述

可能原因：

- prompt 太长，主体被稀释；
- 风格词冲突（比如 realistic + anime）；
- 主体词放太后；
- 模型本身对概念理解弱；
- cfg 不合适。

处理策略：

- 主体词前置；
- 每次只改一类词；
- 固定 seed 做 A/B；
- 拆成 `subject/style/attributes`；
- 清理冲突词。

### 9.3 画风不稳定

可能原因：

- style 词不固定；
- LoRA 强度波动；
- seed 随机范围太大；
- prompt 风格后缀不统一。

处理：

- 固定风格模板；
- 固定 LoRA 与强度区间；
- 固定 sampler/scheduler；
- 统一后缀词（例如 `game concept art, clean silhouette, consistent style`）。

### 9.4 结构崩坏（手/脸/武器）

可能原因：

- 模型能力上限；
- steps 不足；
- prompt 同时要求太复杂；
- 缺少结构控制。

处理：

- 降低描述复杂度；
- 加强 negative prompt；
- 尝试提高 steps 或切 sampler；
- 后续接 ControlNet/pose/depth/reference。

### 9.5 图好看但不适合游戏资产

可能原因：

- 没指定资产用途；
- 没指定构图约束；
- 没考虑裁剪与可读性。

处理示例：

- UI icon：`centered / isolated / high readability / clean background`
- 角色概念：`full body / front view / character sheet`
- 场景参考：`environment concept / wide shot / level design reference`
- 材质参考：`seamless texture / orthographic / material reference`

### 9.6 面试话术

“我排查会先看数据链路，再看生成链路，最后才怀疑模型本身。很多问题不是模型弱，而是 prompt 没覆盖、node map 错、参数没写进去，或者提交错了文件。”

---

## 12. 坏图如何反推下一轮优化策略

| 现象 | 可能原因 | 检查文件 | 下一轮修改 |
|---|---|---|---|
| 主体不是我要的 | 主体词不明确 / cfg 太低 / 模型理解弱 | `run_manifest.json`、`patched_workflows/*.json` | 主体词前置，描述更具体，适当调高 cfg |
| 风格飘了 | style 词不统一 / LoRA 强度不稳定 | `run_manifest.json`、config | 统一 style suffix，固定 LoRA strength |
| 画面太乱 | prompt 太长 / 元素过多 / 构图词缺失 | prompt pack、patched workflow | 减少元素，加入 `clean composition/centered/simple background` |
| 手脸崩坏 | 模型结构能力限制 / 细节过复杂 | 结果图 + prompt + negative prompt | negative 增加 `bad anatomy/extra fingers/distorted face`，后续可接 ControlNet pose |
| 图好看但不可落地 | 没加资产用途约束 | prompt pack | 角色/icon/环境/材质分别用专用模板 |
| 输出文件名混乱 | filename_prefix 没规范 | prompt pack、SaveImage patch | 统一 prefix 命名规则并复查 SaveImage 节点 |
| 两轮无法比较 | seed 未固定 / run_name 混乱 | `run_manifest.json` | 固定 seed，round 命名规范化 |

---

## 13. 与游戏开发效率的关系（讲业务价值）

1. 角色概念探索更快：同一主题可一次出多版方向。  
2. 场景氛围迭代更快：同一关卡可批量比较视觉风格。  
3. UI/icon 草稿更快：减少“从零手绘”的初始成本。  
4. 风格管理更清晰：LoRA + 模板 + 参数策略可控。  
5. 复盘能力更强：结果不再是“只剩图片”，还有参数证据。

---

## 14. 与 UE5 / 3D / 图形学的关系：我怎么讲才不生硬

### 14.1 我不会说这个项目已经完成 3D 生成

这点必须先讲清楚：当前项目是 2D AIGC 资产生成自动化，不是 mesh 生成系统。

### 14.2 为什么它仍然和 3D/图形学岗位相关

我会用生产链路解释，而不是堆关键词：

```text
2D 概念图
-> 角色三视图/多视角参考
-> 建模参考
-> 材质与贴图参考
-> UE5 placeholder / UI / icon / environment reference
-> 后续 image-to-3D / multi-view / reconstruction
```

核心观点：游戏 3D 资产生产不是从 mesh 才开始，前期设定、材质参考、风格一致性同样是链路的一部分。

### 14.3 如果继续往 3D 扩，我会怎么做

阶段 A：2D 参考规范化  
- 角色 front/side/back view prompt 模板  
- 材质 reference prompt 模板  
- 道具 orthographic view 模板

阶段 B：结构可控生成  
- 接 ControlNet / depth / pose / lineart  
- 提高构图和结构一致性

阶段 C：多视角一致性  
- 同一角色/道具生成多视角  
- 以 `asset_id` 绑定多视角 prompt 与结果

阶段 D：image-to-3D / reconstruction  
- 接第三方 image-to-3D 或多视角重建工具  
- 输出 mesh 或 3D preview  
- 将结果与 prompt/seed/2D reference 绑定

阶段 E：UE5 下游验证  
- 命名规范  
- 贴图格式  
- 材质参考  
- 手动或半自动导入 UE5  
- 记录导入问题

### 14.4 面试话术（1 分钟）

“我不会把这个项目说成已经做完 3D 生成，因为它当前主要是 2D 资产自动化。它和 3D/图形学岗位的关系在于：游戏 3D 生产前期需要大量视觉设定、材质参考和风格统一。我做的是这部分前置流程的工程化，把生成结果和参数绑定，能稳定复盘。后续如果继续扩展，我会按阶段走：先做三视图和材质模板，再接 ControlNet 做结构控制，再做多视角一致性，最后接 image-to-3D 和 UE5 下游验证。这样路径清晰，而且不夸大当前完成度。”

---

## 15. 关联项目经验：虚拟人 / 动画（单独说明，避免混项目）

如果面试官追问 3D/动画实践，我会补充另一个项目经验：

- TCP JSON line 发送表情帧到 UE5；
- UE5 端 VHReceiver 接收 `expression_frame`；
- 当前主要驱动 Morph Target（不是骨骼驱动）；
- AI Runtime 有文本 -> TTS -> morph 时间线 -> UE 播放链路。

我会明确说：这是另一个项目，不和当前 AIGC 资产仓库混为一谈。

---

## 16. 面试时我应该按什么顺序讲（含口述稿）

### 步骤 1：先讲业务问题
“游戏前期需要大量概念图和 UI 草稿，如果只靠手动点图，效率和复盘都不行。”

### 步骤 2：再讲手动 ComfyUI 痛点
“手动流程难复现，参数散，批量难，换 workflow 接入成本高。”

### 步骤 3：讲我的方案
“我把 ComfyUI 当生成后端，Python 仓库做调度层和记录层。”

### 步骤 4：讲核心流程
“流程是 `scaffold -> prompt pack -> pipeline -> submit -> report`，每一步都有输入和输出文件。”

### 步骤 5：讲一个具体例子
“比如 Z-Image Turbo 的 prompt pack 两行，一行角色一行场景，pipeline 会生成两个 patched workflow，再 submit 两次拿两个 prompt_id。”

### 步骤 6：讲调参和质检
“我会固定 seed 做 A/B，对比 prompt 与 cfg/steps 的影响，并用 manifest 和报告定位问题。”

### 步骤 7：讲 3D/UE5 与边界
“当前做的是 2D 自动化和下游规划，不夸大成完整 3D 系统。”

---

## 17. 与 AI算法开发-3D/图形学方向 JD 的匹配关系（细化版）

| JD 关键词 | 项目中对应内容 | 我可以怎么讲 | 实际完成程度 | 下一步扩展 | 不能夸大的边界 |
|---|---|---|---|---|---|
| 多模态内容生成 | 当前覆盖 2D 资产（角色/场景/UI/icon）批量生成 | 我把 2D 生成从单次出图做成了批处理流程 | 已实现 | 接 ControlNet、多视角、image-to-3D | 当前不是完整 3D/动画生成 |
| 构建数据与工具流程 | prompt pack CSV + config + node map + results/runs | 我做的是“数据表驱动的生成流程”，不是手工操作 | 已实现 | 加反馈CSV和自动评分闭环 | 不是多人协作平台 |
| 推理框架实践 | 基于 ComfyUI API workflow，含 LoRA 推理参数控制 | 我熟悉推理链路的参数影响和工程封装 | 已实现（推理） | 增加训练/微调闭环 | 不是训练平台 |
| 3D/图形学关联 | 2D 结果作为建模/材质/场景前置参考 | 我理解 2D 参考如何服务 3D 生产链 | 可讲清（规划层） | image-to-3D、材质贴图流程 | 未完成重建/mesh落地 |
| 游戏研发价值 | 角色概念、场景氛围、UI icon、道具草图快速迭代 | 我解决的是游戏研发真实效率问题 | 已实现 | 与UE5资源管理规范衔接 | 仍是实验级仓库 |

---

## 18. 面试官可能追问与回答（25题，扩展版）

> 每题结构：直接回答 + 项目例子 + 加分点 + 边界说明

1. **你这个项目和直接用 ComfyUI 有什么区别？**  
   直接回答：区别不在“能不能出图”，而在“能不能批量、复现、复盘”。  
   项目例子：我用 `workflow_import_pipeline` 让 CSV 每行生成独立 patched workflow，再 `submit` 批量提交并记录结果。  
   加分点：`run_manifest.json` 和 `patch_report.md` 能解释每张图的来源。  
   边界：底层生成仍由 ComfyUI 执行，我做的是流程层。

2. **你如何从一个新 workflow 接入到批量运行？**  
   直接回答：用 `scaffold_workflow` 自动接入，再做人工确认。  
   项目例子：自动生成 config/node_map/default CSV/editable CSV/report。  
   加分点：接入流程标准化，降低人为错配 node id 的风险。  
   边界：自动生成后仍需要人工确认低置信字段。

3. **为什么要做 workflow patch？**  
   直接回答：因为 workflow JSON 应该是模板，不该承载每次实验内容。  
   项目例子：每条任务单独写到 `item_xxxx_patched_workflow.json`。  
   加分点：可重放、可对比、可定位问题。  
   边界：patch 依赖正确 node_map。

4. **为什么需要 node map？**  
   直接回答：ComfyUI node id 不可读，node map 是业务字段和节点输入之间的桥。  
   项目例子：`positive_prompt -> 76:6.inputs.text`，`steps -> 76:3.inputs.steps`。  
   加分点：换 workflow 时只改映射，不改主流程代码。  
   边界：node变化太大时要重新建议或人工修图。

5. **prompt pack 有什么价值？**  
   直接回答：它把“生成任务”数据化。  
   项目例子：`z_image_turbo_prompt_pack.csv` 两行可同时跑角色和场景。  
   加分点：支持 alias，兼容历史列名。  
   边界：CSV 质量仍取决于 prompt 写法。

6. **你如何保证生成结果可复现？**  
   直接回答：固定 seed + 保存每条 patched workflow + 保存提交结果。  
   项目例子：`run_manifest.json` 记录参数来源，`comfyui_submit_results.json` 记录 prompt_id。  
   加分点：不是只留图，而是留证据链。  
   边界：模型文件或 ComfyUI 环境变化仍会影响结果。

7. **如果换一个新的 ComfyUI workflow，怎么接入？**  
   直接回答：`scaffold_workflow` -> 验证默认图 -> 编辑 prompt pack -> pipeline -> submit。  
   项目例子：脚本会给 `next_commands.md`。  
   加分点：新接入不是 ad-hoc，而是固定 SOP。  
   边界：复杂自定义节点仍可能需要人工校验。

8. **如果节点 ID 变了怎么办？**  
   直接回答：重跑建议映射或 scaffold，更新 node_map。  
   项目例子：`mapping_suggester.py` 可输出 diff 和 manual review。  
   加分点：映射可版本管理。  
   边界：如果 workflow 结构完全改写，接入成本会增加。

9. **如果 prompt 没有生效，你怎么排查？**  
   直接回答：先看 manifest，再看 patched workflow，再看 patch report。  
   项目例子：检查 CLIPTextEncode 的 `inputs.text` 是否已替换。  
   加分点：先查数据链路再查模型。  
   边界：即使 prompt 生效，模型也可能理解偏差。

10. **submit 阶段怎么和 ComfyUI 通信？**  
    直接回答：HTTP POST `/prompt`。  
    项目例子：`comfyui_client.py` 用 requests 提交 `{"prompt": prompt_graph}`。  
    加分点：提交失败会保留错误信息和 node_errors。  
    边界：依赖 ComfyUI 在线。

11. **为什么需要 per-item patched workflow？**  
    直接回答：避免多条任务混在一个文件里。  
    项目例子：`item_0001_patched_workflow.json` 对应 CSV 第1行。  
    加分点：逐条重放、逐条定位。  
    边界：文件数量会增加，需要命名规范管理。

12. **这个项目哪里体现 AI 算法能力？**  
    直接回答：在推理策略、prompt工程、LoRA参数管理与实验设计。  
    项目例子：固定 seed 做 prompt A/B，控制 cfg/steps/sampler。  
    加分点：把算法参数和结果建立可解释映射。  
    边界：不宣称完成训练平台。

13. **这个项目哪里体现工程能力？**  
    直接回答：体现在流程分层、接口设计、回归测试和失败处理。  
    项目例子：`test_batch_submit_submits_all_items.py` 覆盖批量提交正确性。  
    加分点：有明确输入/输出契约。  
    边界：当前仍是单仓库工具链，不是完整平台。

14. **和 3D/图形学有什么关系？**  
    直接回答：它是 3D 前置参考层，不是 3D 生成终态。  
    项目例子：角色设定图、材质参考图服务后续建模/材质。  
    加分点：能把 AIGC 放进真实游戏生产链路讲清楚。  
    边界：当前没完成 mesh 重建。

15. **如何扩展到 3D 资产生成？**  
    直接回答：沿用当前批处理框架接 image-to-3D/multi-view。  
    项目例子：保留 run 级证据链，后续可追踪 2D->3D 中间产物。  
    加分点：先有流程基建，再扩能力。  
    边界：目前只是规划。

16. **如何和 UE5 结合？**  
    直接回答：先做人可执行的资源规范，再做自动化。  
    项目例子：用 filename_prefix 和 run 分类做归档。  
    加分点：重视下游资产管理，不止出图。  
    边界：当前未做 UE5 自动导入脚本。

17. **如何做质量评估？**  
    直接回答：目前是人工评估 + 参数可追踪。  
    项目例子：按 run 回看 prompt/seed/参数与输出图。  
    加分点：先把“可解释”做好，再谈“自动评分”。  
    边界：自动评分尚未接入。

18. **如何保证风格一致性？**  
    直接回答：固定 style 模板、LoRA 强度区间、seed策略、采样策略。  
    项目例子：Qwen LoRA workflow 做风格化批量探索。  
    加分点：把“风格”当可控变量，不是纯玄学。  
    边界：跨模型一致性仍需更多约束。

19. **LoRA 在这里起什么作用？**  
    直接回答：用于风格和角色一致性增强。  
    项目例子：`qwen_image_illustration_lora_api.yaml` 中配置了 LoRA 路径和强度。  
    加分点：强度可控，可做 A/B。  
    边界：是推理接入，不是训练闭环。

20. **ControlNet 后续怎么接？**  
    直接回答：映射层已有 controlnet 字段位，后续补节点映射和输入图管理。  
    项目例子：`WorkflowPatchParams` 已有 `use_controlnet/control_image_path`。  
    加分点：接口预留已考虑。  
    边界：当前默认未启用。

21. **项目当前不足是什么？**  
    直接回答：2D 自动化已完成，但自动质检、训练闭环、UE5自动导入未完成。  
    项目例子：已有提交和报告链路，缺自动评分。  
    加分点：边界清晰，迭代路线清楚。  
    边界：不是生产中台。

22. **如果让你继续做一个月，你怎么规划？**  
    直接回答：优先补“质量闭环”和“下游规范”。  
    项目例子：先上 feedback CSV + 规则评分，再接 ControlNet。  
    加分点：先做 ROI 高的事项。  
    边界：不会一口气承诺完整 3D 平台。

23. **你遇到过最难的问题是什么？**  
    直接回答：不是模型，而是流程可靠性。  
    项目例子：批量 submit 只提交第一条的问题，通过 per-item + 完整性校验修正。  
    加分点：有真实故障与回归测试。  
    边界：仍可能遇到第三方节点兼容问题。

24. **你如何定位 prompt pack 没覆盖 workflow 默认 prompt？**  
    直接回答：看 source 字段和 patched 结果双重确认。  
    项目例子：`positive_prompt_source` 与 `final_patched_prompt`。  
    加分点：数据链路可证据化。  
    边界：覆盖成功不代表语义一定被模型理解。

25. **如果面试官说“这不就是调 API 吗”，你怎么回答？**  
    直接回答：调 API 只是最后一步，真正价值是流程设计与复盘机制。  
    项目例子：scaffold 接入、alias 归一化、per-item patch、提交完整性校验、报告链路。  
    加分点：把“生成能力”变成“可运营流程”。  
    边界：我不会说成平台化中台，只说实验工具链。

---

## 19. 高频问题长回答口述版

下面 8 个问题是我建议优先背熟的，每个回答大约 30~60 秒。

### 19.1 这和直接用 ComfyUI 有什么区别？

“如果只是用 ComfyUI，我当然也能手动出图，但问题是很难批量、难复现、也很难回溯参数。我这个项目把 ComfyUI当后端，Python 做调度层：CSV 决定生成什么，workflow JSON 决定怎么生成，node map 决定把字段写到哪个节点。每条任务会生成自己的 patched workflow 和 patch report。这样图不好时，我不是靠猜，而是能回到 `run_manifest.json` 查 prompt、seed、cfg、filename_prefix，再看 patched workflow 具体写进去没。”

### 19.2 这个项目哪里体现 AI 算法能力？

“我不会把它说成训练平台，它体现的是推理工程和实验设计能力。比如我会固定 seed 做 prompt A/B，只改一个变量观察变化；我把 steps、cfg、sampler、LoRA strength 都参数化，不是随意调。`workflow_runner.py` 和 `comfyui_adapter.py` 让这些参数有稳定入口，结果还能追溯。算法价值在于可控实验和解释能力，而不是只会调一次 prompt。”

### 19.3 这个项目哪里体现工程能力？

“工程能力主要体现在流程拆分和可靠性。接入层有 `scaffold_workflow` 自动生成配套文件，执行层有 `workflow_import_pipeline` 做 per-item patch，提交层有 `submit` 做批量提交和结果落盘。再加上测试，比如 `test_batch_submit_submits_all_items.py` 和 `test_batch_submit_detects_incomplete_patched_workflows.py`，说明我不是只写 happy path，还处理了真实批处理故障。”

### 19.4 和 3D/图形学有什么关系？

“我不会说已经做完 3D 生成。它的关系在于：游戏里 3D 生产前期需要大量 2D 设定和材质参考。我这个仓库把这部分前置流程标准化了，能稳定产出角色设定、环境参考、UI/icon，并且能追踪参数。后续可以在这个框架上接多视角一致性和 image-to-3D。也就是说它是 3D 链路前端的工具层，而不是最终重建系统。”

### 19.5 生成效果不好你怎么排查？

“我排查顺序是固定的：先看数据链路，再看生成链路。先看 `run_manifest.json`，确认最终 prompt 是什么；再看 `patched_workflows/item_xxxx`，确认 CLIPTextEncode 的 text 是否真的被替换；再看 `patch_report.md` 和 submit 结果。如果这些都对，再考虑 prompt 结构、cfg、steps 或模型能力。这样可以避免把数据问题误判成模型问题。”

### 19.6 如何做质量评估？

“当前我不会夸大成自动评分系统。我现在做的是‘可追踪 + 人工结构化评分’：每张图可回到 run/item/prompt/seed，然后通过 feedback CSV 记录 prompt 对齐、构图、风格一致、结构质量、可用性这些分数和问题标签。这样下一轮优化不是拍脑袋，而是有数据依据。后续再接 CLIP/aesthetic 这些自动打分模型。”

### 19.7 如何保证风格一致性？

“我会把风格一致性拆成几个可控变量：统一 style suffix、固定 LoRA 和强度区间、固定 sampler/scheduler、控制 seed 策略。比如 Qwen LoRA workflow 我会做不同强度 A/B，但其它参数尽量不动，这样能看出风格变化到底来自 LoRA 还是其他因素。核心是把风格管理从‘感觉’变成‘变量控制’。”

### 19.8 如果继续做一个月，你怎么规划？

“我会按收益优先级做三件事：第一，补 feedback CSV 到统计报表，把问题标签和高分样本结构化；第二，接结构控制能力，比如 ControlNet/pose/depth，解决构图和结构不稳；第三，做 UE5 下游规范，比如命名和分类，保证结果可进入后续流程。不会一上来就承诺完整 3D 平台，而是先把闭环做扎实。”

---

## 20. 项目难点与解决过程（STAR / 问题-分析-解决）

### 难点 1：API workflow 和 UI workflow 混淆
- 现象：导入后 patch 报错。  
- 根因：输入 JSON 格式不对。  
- 解决：`workflow_inspector.py` + `comfyui_adapter.py` 严格识别并拒绝 UI 格式。  
- 结果：接入阶段更早失败，问题更可控。  
- 面试说法：我先保证输入边界，再保证主链路稳定。

### 难点 2：node id 不稳定且不可读
- 现象：每接 workflow 都要手抠节点。  
- 根因：业务字段和节点输入没有中间层。  
- 解决：node_map + mapping_suggester + scaffold。  
- 结果：接入效率和可维护性提升。  
- 面试说法：我把“节点细节”抽象成“业务映射”。

### 难点 3：prompt 覆盖关系不清
- 现象：看起来改了 CSV，但图像还像默认 prompt。  
- 根因：字段 alias 和优先级处理不一致。  
- 解决：在 `workflow_runner.py` 统一 alias 与 source 标记；优先级明确。  
- 结果：可解释“最终 prompt 来自哪里”。  
- 面试说法：我做了可证据化的参数来源链。

### 难点 4：batch submit 曾只提交第一条
- 现象：多行任务只生成一张。  
- 根因：旧单文件逻辑和批量逻辑冲突。  
- 解决：per-item patched workflow + 批量完整性校验。  
- 结果：`test_batch_submit_submits_all_items.py` 覆盖全量提交。  
- 面试说法：我用测试把故障固化成可回归规则。

### 难点 5：新 workflow 接入重复劳动
- 现象：每次都手写配置，易错且慢。  
- 根因：缺标准 onboarding 工具。  
- 解决：`scaffold_workflow` 自动生成全套文件和 next commands。  
- 结果：接入变成流程化操作。  
- 面试说法：我不仅自动化了执行，也自动化了接入。

---

## 21. 面试时如果让我现场演示，我怎么演示

这是一个可在 5 分钟内完成的 demo 脚本。

### 21.1 演示前准备

- ComfyUI Desktop 已打开，监听 `8000`。
- 进入目录：`D:\RT\game-aigc-asset-workflow`。
- 准备好 `examples/prompt_packs/z_image_turbo_prompt_pack.csv`。

### 21.2 第一步：展示 prompt pack

先给面试官看 CSV 两行任务：`character` 和 `environment`。  
说明：“这两行就是两条批量任务，不用手工点两次。”

### 21.3 第二步：跑 workflow_import_pipeline

```bash
python scripts/run_batch_generation.py --config configs/z_image_turbo_api.yaml --prompt-pack examples/prompt_packs/z_image_turbo_prompt_pack.csv --mode workflow_import_pipeline --run-name demo_interview_round1
```

展示文件：

- `run_manifest.json`
- `patched_workflows/`
- `patch_report.md`

重点讲：“每条 CSV 都变成独立 patched workflow。”

### 21.4 第三步：跑 submit

```bash
python scripts/run_batch_generation.py --config configs/z_image_turbo_api.yaml --prompt-pack examples/prompt_packs/z_image_turbo_prompt_pack.csv --mode submit --run-name demo_interview_round1
```

展示：

- `comfyui_submit_results.json`
- ComfyUI Generated 面板

重点讲：“看 `submitted_items` 是否等于 CSV 行数。”

### 21.5 第四步：讲一张图如何追溯

追溯路径：

图片文件名 -> `filename_prefix` -> manifest item -> prompt -> patched workflow 节点内容

重点讲：“我能解释这张图为什么是这个结果。”

### 21.6 第五步：讲图不好时怎么改

- prompt pack 改 prompt；
- config 改 cfg/steps/seed；
- 再跑新 run-name 做 A/B。

这一步体现你不仅会跑，还会迭代。

---

## 22. 我不会夸大的内容（边界 + 后续方向）

1. 当前没有完整 3D mesh 生成。  
   后续：探索 image-to-3D / multi-view / reconstruction 接入。

2. 当前没有完整 LoRA 训练平台。  
   后续：在推理链路稳定基础上补小样本训练闭环。

3. 当前没有 UE5 全自动导入。  
   后续：先做资源规范，再做半自动导入脚本。

4. 当前没有自动质量评分系统。  
   后续：补 CLIP/aesthetic/规则检测 + feedback CSV。

5. 当前没有多人协作平台/数据库/网页系统。  
   后续：如果规模化，再做服务化与任务管理。

6. 当前依赖 ComfyUI 在线运行。  
   后续：可补健康检查与更稳健的重试机制。

7. 当前是实验级工具链，不是生产中台。  
   后续：按团队需求逐步产品化。

---

## 23. 简历项目描述（可直接粘贴）

### 18.1 简历短版（2行）
搭建基于 ComfyUI API workflow 的游戏 AIGC 资产批量生成工具链，实现 `prompt pack -> workflow patch -> batch submit -> report` 全流程。  
支持新 workflow 自动 scaffold、参数追踪与结果复盘，服务角色/场景/UI 资产前期探索。

### 18.2 简历标准版（3条）
- 实现 `scripts/run_batch_generation.py` 主链路，支持 `scaffold_workflow`、`workflow_import_pipeline`、`submit` 三类关键模式。  
- 构建 per-item patched workflow 与结果证据链（`run_manifest.json`、`patch_report.md`、`comfyui_submit_results.json`），提升可复现性与排障效率。  
- 面向游戏研发场景完成 2D 资产自动化流程，并规划向 UE5/3D 下游（材质参考、image-to-3D）扩展。

### 18.3 AI/3D岗位强化版
- 基于 ComfyUI API workflow 实现 diffusion 推理工程化调度，覆盖 prompt 管理、LoRA 推理参数控制与批量实验。  
- 通过 node map 与字段归一化机制，解决 workflow 变更下的参数映射稳定性问题。  
- 以 2D 资产自动化为基础，构建面向 UE5/3D 生产前置的视觉参考流程（非完整 3D 生成系统）。

---

## 24. 面试关键词清单（背诵版）

### 技术关键词
- ComfyUI API workflow
- prompt pack / alias 归一化
- node map
- per-item patched workflow
- batch submit
- seed / steps / cfg / sampler / scheduler / denoise
- LoRA inference control
- run_manifest / patch_report / submit_results
- workflow scaffold
- UE5 downstream planning

### 业务关键词
- 游戏资产前期探索
- 角色概念图 / 场景氛围图 / UI icon / 道具草图
- 风格一致性
- 可复盘实验
- 批量迭代效率

---

## 25. 我在面试中最应该强调的 5 件事

1. 我不是只会用 ComfyUI，而是做了自动化工具链。  
2. 我把流程拆成可配置输入、可执行链路、可验证输出。  
3. 我解决的是游戏资产生产里的真实效率和复盘问题。  
4. 我能讲清楚如何从 2D 自动化扩展到 UE5/3D 下游。  
5. 我会明确边界，不把“规划”说成“已完成”。

---

## 26. 我应该怎么使用这份文档准备面试

1. 先背第 1 章的 30 秒和 2 分钟介绍。  
2. 再掌握第 3 章完整流程（这是主线）。  
3. 再重点看第 9/10/11/12 章（质量评估、反馈表、排查树、坏图反推）。  
4. 面 AI/3D 岗时重点看第 14/17 章（3D关联和JD匹配）。  
5. 最后背第 19 章高频长回答，准备口述。

