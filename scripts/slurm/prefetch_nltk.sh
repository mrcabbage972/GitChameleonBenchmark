#!/bin/bash
# Download the NLTK corpora the dataset needs, on a login node, into a directory the
# eval job binds into the container.
#
# The image pre-downloads punkt, wordnet and omw-1.4 at build time, but one solution
# (example 96) calls nltk.download("sinica_treebank") at import. On a compute node that
# download goes through the site proxy and fails, and the test then cannot load the
# corpus. Fetching it here once avoids depending on the network at eval time.
#
#   scripts/slurm/prefetch_nltk.sh [corpus ...]
#
set -euo pipefail

GC_ROOT="${GC_ROOT:-$SCRATCH/gitchameleon}"
SIF="${GC_SIF:-$GC_ROOT/containers/gitchameleon.sif}"
NLTK_DIR="${GC_NLTK_DATA:-$GC_ROOT/nltk_data}"
CORPORA=("${@:-sinica_treebank punkt wordnet omw-1.4}")

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

mkdir -p "$NLTK_DIR"
echo "Downloading ${CORPORA[*]} into $NLTK_DIR"

"$CONTAINER_BIN" exec --cleanenv \
    --bind "$NLTK_DIR:/nltk_data" \
    ${http_proxy:+--env http_proxy="$http_proxy"} \
    ${https_proxy:+--env https_proxy="$https_proxy"} \
    "$SIF" bash -c '
        set -e
        export PATH=/root/.local/bin:$PATH PYTHONPATH=/app
        export PYENV_VERSION=3.9.19 POETRY_CACHE_DIR=/root/.cache/pypoetry
        HOME="$(mktemp -d "${TMPDIR:-/tmp}/gitchameleon-XXXXXX")"; export HOME
        cd "$HOME"
        "/root/.pyenv/versions/3.9.19/bin/python" -m venv nlv
        ./nlv/bin/pip install -q nltk
        for c in '"${CORPORA[*]}"'; do
            ./nlv/bin/python -m nltk.downloader -d /nltk_data "$c"
        done
    '
ls "$NLTK_DIR"
