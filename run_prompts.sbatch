#!/bin/bash
# Run one prompt file through vLLM on a LUMI 8×MI250X node.
# Usage: sbatch run_prompts.sbatch <prompts.jsonl> <out.jsonl> [extra run_prompts.py args]
#SBATCH --account=<your_project>
#SBATCH --partition=small-g
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=56
#SBATCH --gpus-per-node=8
#SBATCH --mem=480G
#SBATCH --time=24:00:00
#SBATCH --job-name=parallels
#SBATCH --output=logs/%x-%j.log
set -euo pipefail
PROMPTS=${1:?prompts.jsonl}; OUT=${2:?out.jsonl}; shift 2

CONTAINER_SIF=${CONTAINER_SIF:-/path/to/vllm-rocm.sif}   # a ROCm vLLM container
export HF_HOME=${HF_HOME:-/scratch/<your_project>/hf_cache}

# ROCm / vLLM settings that worked for Qwen3.5-122B-A10B on MI250X
export HIP_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
unset ROCR_VISIBLE_DEVICES CUDA_VISIBLE_DEVICES
export VLLM_WORKER_MULTIPROC_METHOD=spawn NCCL_NET=Socket
export VLLM_ROCM_USE_AITER=0 VLLM_ROCM_USE_AITER_MHA=0 VLLM_ROCM_USE_AITER_RMSNORM=0 VLLM_ROCM_USE_AITER_MLA=0
export VLLM_USE_TRITON_FLASH_ATTN=1 VLLM_MLA_DISABLE=1
export PYTHONNOUSERSITE=1

mkdir -p logs
singularity exec --rocm --bind /pfs,/scratch,/flash --env HF_HOME="$HF_HOME" "$CONTAINER_SIF" \
    python3 -u run_prompts.py --prompts "$PROMPTS" --out "$OUT" --backend vllm "$@"
