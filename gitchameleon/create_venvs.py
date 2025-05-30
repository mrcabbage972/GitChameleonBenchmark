import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from gitchameleon.utils import generate_venv_cache_key

# Mapping of Python versions to pyenv-installed versions
python_versions = {"3.7": "3.7.17", "3.9": "3.9.19", "3.10": "3.10.14"}


def install_pinpointed_package(
    package_name: str,
    python_version: str,
    python_executable: Path,
    deps_lower: list,
    version_mapping: dict,
    env_path: str,
):
    """
    Install a pinpointed package using the provided version mapping if the package is not
    already included in additional dependencies.
    """
    # Check if the package appears in additional dependencies
    if all(package_name not in dep for dep in deps_lower):
        package_spec = version_mapping.get(python_version)
        if package_spec:
            install_cmd = [
                python_executable,
                "-m",
                "pip",
                "install",
                package_spec,
                "--quiet",
            ]
            result = subprocess.run(
                install_cmd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if result.returncode == 0:
                print(
                    f"{package_name.capitalize()} installed successfully in {env_path} with version from mapping: {package_spec}"
                )
            else:
                print(f"Failed to install {package_name} in {env_path}: {result.stderr}")
        else:
            print(
                f"No {package_name} version mapping found for Python {python_version}. Skipping {package_name} installation."
            )


def create_virtual_environment(env_path, python_version, create_anyway=False, library_to_check=None, docker=True):
    """Create and return the path of a virtual environment."""
    python_executable = f"/root/.pyenv/versions/{python_version}/bin/python" if docker else "python"
    if not os.path.exists(python_executable):
        print(f"Python version {python_version} not found. Skipping {env_path}.")
        return

    if not os.path.exists(env_path):
        os.makedirs(env_path, exist_ok=True)
        subprocess.run([python_executable, "-m", "venv", "--copies", env_path], check=True)
        print(f"Virtual environment created: {env_path}")
    else:
        print(f"Virtual environment already exists: {env_path}")
        if create_anyway:
            subprocess.run(["rm", "-rf", env_path])
            os.makedirs(env_path, exist_ok=True)
            subprocess.run(
                [python_executable, "-m", "venv", "--copies", "--clear", env_path],
                check=True,
            )
            print(f"Virtual environment recreated: {env_path}")

    if library_to_check:
        python_exec = os.path.join(env_path, "bin", "python")
        result = subprocess.run(
            [python_exec, "-m", "pip", "show", library_to_check],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode == 0:
            print(f"Library '{library_to_check}' is installed in the virtual environment.")
        else:
            print(f"Library '{library_to_check}' is NOT installed in the virtual environment.")

    return env_path


def install_packages(env_path, library, version, additional_dependencies, python_version):
    """Install packages using the Python executable in the virtual environment."""
    python_executable = Path(env_path, "bin", "python")

    # Parse additional dependencies
    dependencies = additional_dependencies.split() if additional_dependencies else []
    pip_version = None
    other_dependencies = []

    # Separate pip version if specified
    for dep in dependencies:
        if dep.startswith("pip="):
            pip_version = dep.split("=")[1]
        elif dep.strip() and dep != "-":  # Filter out invalid entries
            other_dependencies.append(dep)

    # Upgrade pip to the specified version or the latest version
    if pip_version:
        pip_upgrade_cmd = [
            python_executable,
            "-m",
            "pip",
            "install",
            f"pip=={pip_version}",
            "--quiet",
        ]
    else:
        pip_upgrade_cmd = [
            python_executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "--quiet",
        ]
    subprocess.run(pip_upgrade_cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print(f"Pip upgraded in {env_path} to version {pip_version if pip_version else 'latest'}.")

    # Install the main library and other dependencies
    pip_install_cmd = [
        python_executable,
        "-m",
        "pip",
        "install",
        f"{library}=={version}",
        "--quiet",
    ] + other_dependencies

    print(f"Installing packages in {env_path}...")
    result = subprocess.run(pip_install_cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print(f"Failed to install packages in {env_path}: {result.stderr}")
        subprocess.run(["rm", "-rf", env_path])  # Clean up the environment if installation fails
    else:
        print(f"Packages installed successfully in {env_path}")

        deps_lower = [dep.lower() for dep in dependencies]
        if library.lower() != "pytest":
            pytest_versions = {
                "3.7": "pytest==6.2.5",
                "3.9": "pytest==7.1.2",
                "3.10": "pytest==7.2.0",
            }
            install_pinpointed_package(
                "pytest",
                python_version,
                python_executable,
                deps_lower,
                pytest_versions,
                env_path,
            )
            pytest_versions = {
                "3.7": "pytest-cov==4.1.0",
                "3.9": "pytest-cov==4.1.0",
                "3.10": "pytest-cov==4.1.0",
            }
            install_pinpointed_package(
                "pytest-cov",
                python_version,
                python_executable,
                deps_lower,
                pytest_versions,
                env_path,
            )
        if library.lower() != "numpy":
            numpy_versions = {
                "3.7": "numpy==1.21.6",
                "3.9": "numpy==1.21.6",
                "3.10": "numpy==1.23",
            }
            install_pinpointed_package(
                "numpy",
                python_version,
                python_executable,
                deps_lower,
                numpy_versions,
                env_path,
            )
        if library.lower() != "scipy":
            scipy_versions = {
                "3.7": "scipy==1.7.1",
                "3.9": "scipy==1.9.1",
                "3.10": "scipy==1.10.1",
            }
            install_pinpointed_package(
                "scipy",
                python_version,
                python_executable,
                deps_lower,
                scipy_versions,
                env_path,
            )

    return result.returncode


def generate_env_id(row):
    """Generate a unique ID based on library, version, and dependencies."""
    unique_str = f"{row['library']}-{row['version']}-{row['additional_dependencies']}"
    return hashlib.sha256(unique_str.encode()).hexdigest()[:8]


def process_line(key: str, sample: dict, start_id: int, end_id: int, create_anyway: bool, base_path: str) -> bool:
    python_version = sample["python_version"]
    example_id = sample["example_id"]
    library = sample["library"]
    version = sample["version"]
    additional_dependencies = sample.get("additional_dependencies", "") + " " + sample.get("extra_dependencies", "")
    if int(example_id) < start_id or int(example_id) > end_id:
        return True
    if python_version and example_id:
        pyenv_version = python_versions.get(python_version)
        if not pyenv_version:
            print(f"Unsupported Python version {python_version} for example {example_id}.")
            return False

        env_name = f"gcham_venv_{key}"
        env_path = Path(base_path, env_name)

        python_exec = Path(env_path, "bin", "python")
        if not os.path.exists(python_exec):
            print(f"Python executable not found for {example_id}. Creating environment...")
            create_virtual_environment(
                env_path,
                pyenv_version,
                create_anyway=create_anyway,
                library_to_check=library,
            )
            returncode = install_packages(
                env_path,
                library,
                version,
                additional_dependencies,
                python_version,
            )
            if returncode != 0:
                return False
        else:
            print(f"Environment already exists for {example_id}.")
            if args.install_pkgs:
                returncode = install_packages(
                    env_path,
                    library,
                    version,
                    additional_dependencies,
                    python_version,
                )
                if returncode != 0:
                    return False
    return True


def main(args):
    jsonl_file = args.dataset
    base_path = args.base_path
    create_anyway = args.create_anyway
    start_id = args.start
    end_id = args.end
    concurrency = args.concurrency

    # Ensure the base path exists
    os.makedirs(base_path, exist_ok=True)
    failed_count = []

    # Read the JSONL file and process only lines between start_id and end_id (inclusive)
    with open(jsonl_file, "r") as file:
        lines = file.readlines()

    samples = [json.loads(line) for line in lines]
    print(f"Found {len(samples)} lines in dataset")

    venv_key_map = {}
    for sample in samples:
        venv_key = generate_venv_cache_key(
            sample.get("python_version"),
            sample.get("library"),
            sample.get("version"),
            sample.get("additional_dependencies", ""),
        )
        if venv_key not in venv_key_map:
            venv_key_map[venv_key] = sample

    print(f"Creating {len(venv_key_map)} environments, using {args.concurrency} workers")

    failed_count = 0
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(process_line, key, sample, start_id, end_id, create_anyway, base_path)
            for key, sample in venv_key_map.items()
        ]
        for future in tqdm(as_completed(futures)):
            success = future.result()
            if not success:
                failed_count += 1

    print(f"Failed count: {failed_count}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=str, required=True, help="Path to the JSONL dataset file.")
    parser.add_argument(
        "--base_path",
        type=str,
        default=".dataset_venvs",
        help="Base path for virtual environments.",
    )
    parser.add_argument(
        "--create_anyway",
        action="store_true",
        default=False,
        help="Recreate environments if they already exist.",
    )
    parser.add_argument(
        "--install_pkgs",
        action="store_true",
        default=False,
        help="Install packages in the virtual environment.",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Start line number (inclusive) from which to create the environments.",
    )
    parser.add_argument(
        "--end",
        type=int,
        default=sys.maxsize,
        help="End line number (inclusive) until which to create the environments.",
    )

    parser.add_argument(
        "--concurrency",
        type=int,
        default=os.cpu_count(),
        help="The concurrency with which to create the environments.",
    )

    args = parser.parse_args()
    main(args)
