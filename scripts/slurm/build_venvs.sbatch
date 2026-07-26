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
# Wheels for packages the compute node cannot build itself. A few pinned versions
# predate wheels for their Python (matplotlib 3.4.0 on 3.10, say) and build from source,
# which downloads vendored C libraries from hosts some site proxies block. Prebuild
# those on a login node with scripts/slurm/prebuild_wheel.sh and they get picked up here.
GC_WHEELHOUSE="${GC_WHEELHOUSE:-$GC_ROOT/wheelhouse}"
CONCURRENCY="${CONCURRENCY:-${SLURM_CPUS_PER_TASK:-8}}"

# Locate the container runtime. Clusters differ: DRAC sites have an `apptainer` module,
# Mila only has `singularity` (3.x) modules, some installs are already on PATH.
# Prefer apptainer, including a user-installed one: singularity 3.x cannot read the
# image's /root, where poetry and the pyenv interpreters live.
CONTAINER_BIN="${GC_CONTAINER_BIN:-}"
if [ -z "$CONTAINER_BIN" ]; then
    CONTAINER_BIN="$(command -v apptainer || true)"
    [ -z "$CONTAINER_BIN" ] && [ -x "$HOME/.local/bin/apptainer" ] && CONTAINER_BIN="$HOME/.local/bin/apptainer"
    if [ -z "$CONTAINER_BIN" ]; then
        module load apptainer 2>/dev/null ||
            module load singularity/3.7.1 2>/dev/null ||
            module load singularity 2>/dev/null ||
            true
        CONTAINER_BIN="$(command -v apptainer || command -v singularity || true)"
    fi
fi
if [ -z "$CONTAINER_BIN" ]; then
    echo "error: neither apptainer nor singularity is available (set GC_CONTAINER_BIN)" >&2
    exit 1
fi
echo "Container runtime: $CONTAINER_BIN"
# Reach PyPI. Sites differ: some compute nodes route out directly, some need the site
# proxy from the `httpproxy` module — and on some the module sets a proxy that does not
# work from the node, which would break otherwise-fine direct access. So probe.
gc_reachable() { curl -fsS -m 10 -o /dev/null https://pypi.org/simple/ 2>/dev/null; }
if gc_reachable; then
    echo "PyPI: reachable directly"
else
    module load httpproxy 2>/dev/null || true
    if gc_reachable; then
        echo "PyPI: reachable via ${https_proxy:-proxy}"
    else
        echo "warning: cannot reach PyPI directly or through a proxy; venv builds will fail" >&2
        unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
    fi
fi

# The image ships a frozen copy of the dataset and tests at /app. Bind the checkout's
# copies over them when we have one, so dataset fixes take effect without rebuilding the
# image (and so the venvs match the dataset being evaluated).
GC_REPO="${GC_REPO:-${SLURM_SUBMIT_DIR:-}}"
dataset_binds=()
if [ -n "$GC_REPO" ] && [ -f "$GC_REPO/dataset/dataset.jsonl" ]; then
    dataset_binds+=(--bind "$GC_REPO/dataset/dataset.jsonl:/app/dataset.jsonl")
    [ -d "$GC_REPO/dataset/hidden_tests" ] &&
        dataset_binds+=(--bind "$GC_REPO/dataset/hidden_tests:/app/hidden_tests")
    echo "Using dataset from $GC_REPO/dataset"
else
    echo "Using the dataset baked into the image"
fi

BUILD_DIR="${SLURM_TMPDIR:-/tmp}/gcham_venvs"
mkdir -p "$BUILD_DIR" "$GC_PIP_CACHE" "$GC_WHEELHOUSE" "$(dirname "$GC_ARCHIVE")"

echo "Building venvs in $BUILD_DIR (node $(hostname)), $CONCURRENCY at a time"

"$CONTAINER_BIN" exec --cleanenv \
    "${dataset_binds[@]}" \
    --bind "$BUILD_DIR:/app/.dataset_venvs" \
    --bind "$GC_PIP_CACHE:/pip-cache" \
    --bind "$GC_WHEELHOUSE:/wheelhouse" \
    --env PIP_CACHE_DIR=/pip-cache \
    --env PIP_FIND_LINKS=/wheelhouse \
    ${http_proxy:+--env http_proxy="$http_proxy"} \
    ${https_proxy:+--env https_proxy="$https_proxy"} \
    "$GC_SIF" bash -c '
        # See gitchameleon/container.py for why the image needs this environment.
        # PATH/PYTHONPATH are set explicitly because singularity 3.x --cleanenv drops
        # the environment baked into the image, which is where poetry lives.
        export PATH=/root/.local/bin:$PATH PYTHONPATH=/app
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
