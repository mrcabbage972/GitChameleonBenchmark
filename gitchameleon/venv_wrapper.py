import argparse
import os
import subprocess
import sys
from pathlib import Path

from gitchameleon.container import (
    DOCKER,
    poetry_run,
    RUNTIMES,
    Mount,
    build_run_command,
    detect_runtime,
    wrap_command,
)

DEFAULT_SIF = "containers/gitchameleon.sif"


def main():
    """
    Build the per-problem dataset virtual environments inside a container.

    This is the setup step that `make evals-setup` performs; it is exposed as a CLI so
    that the Apptainer path (clusters) and the Docker path share one implementation.
    """
    parser = argparse.ArgumentParser(
        description="Create the GitChameleon dataset venvs inside a container (Docker or Apptainer).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--runtime",
        choices=("auto",) + RUNTIMES,
        default="auto",
        help="Container runtime. 'auto' uses Docker when its daemon is reachable, else Apptainer",
    )
    parser.add_argument(
        "--docker-image", type=str, default="mrcabbage972/gitchameleon", help="Name of the Docker image to use"
    )
    parser.add_argument("--docker-tag", type=str, default="latest", help="Tag of the Docker image to use")
    parser.add_argument("--sif", type=Path, default=Path(DEFAULT_SIF), help="Path to the Apptainer image")
    parser.add_argument(
        "--env-dir",
        type=Path,
        default=Path(".dataset_venvs"),
        help="Host directory to build the venvs in",
    )
    parser.add_argument(
        "--pip-cache",
        type=Path,
        default=None,
        help="Host directory to use as a shared pip cache; greatly speeds up repeated builds",
    )
    parser.add_argument("--start", type=int, default=0, help="First example id to build an environment for")
    parser.add_argument("--end", type=int, default=1000, help="Last example id to build an environment for")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=min(8, os.cpu_count() or 1),
        help="Number of environments to build in parallel",
    )

    args = parser.parse_args()
    runtime = detect_runtime() if args.runtime == "auto" else args.runtime
    print(f"Container runtime: {runtime}")

    inner = (
        f"{poetry_run(runtime)} python /app/gitchameleon/create_venvs.py "
        f"--start {args.start} --end {args.end} --base_path /app/.dataset_venvs "
        f"--dataset /app/dataset.jsonl --concurrency {args.concurrency}"
    )

    mounts = []
    env = {}
    if args.pip_cache:
        pip_cache = args.pip_cache.resolve()
        pip_cache.mkdir(parents=True, exist_ok=True)
        mounts.append(Mount(pip_cache, "/pip-cache"))
        env["PIP_CACHE_DIR"] = "/pip-cache"

    if runtime == DOCKER:
        env_dir_host = args.env_dir.resolve()
        env_dir_host.mkdir(parents=True, exist_ok=True)
        mounts.append(Mount(env_dir_host, "/app/.dataset_venvs"))
        image = f"{args.docker_image}:{args.docker_tag}"
    else:
        image = str(args.sif.resolve())
        if not Path(image).is_file():
            print(f"Error: Apptainer image not found at '{image}'. Build it with 'make apptainer-build'.")
            sys.exit(1)
        env_dir_host = args.env_dir.resolve()
        env_dir_host.mkdir(parents=True, exist_ok=True)
        mounts.append(Mount(env_dir_host, "/app/.dataset_venvs"))

    command = build_run_command(
        runtime,
        image,
        wrap_command(runtime, inner),
        mounts=mounts,
        env=env,
    )

    try:
        subprocess.run(command, check=True)
    except FileNotFoundError:
        print(f"Error: '{command[0]}' command not found. Is it installed and in your system's PATH?")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"\n--- {runtime} command failed with exit code {e.returncode}. ---")
        sys.exit(1)


if __name__ == "__main__":
    main()
