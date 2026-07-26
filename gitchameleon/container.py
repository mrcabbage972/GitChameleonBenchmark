"""Container-runtime abstraction for the GitChameleon harness.

The harness runs the dataset environments inside a container so that the pyenv
interpreters (3.7 / 3.9 / 3.10) and the per-problem venvs are reproducible. Docker is
the default, but HPC clusters almost never allow it and provide Apptainer (formerly
Singularity) instead, so both runtimes are supported here behind one interface.

The two runtimes differ in more than command syntax:

* Docker runs the image read-write as root, so ``pyenv global`` (which writes
  ``$PYENV_ROOT/version``) and poetry's ``$HOME``-keyed venv lookup both work as-is, and
  the working directory ``/app`` is writable.
* Apptainer runs the image **read-only** as the invoking user, with the host ``$HOME``
  bind-mounted over the image's. So ``pyenv global`` fails on a read-only filesystem;
  poetry cannot find the venv that ``poetry install`` created under ``/root`` at image
  build time; and anything a test writes to a relative path or to ``$HOME`` fails too.
  A handful of the dataset's problems do exactly that (gradio, for one, does
  ``os.makedirs("flagged")`` at import). The fix is to select the interpreter with
  ``PYENV_VERSION`` (which writes nothing), point poetry and nltk at the image's copies
  explicitly, and run from a writable scratch ``HOME`` instead of ``/app``.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

DOCKER = "docker"
APPTAINER = "apptainer"
RUNTIMES = (DOCKER, APPTAINER)

# `pyenv global 3.9` resolves a prefix, but PYENV_VERSION needs the exact version that
# the image installed. Keep in sync with the Dockerfile's `pyenv install` lines.
PYENV_VERSIONS = {"3.7": "3.7.17", "3.9": "3.9.19", "3.10": "3.10.14"}

# Paths baked into the image at build time. `poetry install --no-root` and
# `nltk.download(...)` both run as root, so their output lives under /root no matter who
# runs the container later.
IMAGE_POETRY_CACHE = "/root/.cache/pypoetry"
IMAGE_NLTK_DATA = "/root/nltk_data"
IMAGE_POETRY_BIN = "/root/.local/bin"
APP_DIR = "/app"


@dataclass(frozen=True)
class Mount:
    """A host path exposed inside the container."""

    host: Path
    container: str
    read_only: bool = False


def available_runtimes() -> list[str]:
    """Runtimes whose client binary is on PATH (does not check the Docker daemon)."""
    found = []
    if shutil.which("docker"):
        found.append(DOCKER)
    if apptainer_binary():
        found.append(APPTAINER)
    return found


def apptainer_binary() -> Optional[str]:
    """Return the apptainer/singularity binary on PATH, if any."""
    for candidate in ("apptainer", "singularity"):
        path = shutil.which(candidate)
        if path:
            return path
    return None


def detect_runtime() -> str:
    """Pick a runtime: a *usable* Docker if present, else Apptainer, else Docker.

    Docker being on PATH is not enough — on a cluster login node it is common to have a
    docker client with no daemon it can reach, in which case Apptainer is the right
    answer. Falling back to Docker when neither is available keeps the original error
    message ("is Docker installed?") for users who have set up nothing at all.
    """
    if shutil.which("docker") and _docker_daemon_reachable():
        return DOCKER
    if apptainer_binary():
        return APPTAINER
    return DOCKER


def _docker_daemon_reachable() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def wrap_command(runtime: str, command: str, python_version: str = "3.9") -> str:
    """Prefix a harness command with the runtime-specific environment setup.

    ``command`` must refer to files by absolute path (``/app/...``): under Apptainer the
    working directory is deliberately *not* ``/app``.
    """
    if runtime == DOCKER:
        return f"pyenv global {python_version} && {command}"
    pyenv_version = PYENV_VERSIONS.get(python_version, python_version)
    # See the module docstring for why each of these is needed. HOME doubles as the
    # working directory so that tests writing to a relative path land somewhere
    # writable; on SLURM, TMPDIR is node-local disk.
    return (
        # PATH and PYTHONPATH are set explicitly because singularity 3.x --cleanenv drops
        # the image's own environment, and poetry lives in /root/.local/bin.
        f"export PATH={IMAGE_POETRY_BIN}:$PATH PYTHONPATH={APP_DIR} "
        f"PYENV_VERSION={pyenv_version} "
        f"POETRY_CACHE_DIR={IMAGE_POETRY_CACHE} NLTK_DATA={IMAGE_NLTK_DATA}; "
        'HOME="$(mktemp -d "${TMPDIR:-/tmp}/gitchameleon-XXXXXX")"; export HOME; '
        f'cd "$HOME" && {command}'
    )


def poetry_run(runtime: str) -> str:
    """The `poetry run` prefix for a harness command.

    ``-C`` is needed under Apptainer, where the working directory is not the project
    root; it is harmless under Docker, whose WORKDIR already is ``/app``.
    """
    return f"poetry -C {APP_DIR} run" if runtime == APPTAINER else "poetry run"


def build_run_command(
    runtime: str,
    image: str,
    command: str,
    mounts: Sequence[Mount] = (),
    env: Optional[dict[str, str]] = None,
    interactive: bool = True,
) -> list[str]:
    """Build the argv that runs ``command`` (a shell snippet) inside ``image``.

    ``image`` is ``name:tag`` for Docker and a path to a ``.sif`` for Apptainer.
    """
    if runtime == DOCKER:
        return _docker_command(image, command, mounts, env, interactive)
    if runtime == APPTAINER:
        return _apptainer_command(image, command, mounts, env)
    raise ValueError(f"unknown container runtime '{runtime}' (expected one of {', '.join(RUNTIMES)})")


def _docker_command(
    image: str,
    command: str,
    mounts: Sequence[Mount],
    env: Optional[dict[str, str]],
    interactive: bool,
) -> list[str]:
    argv = ["docker", "run", "--rm"]
    if interactive:
        argv.append("-it")
    for mount in mounts:
        spec = f"{mount.host}:{mount.container}"
        if mount.read_only:
            spec += ":ro"
        argv += ["-v", spec]
    for key, value in (env or {}).items():
        argv += ["-e", f"{key}={value}"]
    # The image's entrypoint is /bin/bash, so the command is passed as bash arguments.
    argv += [image, "-c", command]
    return argv


def _apptainer_command(
    image: str,
    command: str,
    mounts: Sequence[Mount],
    env: Optional[dict[str, str]],
) -> list[str]:
    binary = apptainer_binary() or "apptainer"
    # --cleanenv keeps the host environment (notably PYTHONPATH, VIRTUAL_ENV and a
    # module-system PATH) from leaking in and shadowing the image's interpreters.
    argv = [binary, "exec", "--cleanenv"]
    for mount in mounts:
        spec = f"{mount.host}:{mount.container}"
        if mount.read_only:
            spec += ":ro"
        argv += ["--bind", spec]
    for key, value in (env or {}).items():
        argv += ["--env", f"{key}={value}"]
    argv += [image, "bash", "-c", command]
    return argv
