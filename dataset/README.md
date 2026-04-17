---
license: mit
language:
  - en
  - code
task_categories:
  - text-generation
  - question-answering
tags:
  - code
  - benchmark
  - python
  - library-versioning
  - code-generation
  - evaluation
  - code-completion
  - llm-evaluation
  - version-compatibility
  - software-engineering
pretty_name: GitChameleon 2.0
size_categories:
  - n<1K
configs:
  - config_name: problems
    data_files:
      - split: train
        path: dataset.jsonl
  - config_name: solutions
    data_files:
      - split: train
        path: ground_truth_solutions.jsonl
---

# GitChameleon 2.0

GitChameleon 2.0 is an AI coding benchmark comprising **328 Python-based problems** conditioned on specific versions of popular libraries for scientific computing and web development. It evaluates whether AI code generation models can correctly use library APIs as they existed at a particular version — a challenging test of version-specific knowledge.

> **Note:** This is GitChameleon **2.0**, a distinct and newer work from the original GitChameleon benchmark. Please do not confuse the two.

**Project website:** [gitchameleon-2-0.github.io](https://gitchameleon-2-0.github.io) — paper, results, citation, and getting started guide.

Paper: [GitChameleon 2.0: Evaluating AI Code Generation Against Python Library Version Incompatibilities](https://arxiv.org/abs/2507.12367) (ACL 2026, Main)

## Example Task

Each problem provides a library version, a natural-language description, and a stub to complete:

> **Library:** `torch==1.9.0` | **Python:** 3.7
>
> **Problem:** Calculate the logarithm of the cumulative distribution function of the standard normal distribution using available functions. If not available in PyTorch, use another library.

```python
import torch
def log_ndtr(input_tensor: torch.Tensor) -> torch.Tensor:
    # your solution here
```

The model must produce a solution that passes the visible test:

```python
from scipy.stats import norm
input_tensor = torch.linspace(-10, 10, steps=20)
expected_result = torch.tensor([-5.3231e+01, ..., -7.6199e-24], dtype=torch.float64)
assert torch.allclose(log_ndtr(input_tensor), expected_result, rtol=1e-3, atol=1e-3)
```

This particular problem tests awareness that `torch.special.log_ndtr` was not available in `torch==1.9.0`, requiring the model to fall back to `scipy.stats.norm.logcdf`.

## Dataset Configs

| Config | Description | Rows |
|---|---|---|
| `problems` | Problem statements, starting code, solutions, and metadata | 328 |
| `solutions` | Ground-truth solutions keyed by `example_id` | 328 |

## Usage

```python
from datasets import load_dataset

# Load problems
ds = load_dataset("cabbage972/GitChameleon-2.0", "problems")

# Load ground-truth solutions
solutions = load_dataset("cabbage972/GitChameleon-2.0", "solutions")
```

## Schema

### `problems` config

| Field | Type | Description |
|---|---|---|
| `example_id` | string | Unique identifier (0–327) |
| `library` | string | Target Python library (e.g. `torch`, `scipy`, `flask`) |
| `version` | string | Library version the problem is conditioned on |
| `python_version` | string | Required Python version (`3.7`, `3.9`, or `3.10`) |
| `problem` | string | Natural-language task description |
| `starting_code` | string | Stub function/class definition to complete |
| `solution` | string | Reference solution |
| `test` | string | Visible pytest assertions |
| `functional` | int | 1 if the library is a scientific/functional library |
| `webdev` | int | 1 if the library is a web-development library |
| `solution_api_call` | bool | Whether the solution uses an API call |
| `api_calls` | list[string] | API calls used in the reference solution |
| `type_of_change` | string | Category of version change (e.g. `argument change`, `name change`) |
| `name_of_class_or_func` | string | Name of the target function or class |
| `additional_dependencies` | string | Extra packages required (e.g. `scipy==1.7.3`) |
| `extra_dependencies` | string | Additional optional dependencies (nullable) |
| `release_date` | string | Library release date (`YYYY-MM`) |
| `docs` | list[string] | Relevant documentation URLs |

### `solutions` config

| Field | Type | Description |
|---|---|---|
| `example_id` | string | Matches `example_id` in `problems` |
| `answer` | string | Complete function/class implementation |

## Running Evaluation

Evaluation is run via the [GitChameleonBenchmark](https://github.com/mrcabbage972/GitChameleonBenchmark) harness. Requirements: Python 3.9+, [Poetry](https://python-poetry.org/docs/), and [Docker](https://docs.docker.com/get-started/get-docker/).

```bash
git clone https://github.com/mrcabbage972/GitChameleonBenchmark.git
cd GitChameleonBenchmark
make evals-setup
evaluate --solution-path SOLUTION_PATH [--workers WORKERS]
```

Your solution file should be a JSONL where each line has `example_id` and `answer` fields (matching the `solutions` config schema above). Success rates are printed to stdout and detailed logs are written next to the solution file.

## Libraries Covered

26 libraries including: `torch`, `scipy`, `sympy`, `flask`, `falcon`, `numpy`, `scikit-learn`, `pandas`, `django`, `librosa`, and more.

## Citation

```bibtex
@misc{misra2025gitchameleon20evaluatingai,
      title={GitChameleon 2.0: Evaluating AI Code Generation Against Python Library Version Incompatibilities},
      author={Diganta Misra and Nizar Islah and Victor May and Brice Rauby and Zihan Wang and Justine Gehring and Antonio Orvieto and Muawiz Chaudhary and Eilif B. Muller and Irina Rish and Samira Ebrahimi Kahou and Massimo Caccia},
      year={2025},
      eprint={2507.12367},
      archivePrefix={arXiv},
      primaryClass={cs.SE},
      url={https://arxiv.org/abs/2507.12367},
}
```
