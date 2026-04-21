# Experiment Log

## Purpose

This document is used to record project progress, experiment attempts, workflow changes, and practical observations during development.

It is not limited to formal experiments only. It can also include:

- repository setup progress
- workflow design decisions
- prompt template updates
- preprocessing attempts
- LoRA experiment notes
- ControlNet comparison notes
- UE5-side validation observations
- failure cases and follow-up plans

---

## 2026-04-20

### Project Initialization

#### Summary
Initialized the repository for a game-oriented AIGC asset generation workflow project.

#### Current Positioning
The project is currently defined as an experimental workflow for:

- character concept generation
- UI icon generation
- stylized concept art generation
- controllable image generation for game production scenarios

#### Selected Technical Direction
The current baseline technical stack is:

- ComfyUI
- Stable Diffusion / SDXL / SD3.5
- LoRA
- ControlNet
- OpenCV
- PyTorch
- diffusers
- UE5-oriented downstream validation

#### Completed Work
- repository created
- basic directory structure created
- dependency files initialized
- project README drafted
- roadmap drafted
- experiment log initialized

#### Current Development Principles
- prioritize engineering completeness over flashy demos
- keep the workflow reusable and resume-oriented
- focus on practical game asset production scenarios
- gradually build from baseline generation to controllable generation and then to lightweight fine-tuning

#### Immediate Next Steps
- complete remaining documentation files
- fill config placeholders
- add prompt template placeholders
- add workflow placeholder files
- add script placeholders
- begin first baseline workflow planning

---

## 2026-04-21

### Scaffold to ComfyUI Baseline Integration Preparation

#### Summary
Promoted the repository from scaffold stage to a practical ComfyUI baseline integration preparation stage, while keeping placeholder workflow JSON files explicit.

#### Main Changes
- added ComfyUI adapter module for API workflow patching
- added external node mapping YAML mechanism (no hardcoded node ids)
- upgraded batch generation script to support:
  - `manifest`
  - `patch_workflow`
  - optional `submit`
- aligned task configs with ComfyUI connection fields and future LoRA/ControlNet hooks
- refactored scripts to thin CLI entrypoints that call `src` modules
- added local tests for workflow patching and placeholder detection

#### Scope Decisions
- prioritized SDXL baseline for UI icon and character concept tasks
- kept UE5 automation out of this phase (docs only)
- kept LoRA / ControlNet as disabled-by-default interfaces

#### Next Step
- replace placeholder workflow JSON files with real ComfyUI API exports
- fill real node ids in node mapping YAML files
- run baseline patching and first ComfyUI execution round

---

## Logging Template

Use the following format for future updates.

### Date
YYYY-MM-DD

### Task Type
Examples:
- repo setup
- baseline generation
- prompt design
- data preparation
- OpenCV preprocessing
- ControlNet experiment
- LoRA experiment
- UE5 validation
- evaluation summary

### Goal
What was the purpose of this task or experiment?

### Inputs
What inputs, settings, prompts, references, or configs were used?

### Actions
What was actually done?

### Outputs
What files, images, logs, or results were produced?

### Observations
What looked good, what failed, what was unstable, and what should be improved?

### Next Step
What should be done next?

---

## Suggested Future Record Types

### 1. Baseline Workflow Record
Recommended fields:
- model version
- workflow file
- task type
- prompt template
- negative prompt
- image size
- seed
- sampler / scheduler
- notable observations

### 2. Prompt Iteration Record
Recommended fields:
- task scenario
- old prompt
- new prompt
- expected change
- observed change
- whether the update is worth keeping

### 3. ControlNet / Structure Guidance Record
Recommended fields:
- preprocessing type
- control condition
- guidance strength
- whether structure improved
- whether style was harmed
- whether output became more production-usable

### 4. LoRA Experiment Record
Recommended fields:
- dataset subset
- caption quality
- training config
- number of steps / epochs
- target style
- base vs LoRA comparison
- whether overfitting appeared

### 5. UE5 Validation Record
Recommended fields:
- target use case
- asset type
- whether usable as-is
- whether useful as concept reference
- consistency / readability notes
- follow-up optimization direction

---

## Notes

This file should be updated continuously during development.

The emphasis is on:
- traceability
- comparability
- practical observations
- workflow iteration value

Not every entry needs to be long, but every important change should leave a record.
