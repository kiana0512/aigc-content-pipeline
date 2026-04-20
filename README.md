# game-aigc-asset-workflow

An experimental AIGC workflow for game-oriented asset generation, focusing on controllable image generation for character concepts, UI icons, and stylized visual assets.

## Overview

This repository is built around practical game art production scenarios.  
Instead of treating image generation as a simple text-to-image demo, this project focuses on building a reusable workflow that covers:

- prompt design and template reuse
- parameter presets and batch generation
- small-scale data preparation
- controllable generation with structural guidance
- result evaluation and workflow documentation
- UE5-oriented asset usability validation

The current technical direction is centered on:

- **ComfyUI** for node-based workflow design
- **Stable Diffusion / SDXL / SD3.5** for image generation
- **LoRA** for lightweight fine-tuning and style adaptation
- **ControlNet** for controllable generation
- **OpenCV** for preprocessing and structural guidance
- **PyTorch + diffusers** for model-side experimentation
- **UE5** for downstream asset validation

## Project Goals

The project aims to support several game-related visual content tasks, including:

- character concept generation
- UI icon generation
- stylized concept art generation
- style consistency exploration under small-data settings
- reusable workflow and prompt asset accumulation

This repository is intended to serve both as:

1. a practical engineering project for game AIGC content production, and  
2. a research exploration base for controllable and style-consistent generation.

## Tech Stack

- Python
- PyTorch
- diffusers
- ComfyUI
- Stable Diffusion / SDXL / SD3.5
- LoRA
- ControlNet
- OpenCV
- Pillow
- NumPy / Pandas
- YAML-based experiment configs
- UE5

## Repository Structure

```text
configs/         experiment configs
data/            raw / interim / processed / metadata
docs/            roadmap, experiment logs, resume-ready summaries
examples/        sample inputs and outputs
prompts/         prompt templates and prompt packs
scripts/         runnable utility scripts
src/             core Python modules
tests/           unit tests
ue5_validation/  UE5-side usability notes and screenshots
workflows/       ComfyUI workflow json files and notes