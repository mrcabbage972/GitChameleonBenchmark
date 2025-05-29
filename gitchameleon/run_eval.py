#!/usr/bin/env python3
import argparse
import json
import os
import py_compile
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from tqdm import tqdm

from gitchameleon.eval_sample import eval_sample


def run_script(env_path, py_file="temp.py"):
    python_executable = os.path.join(env_path, "bin", "python")
    if py_file is None:
        return False, False, "", ""

    try:
        with open(py_file, "r") as file:
            file.read()
    except Exception as e:
        print(py_file, type(py_file))
        print("Error at py_file open:", e)

    error_log = ""
    try:
        # Try to compile the temporary file
        py_compile.compile(py_file, doraise=True)
        compile_code = 0  # Compilation successful
    except py_compile.PyCompileError as e:
        compile_code = 1  # Compilation failed due to a syntax error
        error_log = str(e)
    if compile_code == 0:
        # Run the Python script within the virtual environment
        command = [python_executable, py_file]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=120)
            exit_code = result.returncode
            error_log = result.stderr
        except subprocess.TimeoutExpired as e:
            print(e)
            exit_code = 1
            error_log = "TimeoutError"
    else:
        exit_code = 1  # since Compilation failed, the script will not run
    try:
        os.remove(py_file)
    except Exception as e:
        print(e)
    result = {
        "compiled_manual": bool(1 - compile_code),
        "passed_manual": bool(1 - exit_code),
        "output_manual": error_log,
    }
    return result  # 1 = pass, 0 = fail


def extract_code(text: str) -> str:
    """Parse raw string into python code"""
    try:
        match = re.search(r"```python(.*?)```", text, re.DOTALL)
    except Exception:
        try:
            match = re.search(r"```(.*?)```", rf"{text}", re.DOTALL)  # anthropic
        except Exception as e:
            print("Error: ", e)
            match = None
    return match.group(1) if match else text


def get_solution(record):
    solution = record.get("answer", "")
    if solution == "":
        solution = record.get("solution", "")
    if solution == "":
        solution = record.get("output", "")
    if solution == "":
        raise ValueError("No solution found in record")
    return extract_code(solution)


def get_example_id(record):
    id = record.get("example_id", "")
    if id == "":
        id = record.get("sample_idx", "")
    if id == "":
        raise ValueError("No example_id found in record")
    return id


def process_record(idx, record, manual_tests, env_dir, test_dir):
    """
    Process one JSON record: run eval_sample() and return a dict
    with example_id, code_id, output, passed, compiled, and idx.
    """
    example_id = get_example_id(record)
    try:
        example_id = int(example_id)
        manual_test = manual_tests[example_id]
        solution = get_solution(record)
        env_path = os.path.join(env_dir, f"gcham_venv_{example_id}")

        test_file_path = os.path.join(test_dir, f"test_sample_{example_id}.py")
        with open(test_file_path, "r") as tf:
            test_file_content = tf.read()

        code_dict = {
            "test_file": test_file_content,
            "codes": {"solution_code": {"code": solution}},
        }
        eval_res = eval_sample(example_id, env_path, code_dict)["codes"]["solution_code"]
        res = {
            "idx": idx,
            "example_id": example_id,
            "code_id": "solution_code",
            "output": eval_res.get("output", "").strip(),
            "passed": eval_res.get("pass", False),
            "compiled": eval_res.get("compile", True),
        }
    except Exception as e:
        print(f"Error processing record (hidden) {idx}: {e}")
        res = {
            "idx": idx,
            "example_id": example_id,
            "code_id": "solution_code",
            "output": f"Error: {e}",
            "passed": False,
            "compiled": False,
        }
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            test_code = solution + "\n" + manual_test
            test_file = os.path.join(temp_dir, f"manual_test_sample_{example_id}.py")
            with open(test_file, "w") as f:
                f.write(test_code)
            eval_res_manual = run_script(env_path, test_file)
        res.update(
            {
                "output_manual": eval_res_manual.get("output_manual", "").strip(),
                "passed_manual": eval_res_manual.get("passed_manual", False),
                "compiled_manual": eval_res_manual.get("compiled_manual", True),
            }
        )

    except Exception as e:
        print(f"Error processing record (visible) {idx}: {e}")
        res.update(
            {
                "output_manual": f"Error: {e}",
                "passed_manual": False,
                "compiled_manual": False,
            }
        )
    return res


def load_manual_tests(dataset_file_path: str) -> dict[int, str]:
    manual_tests = {}
    with open(dataset_file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data = json.loads(line)
                manual_tests[int(data["example_id"])] = data["test"]
    return manual_tests


def load_solutions(solution_path: str) -> list[str]:
    outputs = []
    with open(solution_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                outputs.append(json.loads(line))
    return outputs


def verify_solutions(manual_tests, solutions, env_dir, test_dir, max_workers) -> pd.DataFrame:
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as exe:
        futures = [
            exe.submit(
                process_record,
                idx,
                rec,
                manual_tests,
                env_dir,
                test_dir,
            )
            for idx, rec in enumerate(solutions)
        ]
        for fut in tqdm(as_completed(futures), total=len(futures), desc="Evaluating"):
            results.append(fut.result())

        # Sort back into original order
        results.sort(key=lambda row: row["idx"])
        # Build DataFrame, drop the helper idx column
        df = pd.DataFrame(results).drop(columns=["idx"])
        return df


def print_summary_stats(results_df: pd.DataFrame):
    # fraction passed
    passed = results_df["passed"].sum()
    total = len(results_df)
    print(f"[✓] {passed}/{total} tests passed (hidden) ({passed / total:.2%})")
    compiled = results_df["compiled"].sum()
    print(f"[✓] {compiled}/{total} tests compiled (hidden) ({compiled / total:.2%})")

    # fraction passed manual
    passed_manual = results_df["passed_manual"].sum()
    total_manual = len(results_df)
    print(f"[✓] {passed_manual}/{total_manual} tests passed (visible) ({passed_manual / total_manual:.2%})")
    compiled_manual = results_df["compiled_manual"].sum()
    print(f"[✓] {compiled_manual}/{total_manual} tests compiled (visible) ({compiled_manual / total_manual:.2%})")


def get_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Process a JSONL file in parallel with eval_sample and save results.")
    parser.add_argument("dataset_file", help="Path to the dataset JSONL file.")
    parser.add_argument("solution_file", help="Path to the solutions JSONL file to evaluate.")
    parser.add_argument("env_dir", help="Path to the dir where environments live")
    parser.add_argument("test_dir", help="Path to the dir where test files are stored")
    parser.add_argument(
        "--workers",
        type=int,
        default=os.cpu_count() or 4,
        help="Number of threads to use (default: CPU count)",
    )
    return parser


def main():
    parser = get_arg_parser()
    args = parser.parse_args()

    manual_tests = load_manual_tests(args.dataset_file)
    solutions = load_solutions(args.solution_file)

    results_df = verify_solutions(manual_tests, solutions, args.env_dir, args.test_dir, args.max_workers)

    # Save CSV
    output_csv = os.path.splitext(args.jsonl_file)[0] + "_eval_results.csv"
    results_df.to_csv(output_csv, index=False)
    print(f"[✓] Saved results to {output_csv}")

    print_summary_stats(results_df)


if __name__ == "__main__":
    main()
