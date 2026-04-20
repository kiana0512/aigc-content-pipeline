# Roadmap

## Project Positioning

This project aims to build a practical AIGC workflow for game-oriented asset generation, with a focus on:

- character concept generation
- UI icon generation
- stylized concept art generation
- controllable diffusion workflows
- small-scale data preparation and LoRA experiments
- UE5-oriented downstream validation

The project is designed as both an engineering workflow repository and a potential research exploration base.

---

## Phase 1: Project Bootstrap

### Goals
- initialize repository structure
- define project scope
- organize dependency files
- write project documentation
- prepare placeholder scripts and configs

### Tasks
- complete README
- complete roadmap / experiment log / resume notes
- create configs, prompts, scripts, workflows, and src modules
- define first-stage task boundaries
- prepare development environment and basic coding conventions

### Expected Outputs
- a clean and structured repository
- initial project documentation
- reusable directory layout for future experiments

---

## Phase 2: Baseline Workflow Setup

### Goals
- build first runnable baseline workflows for game asset generation
- organize prompt templates and task presets
- support basic batch generation and output recording

### Tasks
- prepare prompt templates for:
  - UI icons
  - character concepts
  - stylized concept art
- add baseline ComfyUI workflow json files
- define config files for different generation tasks
- add basic batch generation scripts
- add result indexing logic

### Expected Outputs
- baseline prompt packs
- baseline ComfyUI workflows
- first batch of organized generation outputs

---

## Phase 3: Data Preparation and Prompt Assets

### Goals
- support small-scale image-text data organization
- build reusable prompt and metadata assets
- prepare for later LoRA experiments

### Tasks
- organize raw image folders
- clean filenames and metadata
- build caption generation / cleanup scripts
- define prompt templates with reusable fields
- add dataset split utilities
- build a small experiment-ready metadata table

### Expected Outputs
- cleaned small-scale dataset structure
- reusable prompt templates
- caption / metadata preparation pipeline

---

## Phase 4: Controllable Generation

### Goals
- improve generation controllability
- introduce structure-aware preprocessing
- compare guided and unguided generation behavior

### Tasks
- add OpenCV preprocessing utilities
- support edge map generation
- support mask / simple structure guidance
- connect preprocessing outputs to ControlNet workflows
- compare baseline generation with guided generation
- record qualitative observations for style and structure consistency

### Expected Outputs
- OpenCV preprocessing scripts
- ControlNet-based workflow variants
- comparison records for controllable generation

---

## Phase 5: Small-Scale LoRA Experiments

### Goals
- explore lightweight fine-tuning for game visual styles
- test style adaptation under limited data conditions
- build a minimal fine-tuning and evaluation loop

### Tasks
- define LoRA experiment configs
- prepare training data subsets
- run small-scale style adaptation experiments
- record training settings and outputs
- compare base model outputs with LoRA-enhanced outputs

### Expected Outputs
- initial LoRA experiment records
- style adaptation observations
- reusable fine-tuning configs

---

## Phase 6: Evaluation and Result Organization

### Goals
- make generated outputs easier to review and compare
- summarize results from usability and consistency perspectives
- support future resume writing and research exploration

### Tasks
- add result parsing scripts
- organize outputs by task / workflow / config
- build simple qualitative evaluation records
- compare results in terms of:
  - style consistency
  - icon readability
  - concept usability
  - workflow stability
- build report-ready notes

### Expected Outputs
- organized experiment logs
- structured result folders
- evaluation summaries for iteration

---

## Phase 7: UE5-Oriented Validation

### Goals
- verify whether generated assets are useful in downstream UE5 scenarios
- connect generation workflow with practical asset usage

### Tasks
- define UE5-side validation checklist
- record whether generated images are usable as:
  - concept references
  - UI design references
  - stylized visual direction references
- collect screenshots and usage notes
- summarize practical limitations and improvement directions

### Expected Outputs
- UE5 validation notes
- screenshot-based usage records
- downstream usability observations

---

## Potential Research Extension

A possible research direction based on this repository is:

**Style-consistent and controllable generation for game UI icons and concept art under small-data conditions**

Possible focus points:
- style consistency under limited data
- prompt and reference-based controllability
- structural guidance with preprocessing signals
- workflow-level quality evaluation for practical content production

---

## Current Priority

The current priority is:

1. complete project scaffolding
2. finish documentation and config placeholders
3. build baseline prompt assets
4. add first workflow and script placeholders
5. start baseline generation experiments