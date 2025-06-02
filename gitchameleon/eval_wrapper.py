import argparse
import subprocess
import sys
from pathlib import Path

from gitchameleon.utils import default_num_workers


def main():
    """
    A Python script for running the GitChameleon evaluation inside a Docker container.
    """
    parser = argparse.ArgumentParser(
        description="Run the gitchameleon evaluation inside a Docker container.",
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
        "--docker-image", type=str, default="mrcabbage972/gitchameleon", help="Name of the Docker image to use"
    )
    parser.add_argument("--docker-tag", type=str, default="latest", help="Tag of the Docker image to use")

    args = parser.parse_args()

    solution_path_host = args.solution_path.resolve()
    if not solution_path_host.is_file():
        print(f"Error: Solution file not found at '{solution_path_host}'")
        sys.exit(1)

    output_csv_host_path = solution_path_host.parent / f"{solution_path_host.stem}_eval_results.csv"
    output_csv_host_path.touch(exist_ok=True)

    dataset_venvs_dir = Path("./.dataset_venvs")
    dataset_venvs_host_dir = dataset_venvs_dir.resolve()
    if not dataset_venvs_host_dir.is_dir():
        print(f"Warning: Dataset venvs directory not found at '{dataset_venvs_host_dir}'.")

    print(f"Solution file (host): {solution_path_host}")

    docker_command = [
        "docker",
        "run",
        "--rm",
        "-it",
        # Mount the solution file (read-only)
        "-v",
        f"{solution_path_host}:/app/solution.jsonl:ro",
        # Mount the dataset virtual environments
        "-v",
        f"{dataset_venvs_host_dir}:/app/.dataset_venvs",
        # Mount the target output file
        "-v",
        f"{output_csv_host_path}:/app/solution_eval_results.csv",
        # Set the image and tag
        f"{args.docker_image}:{args.docker_tag}",
        # The command to execute inside the container
        f'-c "pyenv global 3.9 && poetry run python gitchameleon/run_eval.py --dataset_file dataset.jsonl --solution_file solution.jsonl --env_dir .dataset_venvs --test_dir hidden_tests --workers {args.workers}"',
    ]

    try:
        subprocess.run(" ".join(docker_command), check=True, shell=True)
        print(f"Evaluation finished. Output CSV should be at: {output_csv_host_path}")
    except FileNotFoundError:
        print("Error: 'docker' command not found. Is Docker installed and in your system's PATH?")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"\n--- Docker command failed with exit code {e.returncode}. ---")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
