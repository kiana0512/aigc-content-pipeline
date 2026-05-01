from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the dedicated SAM3 conda environment.")
    parser.add_argument("--conda-env", default="sam3")
    parser.add_argument("--python-exe", default="")
    parser.add_argument("--sam3-repo-dir", default="")
    parser.add_argument("--sam3-model-root", default="")
    parser.add_argument("--sam3-config-path", default="")
    parser.add_argument("--sam3-checkpoint-path", default="")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    code = _check_code(args.sam3_repo_dir, args.sam3_model_root, args.sam3_config_path, args.sam3_checkpoint_path, args.offline)
    command = [args.python_exe, "-c", code] if args.python_exe else ["conda", "run", "-n", args.conda_env, "python", "-c", code]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        print(result.stdout.strip())
        return
    print("SAM3 environment check failed.")
    print(f"conda env: {args.conda_env}")
    print(f"python exe: {args.python_exe or '<conda run>'}")
    print(f"sam3 repo dir: {args.sam3_repo_dir or '<not provided>'}")
    print(f"sam3 model root: {args.sam3_model_root or '<not provided>'}")
    print(f"command: {' '.join(command)}")
    print(f"stdout:\n{result.stdout or '<empty>'}")
    print(f"stderr:\n{result.stderr or '<empty>'}")
    print("")
    print("Please create and install the dedicated SAM3 environment first:")
    print(f"  conda create -n {args.conda_env} python=3.12")
    print(f"  conda activate {args.conda_env}")
    print("  pip install torch torchvision --index-url <your CUDA torch index>")
    print(f"  cd {args.sam3_repo_dir or 'weights/segmentation/sam3'}")
    print("  pip install -e .")
    raise SystemExit(result.returncode or 1)


def _check_code(sam3_repo_dir: str, sam3_model_root: str, sam3_config_path: str, sam3_checkpoint_path: str, offline: bool) -> str:
    repo = str(Path(sam3_repo_dir).resolve()) if sam3_repo_dir else ""
    model_root = str(Path(sam3_model_root).resolve()) if sam3_model_root else ""
    config_path = str(Path(sam3_config_path).resolve()) if sam3_config_path else ""
    checkpoint_path = str(Path(sam3_checkpoint_path).resolve()) if sam3_checkpoint_path else ""
    return f"""
import importlib.util, inspect, os, sys
from pathlib import Path
repo={repo!r}
model_root={model_root!r}
config_path={config_path!r}
checkpoint_path={checkpoint_path!r}
offline={offline!r}
if offline:
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    os.environ['HF_DATASETS_OFFLINE']='1'
if repo and repo not in sys.path:
    sys.path.insert(0, repo)
import torch
from sam3.model_builder import build_sam3_image_model, build_sam3_predictor
from sam3.model.sam3_image_processor import Sam3Processor
root=Path(model_root) if model_root else None
def first(patterns):
    if not root:
        return None
    for pattern in patterns:
        direct=root / pattern
        if '*' not in pattern and direct.exists():
            return direct
        matches=sorted(root.rglob(pattern))
        if matches:
            return matches[0]
    return None
cfg=Path(config_path) if config_path else first(['config.json','*.yaml','*.yml'])
ckpt=Path(checkpoint_path) if checkpoint_path else first(['*.safetensors','*.pt','*.pth','*.bin'])
print('python:', sys.version.split()[0])
print('python_executable:', sys.executable)
print('torch:', torch.__version__)
print('torch.cuda.is_available:', torch.cuda.is_available())
print('torch.version.cuda:', torch.version.cuda)
print('sam3_repo_dir:', repo or '<not provided>')
print('model_root_exists:', root.exists() if root else '<not provided>')
print('config_path:', cfg)
print('config_path_exists:', cfg.exists() if cfg else '<not found>')
print('checkpoint_path:', ckpt)
print('checkpoint_path_exists:', ckpt.exists() if ckpt else '<not found>')
print('find_spec_sam3:', importlib.util.find_spec('sam3'))
print('find_spec_model_builder:', importlib.util.find_spec('sam3.model_builder'))
print('find_spec_processor:', importlib.util.find_spec('sam3.model.sam3_image_processor'))
is_sam31 = ckpt and ('sam3.1' in str(ckpt).lower() or 'multiplex' in str(ckpt).lower() or 'sam3.1' in str(root).lower())
if is_sam31:
    print('sam3_builder_mode: build_sam3_predictor(version=sam3.1)')
    if not ckpt:
        raise RuntimeError('No local SAM3.1 checkpoint found')
    predictor = build_sam3_predictor(
        checkpoint_path=str(ckpt),
        version='sam3.1',
        compile=False,
        warm_up=False,
        async_loading_frames=False,
    )
    print('SAM3.1 local predictor init: ok')
    print('SAM3 APIs: ok')
    raise SystemExit(0)
sig=inspect.signature(build_sam3_image_model)
print('build_sam3_image_model_signature:', sig)
params=sig.parameters
kwargs={{}}
if 'device' in params:
    kwargs['device']='cuda' if torch.cuda.is_available() else 'cpu'
if 'checkpoint_path' in params:
    if not ckpt:
        raise RuntimeError('No local SAM3 checkpoint found')
    kwargs['checkpoint_path']=str(ckpt)
    if 'load_from_HF' in params:
        kwargs['load_from_HF']=False
elif 'config_path' in params and 'checkpoint_path' in params:
    kwargs['config_path']=str(cfg)
    kwargs['checkpoint_path']=str(ckpt)
elif 'model_root' in params:
    kwargs['model_root']=str(root)
elif 'model_path' in params:
    kwargs['model_path']=str(root)
elif 'model_id' in params:
    kwargs['model_id']=str(root)
else:
    raise RuntimeError('No supported local model path argument in build_sam3_image_model signature')
print('local_init_kwargs:', kwargs)
model=build_sam3_image_model(**kwargs)
print('SAM3 local model init: ok')
print('SAM3 APIs: ok')
"""


if __name__ == "__main__":
    main()
