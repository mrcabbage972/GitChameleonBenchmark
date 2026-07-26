#!/bin/bash
# Build a wheel on a login node for a package the compute nodes cannot build themselves.
#
# A few of the dataset's pinned versions predate wheels for their Python version, so pip
# builds them from source — and those builds fetch vendored C libraries (matplotlib
# 3.4.0 downloads freetype from sourceforge) from hosts that some site proxies block.
# Login nodes usually have unrestricted egress, so build the wheel there once; the venv
# build job picks it up via PIP_FIND_LINKS.
#
#   scripts/slurm/prebuild_wheel.sh 3.10 matplotlib==3.4.0
#
set -euo pipefail

PY_SERIES="${1:?usage: prebuild_wheel.sh <3.7|3.9|3.10> <package==version>}"
SPEC="${2:?usage: prebuild_wheel.sh <3.7|3.9|3.10> <package==version>}"

GC_ROOT="${GC_ROOT:-$SCRATCH/gitchameleon}"
GC_SIF="${GC_SIF:-$GC_ROOT/containers/gitchameleon.sif}"
GC_WHEELHOUSE="${GC_WHEELHOUSE:-$GC_ROOT/wheelhouse}"

case "$PY_SERIES" in
    3.7) PY_FULL=3.7.17 ;;
    3.9) PY_FULL=3.9.19 ;;
    3.10) PY_FULL=3.10.14 ;;
    *) echo "unsupported python series '$PY_SERIES' (expected 3.7, 3.9 or 3.10)" >&2; exit 2 ;;
esac

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
mkdir -p "$GC_WHEELHOUSE"

echo "Building $SPEC for python $PY_FULL into $GC_WHEELHOUSE"
"$CONTAINER_BIN" exec --cleanenv \
    --bind "$GC_WHEELHOUSE:/wheelhouse" \
    "$GC_SIF" bash -c '
        set -e
        HOME="$(mktemp -d "${TMPDIR:-/tmp}/gitchameleon-XXXXXX")"; export HOME
        cd "$HOME"
        # The image pythons have no `wheel`, and these old packages build through the
        # legacy setup.py path, which needs it for bdist_wheel.
        "/root/.pyenv/versions/'"$PY_FULL"'/bin/python" -m venv "$HOME/venv"
        "$HOME/venv/bin/python" -m pip install -q --upgrade pip wheel setuptools
        "$HOME/venv/bin/python" -m pip wheel --no-deps --wheel-dir /wheelhouse "'"$SPEC"'"
    '
ls -l "$GC_WHEELHOUSE"
