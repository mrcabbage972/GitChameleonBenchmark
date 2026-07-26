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
# A few of the dataset's tests reach the network (nltk corpus downloads, gradio version
# checks); they time out rather than fail without it. Same probe as build_venvs.sbatch:
# a proxy that does not work from the node is worse than no proxy at all.
gc_reachable() { curl -fsS -m 10 -o /dev/null https://pypi.org/simple/ 2>/dev/null; }
if gc_reachable; then
    echo "network: reachable directly"
else
    module load httpproxy 2>/dev/null || true
    gc_reachable || { echo "network: unreachable; a few tests may time out" >&2; \
        unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY; }
fi
# Some tests start a local server and then talk to it (gradio's launch() checks that its
# own URL responds). Sending that through the site proxy fails, and gradio then falls
# back to opening a public share tunnel and errors. Set this *after* loading httpproxy,
# which sets no_proxy itself and would otherwise clobber these entries.
if [ -n "${http_proxy:-}" ]; then
    export no_proxy="localhost,127.0.0.1,0.0.0.0,::1,$(hostname),$(hostname -s),${no_proxy:-}"
    export NO_PROXY="$no_proxy"
    echo "no_proxy=$no_proxy"
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

# Corpora fetched by scripts/slurm/prefetch_nltk.sh, on top of the ones baked into the
# image; NLTK searches both paths.
GC_NLTK_DATA="${GC_NLTK_DATA:-$GC_ROOT/nltk_data}"
nltk_binds=()
nltk_path=/root/nltk_data
if [ -d "$GC_NLTK_DATA" ]; then
    nltk_binds+=(--bind "$GC_NLTK_DATA:/nltk_data")
    nltk_path=/root/nltk_data:/nltk_data
fi

# librosa's example audio, fetched by scripts/slurm/prefetch_librosa.sh.
GC_LIBROSA_DATA="${GC_LIBROSA_DATA:-$GC_ROOT/librosa_data}"
librosa_binds=()
if [ -d "$GC_LIBROSA_DATA" ]; then
    librosa_binds+=(--bind "$GC_LIBROSA_DATA:/librosa_data" --env LIBROSA_DATA_DIR=/librosa_data)
fi

ENV_DIR="${SLURM_TMPDIR:-/tmp}/gcham_venvs"
mkdir -p "$ENV_DIR"
echo "Unpacking $GC_ARCHIVE to $ENV_DIR"
tar --use-compress-program="zstd -d -T0" -xf "$GC_ARCHIVE" -C "$ENV_DIR"
echo "$(find "$ENV_DIR" -maxdepth 1 -name 'gcham_venv_*' | wc -l) environments ready"

# The venvs record absolute paths, so they must be bound at the same container path
# they were built at (/app/.dataset_venvs).
"$CONTAINER_BIN" exec --cleanenv \
    "${dataset_binds[@]}" \
    "${nltk_binds[@]}" \
    "${librosa_binds[@]}" \
    --bind "$ENV_DIR:/app/.dataset_venvs" \
    --bind "$(dirname "$SOLUTION"):/work" \
    ${http_proxy:+--env http_proxy="$http_proxy"} \
    ${https_proxy:+--env https_proxy="$https_proxy"} \
    ${no_proxy:+--env no_proxy="$no_proxy" --env NO_PROXY="$no_proxy"} \
    "$GC_SIF" bash -c '
        # See gitchameleon/container.py for why the image needs this environment.
        # PATH/PYTHONPATH are set explicitly because singularity 3.x --cleanenv drops
        # the environment baked into the image, which is where poetry lives. In
        # particular HOME must be writable and must not be /app: some tests write to
        # relative paths, and /app is read-only under Apptainer.
        export PATH=/root/.local/bin:$PATH PYTHONPATH=/app
        export PYENV_VERSION=3.9.19 POETRY_CACHE_DIR=/root/.cache/pypoetry NLTK_DATA='"$nltk_path"'
        HOME="$(mktemp -d "${TMPDIR:-/tmp}/gitchameleon-XXXXXX")"; export HOME
        cd "$HOME" && poetry -C /app run python /app/gitchameleon/run_eval.py \
            --dataset_file /app/dataset.jsonl --solution_file /work/'"$(basename "$SOLUTION")"' \
            --env_dir /app/.dataset_venvs --test_dir /app/hidden_tests --workers '"$WORKERS"'
    '

echo "Results: ${SOLUTION%.*}_eval_results.csv"
