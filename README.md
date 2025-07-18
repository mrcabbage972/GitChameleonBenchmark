<p align="center">
  <img src="./images/gc-icon.png"
       alt="GitChameleon icon"
       width="120"
       style="margin:0 0 1em 0;">
</p>

# GitChameleon


This is an evaluation harness for **GitChameleon**, an AI coding benchmark that comprises 328 Python-based problems tha are conditioned on specific versions of popular libraries for scientific computing and web development.

[![CI](https://github.com/mrcabbage972/GitChameleonBenchmark/actions/workflows/ci.yaml/badge.svg?branch=main)](https://github.com/mrcabbage972/GitChameleonBenchmark/actions/workflows/ci.yaml)
![Python](https://img.shields.io/badge/python-3.9-blue.svg)

## 🚀 Usage
### 📦 Prerequisites
Before you begin, ensure you have the following installed:
1. [Python 3.9+](https://www.python.org/downloads/)
1. [Poetry](https://python-poetry.org/docs/)
1. [Docker](https://docs.docker.com/get-started/get-docker/)

### 🏗️ Harness Setup
1. Clone the repository:
```
git clone https://github.com/mrcabbage972/GitChameleonBenchmark.git
```
2. Run the setup command:
```
make evals-setup
```

### ▶️ Running Evaluation
To evaluate your solution, execute the following command:
```
evaluate --solution-path SOLUTION_PATH [--workers WORKERS] 
```

The success rates will be printed out and detailed logs will be written to an output file next to the solution file.

## 🐞 Reporting Issues

If you run into any bugs or have trouble using **GitChameleon**, please open an issue on GitHub so we can help:

[![Issues](https://img.shields.io/github/issues/mrcabbage972/GitChameleonBenchmark.svg)](https://github.com/mrcabbage972/GitChameleonBenchmark/issues)

Before opening a new issue, please search the existing issues to see if someone else has already reported your problem. When you do file an issue, include:

1. **What you expected to happen**  
2. **What actually happened** (error messages, stack traces, screenshots)  
3. **Steps to reproduce** (a minimal code example or command)  
4. **Your environment** (OS, Python version, GitChameleon commit hash)

That extra detail helps us diagnose and fix things much faster.


## 📚 Citation
```
@misc{misra2025gitchameleonevaluatingaicode,
      title={GitChameleon: Evaluating AI Code Generation Against Python Library Version Incompatibilities}, 
      author={Diganta Misra and Nizar Islah and Victor May and Brice Rauby and Zihan Wang and Justine Gehring and Antonio Orvieto and Muawiz Chaudhary and Eilif B. Muller and Irina Rish and Samira Ebrahimi Kahou and Massimo Caccia},
      year={2025},
      eprint={2507.12367},
      archivePrefix={arXiv},
      primaryClass={cs.SE},
      url={https://arxiv.org/abs/2507.12367}, 
}
```
