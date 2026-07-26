import argparse
import subprocess
import sys
from pathlib import Path

from gitchameleon.container import (
    APPTAINER,
    DOCKER,
    RUNTIMES,
    Mount,
    build_run_command,
    detect_runtime,
    poetry_run,
    wrap_command,
)
from gitchameleon.utils import default_num_workers

DEFAULT_SIF = "containers/gitchameleon.sif"


def main():
    """
    A Python script for running the GitChameleon evaluation inside a container.
    """
    parser = argparse.ArgumentParser(
        description="Run the gitchameleon evaluation inside a container (Docker or Apptainer).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--solution-path", type=Path, required=True, help="Absolute path to the solution file on the host machine"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=default_num_workers(),
        help="Number of threads to use",
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
    parser.add_argument(
        "--sif",
        type=Path,
        default=Path(DEFAULT_SIF),
        help="Path to the Apptainer image (ignored unless the runtime is apptainer)",
    )
    parser.add_argument(
        "--env-dir",
        type=Path,
        default=Path(".dataset_venvs"),
        help="Host directory holding the dataset venvs",
    )

    args = parser.parse_args()

    runtime = detect_runtime() if args.runtime == "auto" else args.runtime

    solution_path_host = args.solution_path.resolve()
    if not solution_path_host.is_file():
        print(f"Error: Solution file not found at '{solution_path_host}'")
        sys.exit(1)

    output_csv_host_path = solution_path_host.parent / f"{solution_path_host.stem}_eval_results.csv"

    print(f"Solution file (host): {solution_path_host}")
    print(f"Container runtime: {runtime}")

    if runtime == DOCKER:
        command = _docker_invocation(args, solution_path_host, output_csv_host_path)
    else:
        command = _apptainer_invocation(args, solution_path_host)

    try:
        subprocess.run(command, check=True)
        print(f"Evaluation finished. Output CSV should be at: {output_csv_host_path}")
    except FileNotFoundError:
        print(f"Error: '{command[0]}' command not found. Is it installed and in your system's PATH?")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"\n--- {runtime} command failed with exit code {e.returncode}. ---")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)


def _run_eval(runtime: str, solution_file: str, workers: int) -> str:
    return (
        f"{poetry_run(runtime)} python /app/gitchameleon/run_eval.py "
        f"--dataset_file /app/dataset.jsonl --solution_file {solution_file} "
        f"--env_dir /app/.dataset_venvs --test_dir /app/hidden_tests --workers {workers}"
    )


def _docker_invocation(args, solution_path_host: Path, output_csv_host_path: Path) -> list[str]:
    # Docker runs as root, so pre-create the output file to keep it owned by the caller.
    output_csv_host_path.touch(exist_ok=True)

    env_dir_host = args.env_dir.resolve()
    if not env_dir_host.is_dir():
        print(f"Warning: Dataset venvs directory not found at '{env_dir_host}'.")

    mounts = [
        Mount(solution_path_host, "/app/solution.jsonl", read_only=True),
        Mount(env_dir_host, "/app/.dataset_venvs"),
        Mount(output_csv_host_path, "/app/solution_eval_results.csv"),
    ]
    command = wrap_command(DOCKER, _run_eval(DOCKER, "/app/solution.jsonl", args.workers))
    return build_run_command(
        DOCKER,
        f"{args.docker_image}:{args.docker_tag}",
        command,
        mounts=mounts,
    )


def _apptainer_invocation(args, solution_path_host: Path) -> list[str]:
    sif = args.sif.resolve()
    if not sif.is_file():
        print(f"Error: Apptainer image not found at '{sif}'. Build it with 'make apptainer-build'.")
        sys.exit(1)

    # Apptainer runs as the invoking user, so results can be written straight into a
    # bind-mounted work directory without leaving root-owned files behind. run_eval.py
    # derives the CSV name from the solution path, so it lands next to it on the host.
    mounts = [Mount(solution_path_host.parent, "/work")]

    env_dir_host = args.env_dir.resolve()
    if not env_dir_host.is_dir():
        print(f"Warning: Dataset venvs directory not found at '{env_dir_host}'.")
    mounts.append(Mount(env_dir_host, "/app/.dataset_venvs"))

    command = wrap_command(
        APPTAINER,
        _run_eval(APPTAINER, f"/work/{solution_path_host.name}", args.workers),
    )
    return build_run_command(
        APPTAINER,
        str(sif),
        command,
        mounts=mounts,
    )


if __name__ == "__main__":
    main()
