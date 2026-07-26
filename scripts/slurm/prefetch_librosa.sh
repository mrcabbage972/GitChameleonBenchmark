#!/bin/bash
# Download librosa's example audio on a login node, into a directory the eval job binds
# into the container.
#
# librosa.util.example_audio_file() fetches a clip from librosa.org at test time. Some
# site proxies refuse that host (rorqual returns 403), so the tests that use it fail on
# a compute node. Populating librosa's pooch cache here makes eval independent of it.
#
#   scripts/slurm/prefetch_librosa.sh
#
set -euo pipefail

GC_ROOT="${GC_ROOT:-$SCRATCH/gitchameleon}"
SIF="${GC_SIF:-$GC_ROOT/containers/gitchameleon.sif}"
LIBROSA_DIR="${GC_LIBROSA_DATA:-$GC_ROOT/librosa_data}"

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

mkdir -p "$LIBROSA_DIR"
echo "Fetching librosa example audio into $LIBROSA_DIR"

"$CONTAINER_BIN" exec --cleanenv \
    --bind "$LIBROSA_DIR:/librosa_data" \
    ${http_proxy:+--env http_proxy="$http_proxy"} \
    ${https_proxy:+--env https_proxy="$https_proxy"} \
    "$SIF" bash -c '
        set -e
        export LIBROSA_DATA_DIR=/librosa_data
        HOME="$(mktemp -d "${TMPDIR:-/tmp}/gitchameleon-XXXXXX")"; export HOME
        cd "$HOME"
        "/root/.pyenv/versions/3.9.19/bin/python" -m venv lv
        # Only pooch and the file layout matter here, not librosa itself working —
        # importing librosa 0.8 drags in numba, which fights over numpy versions.
        ./lv/bin/pip install -q pooch
        ./lv/bin/python -c "
import pooch
p = pooch.create(
    path=pooch.os_cache(\"librosa\"), base_url=\"https://librosa.org/data/audio/\",
    env=\"LIBROSA_DATA_DIR\", registry=None,
)
for name in (\"Kevin_MacLeod_-_Vibe_Ace.hq.ogg\", \"Kevin_MacLeod_-_Vibe_Ace.ogg\"):
    p.registry[name] = None
    print(p.fetch(name))
"
    '
find "$LIBROSA_DIR" -type f | head
