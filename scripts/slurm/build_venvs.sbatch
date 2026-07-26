#!/bin/bash
# Build the GitChameleon dataset venvs on a SLURM cluster and archive them.
#
# The 99 environments come to roughly a million small files, which exceeds the
# file-count quota of a typical cluster filesystem. So they are built on the compute
# node's local disk (fast, no quota) and stored on the shared filesystem as a single
# compressed archive; run_eval.sbatch unpacks it back onto local disk per job.
#
#   sbatch --account=<your-account> scripts/slurm/build_venvs.sbatch
#
# Configure via environment or --export:
#   GC_ROOT     shared working directory (default $SCRATCH/gitchameleon)
#   GC_SIF      apptainer image        (default $GC_ROOT/containers/gitchameleon.sif)
#   GC_ARCHIVE  output archive         (default $GC_ROOT/venvs.tar.zst)
#
#SBATCH --job-name=gcham-venvs
#SBATCH --time=6:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=48G
#SBATCH --output=gcham-venvs-%j.out

set -euo pipefail

GC_ROOT="${GC_ROOT:-$SCRATCH/gitchameleon}"
GC_SIF="${GC_SIF:-$GC_ROOT/containers/gitchameleon.sif}"
GC_ARCHIVE="${GC_ARCHIVE:-$GC_ROOT/venvs.tar.zst}"
GC_PIP_CACHE="${GC_PIP_CACHE:-$GC_ROOT/pip-cache}"
CONCURRENCY="${CONCURRENCY:-${SLURM_CPUS_PER_TASK:-8}}"

module load apptainer 2>/dev/null || true
# Compute nodes on many clusters have no direct outbound route; this module points
# http(s)_proxy at the site proxy so pip can reach PyPI.
module load httpproxy 2>/dev/null || echo "note: no httpproxy module; assuming direct internet access"

BUILD_DIR="${SLURM_TMPDIR:-/tmp}/gcham_venvs"
mkdir -p "$BUILD_DIR" "$GC_PIP_CACHE" "$(dirname "$GC_ARCHIVE")"

echo "Building venvs in $BUILD_DIR (node $(hostname)), $CONCURRENCY at a time"

apptainer exec --cleanenv \
    --bind "$BUILD_DIR:/app/.dataset_venvs" \
    --bind "$GC_PIP_CACHE:/pip-cache" \
    --env PIP_CACHE_DIR=/pip-cache \
    ${http_proxy:+--env http_proxy="$http_proxy"} \
    ${https_proxy:+--env https_proxy="$https_proxy"} \
    "$GC_SIF" bash -c '
        # See gitchameleon/container.py for why the image needs this environment.
        export PYENV_VERSION=3.9.19 POETRY_CACHE_DIR=/root/.cache/pypoetry
        HOME="$(mktemp -d "${TMPDIR:-/tmp}/gitchameleon-XXXXXX")"; export HOME
        cd "$HOME" && poetry -C /app run python /app/gitchameleon/create_venvs.py \
            --start 0 --end 1000 --base_path /app/.dataset_venvs \
            --dataset /app/dataset.jsonl --concurrency '"$CONCURRENCY"'
    '

built=$(find "$BUILD_DIR" -maxdepth 1 -name 'gcham_venv_*' | wc -l)
echo "Built $built environments; $(du -sh "$BUILD_DIR" | cut -f1), $(find "$BUILD_DIR" | wc -l) files"

echo "Archiving to $GC_ARCHIVE"
tar --use-compress-program="zstd -T0 -3" -cf "$GC_ARCHIVE.tmp" -C "$BUILD_DIR" .
mv "$GC_ARCHIVE.tmp" "$GC_ARCHIVE"
ls -lh "$GC_ARCHIVE"
