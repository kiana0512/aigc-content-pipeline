# Workflow Notes

## Purpose

This document records the purpose, current status, and future replacement plan for the workflow files stored under `workflows/comfyui/`.

At the current stage, the JSON files in that folder are placeholder definitions rather than final exported ComfyUI graphs.

They are used to:
- clarify workflow responsibilities
- keep repository structure complete
- prepare for later replacement with real ComfyUI workflow exports
- support documentation and experiment planning

---

## Current Workflow Files

### 1. `sdxl_ui_icon_base.json`

#### Purpose
Baseline workflow definition for game UI icon generation.

#### Current Role
- stores baseline task metadata
- records target prompt files and output directory
- defines expected sampling settings
- serves as the future placeholder for the actual ComfyUI-exported workflow

#### Main Focus
- icon readability
- centered composition
- clean silhouette
- asset reusability for game UI scenarios

#### Replacement Plan
Replace with a real ComfyUI workflow export after:
- SDXL base graph is built
- prompt inputs are verified
- batch output path is tested

---

### 2. `sdxl_concept_base.json`

#### Purpose
Baseline workflow definition for character concept art and stylized concept generation.

#### Current Role
- records baseline concept-art generation setup
- defines concept-art prompt source and output path
- serves as a placeholder for future exported workflow JSON

#### Main Focus
- character design readability
- style consistency
- costume structure
- concept-art usability for game production reference

#### Replacement Plan
Replace with a real ComfyUI workflow export after:
- baseline concept-art graph is built
- generation parameters are validated
- output organization scheme is confirmed

---

### 3. `controlnet_edge_icon.json`

#### Purpose
Controllable generation workflow definition for UI icon generation with edge-map guidance.

#### Current Role
- records the planned ControlNet experiment path
- connects OpenCV preprocessing with downstream generation
- defines future baseline-vs-guided comparison direction

#### Main Focus
- structure control
- silhouette clarity
- shape readability
- controllability under icon-generation scenarios

#### Replacement Plan
Replace with a real ComfyUI workflow export after:
- edge extraction script is implemented
- control image directory format is fixed
- ControlNet graph is constructed and tested

---

## Recommended Workflow Development Order

### Step 1
Build and validate `sdxl_ui_icon_base`

### Step 2
Build and validate `sdxl_concept_base`

### Step 3
Implement OpenCV preprocessing for edge extraction

### Step 4
Build and validate `controlnet_edge_icon`

### Step 5
Add optional workflow variants:
- LoRA-enhanced icon workflow
- reference-guided concept workflow
- IP-Adapter-based consistency workflow

---

## Suggested Comparison Dimensions

When comparing workflows later, focus on:

### For UI Icons
- readability
- silhouette clarity
- visual focus
- production usability
- style consistency

### For Character Concepts
- design readability
- costume detail coherence
- composition quality
- style consistency
- downstream concept usability

### For ControlNet Variants
- structure adherence
- whether style quality drops
- whether generation becomes more stable
- whether outputs become more reusable

---

## Notes for Future Export

When real ComfyUI graphs are ready, exported workflow files should:
- replace the placeholder JSON files directly
- keep the same filenames if possible
- preserve a short note in this file about what changed
- record the model / sampler / scheduler used at export time

---

## Current Status

Current status: placeholder stage

This folder is structurally ready, but the workflow JSON files should still be replaced later by real ComfyUI-exported graphs.