#!/bin/bash
# Evaluate a GitChameleon solution file on a SLURM cluster.
#
# Unpacks the venv archive produced by build_venvs.sbatch onto the compute node's local
# disk, then runs the harness against it inside Apptainer. Needs no network.
#
#   sbatch --account=<your-account> --export=ALL,SOLUTION=/abs/path/solutions.jsonl \
#          scripts/slurm/run_eval.sbatch
#
#SBATCH --job-name=gcham-eval
#SBATCH --time=3:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=48G
#SBATCH --output=gcham-eval-%j.out

set -euo pipefail

GC_ROOT="${GC_ROOT:-$SCRATCH/gitchameleon}"
GC_SIF="${GC_SIF:-$GC_ROOT/containers/gitchameleon.sif}"
GC_ARCHIVE="${GC_ARCHIVE:-$GC_ROOT/venvs.tar.zst}"
SOLUTION="${SOLUTION:?set SOLUTION to the absolute path of the solution jsonl}"
WORKERS="${WORKERS:-${SLURM_CPUS_PER_TASK:-8}}"

module load apptainer 2>/dev/null || true
# A few of the dataset's tests reach the network (nltk corpus downloads, gradio version
# checks). They time out rather than fail on an isolated compute node, so give the job
# the site proxy where there is one.
module load httpproxy 2>/dev/null || true

ENV_DIR="${SLURM_TMPDIR:-/tmp}/gcham_venvs"
mkdir -p "$ENV_DIR"
echo "Unpacking $GC_ARCHIVE to $ENV_DIR"
tar --use-compress-program="zstd -d -T0" -xf "$GC_ARCHIVE" -C "$ENV_DIR"
echo "$(find "$ENV_DIR" -maxdepth 1 -name 'gcham_venv_*' | wc -l) environments ready"

# The venvs record absolute paths, so they must be bound at the same container path
# they were built at (/app/.dataset_venvs).
apptainer exec --cleanenv \
    --bind "$ENV_DIR:/app/.dataset_venvs" \
    --bind "$(dirname "$SOLUTION"):/work" \
    ${http_proxy:+--env http_proxy="$http_proxy"} \
    ${https_proxy:+--env https_proxy="$https_proxy"} \
    "$GC_SIF" bash -c '
        # See gitchameleon/container.py for why the image needs this environment. In
        # particular HOME must be writable and must not be /app: some tests write to
        # relative paths, and /app is read-only under Apptainer.
        export PYENV_VERSION=3.9.19 POETRY_CACHE_DIR=/root/.cache/pypoetry NLTK_DATA=/root/nltk_data
        HOME="$(mktemp -d "${TMPDIR:-/tmp}/gitchameleon-XXXXXX")"; export HOME
        cd "$HOME" && poetry -C /app run python /app/gitchameleon/run_eval.py \
            --dataset_file /app/dataset.jsonl --solution_file /work/'"$(basename "$SOLUTION")"' \
            --env_dir /app/.dataset_venvs --test_dir /app/hidden_tests --workers '"$WORKERS"'
    '

echo "Results: ${SOLUTION%.*}_eval_results.csv"
