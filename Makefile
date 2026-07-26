DOCKER_IMAGE := gc
DOCKER_TAG := 1.0

REMOTE_DOCKER_IMAGE := mrcabbage972/gitchameleon
REMOTE_DOCKER_TAG := latest

PYTHON_VERSION ?= 3.9

# ---- Apptainer (HPC clusters, where Docker is not available) ----
APPTAINER ?= apptainer
SIF ?= containers/gitchameleon.sif
# A venv tree is ~1M small files, which blows through the file-count quota of most
# cluster filesystems. Build it on node-local disk and keep it on the shared filesystem
# as a single archive instead.
VENV_DIR ?= .dataset_venvs
VENV_ARCHIVE ?= venvs.tar.zst
PIP_CACHE ?= .pip-cache
VENV_CONCURRENCY ?= 8

# Conditional logic to determine which Docker image/tag to use in run-eval
# If USE_LOCAL_DOCKER is set to 1, use the local image. Otherwise, use the remote.
ifeq ($(USE_LOCAL_DOCKER),1)
    FINAL_DOCKER_IMAGE := $(DOCKER_IMAGE)
    FINAL_DOCKER_TAG := $(DOCKER_TAG)
else
    FINAL_DOCKER_IMAGE := $(REMOTE_DOCKER_IMAGE)
    FINAL_DOCKER_TAG := $(REMOTE_DOCKER_TAG)
endif

.PHONY: docker-run

# This target will only run docker build if FORCE_DOCKER_BUILD is set
conditional-docker-build:
ifeq ($(FORCE_DOCKER_BUILD),1)
	@echo "FORCE_DOCKER_BUILD is set. Building Docker image..."
	$(MAKE) docker-build
else
	@echo "FORCE_DOCKER_BUILD is not set. Skipping Docker image build for evals-setup."
	@echo "To force build, run: make evals-setup FORCE_DOCKER_BUILD=1"
endif

docker-build:
	docker build . -t $(DOCKER_IMAGE):$(DOCKER_TAG)

docker-run:
	docker run --rm -it -v "./.dataset_venvs:/app/.dataset_venvs" $(FINAL_DOCKER_IMAGE):$(FINAL_DOCKER_TAG) -c "pyenv global $(PYTHON_VERSION) && exec bash"

evals-setup: conditional-docker-build build-venvs

build-venvs:
	docker run --rm -it -v "./.dataset_venvs:/app/.dataset_venvs" $(FINAL_DOCKER_IMAGE):$(FINAL_DOCKER_TAG) -c "pyenv global $(PYTHON_VERSION) && poetry run python gitchameleon/create_venvs.py --start 0 --end 1000 --base_path .dataset_venvs --dataset dataset.jsonl"

# ---- Apptainer targets ----
# Usage on a cluster:
#   make apptainer-build                       # convert the published image to a .sif
#   make apptainer-venvs                       # build the 99 dataset venvs (needs PyPI)
#   make run-eval-apptainer SOLUTION_PATH=...  # evaluate
# On a SLURM cluster, drive the last two through scripts/slurm/ instead, so the venvs
# are built on node-local disk and shipped around as one archive.

apptainer-build:
	mkdir -p $(dir $(SIF))
	$(APPTAINER) build --force $(SIF) docker://$(REMOTE_DOCKER_IMAGE):$(REMOTE_DOCKER_TAG)

apptainer-venvs:
	poetry run build-venvs --runtime apptainer --sif $(SIF) --env-dir $(VENV_DIR) \
		--pip-cache $(PIP_CACHE) --concurrency $(VENV_CONCURRENCY)

# Pack/unpack the venv tree as a single file, to keep ~1M small files off a filesystem
# with a file-count quota (and to copy the environments between clusters).
apptainer-archive:
	tar --use-compress-program="zstd -T0 -3" -cf $(VENV_ARCHIVE) -C $(VENV_DIR) .

apptainer-unarchive:
	mkdir -p $(VENV_DIR)
	tar --use-compress-program="zstd -d -T0" -xf $(VENV_ARCHIVE) -C $(VENV_DIR)

apptainer-shell:
	$(APPTAINER) shell --cleanenv --bind $(VENV_DIR):/app/.dataset_venvs $(SIF)

evals-setup-apptainer: apptainer-build apptainer-venvs

run-eval-apptainer:
	@if [ -z "$(SOLUTION_PATH)" ]; then \
	  echo "Usage: make run-eval-apptainer SOLUTION_PATH=<an absolute path to the solution file>"; exit 1; \
	else \
	  poetry run evaluate --runtime apptainer --sif $(SIF) --env-dir $(VENV_DIR) \
	    --solution-path $(SOLUTION_PATH); \
	fi

lint-all: format ruff-fix sort-imports pyright

format:
	poetry run ruff format

pyright:
	poetry run pyright

ruff-fix:
	poetry run ruff check . --fix

sort-imports:
	poetry run ruff check --select I --fix

run-eval:
	@if [ -z "$(SOLUTION_PATH)" ]; then \
	  echo "Usage: make run-eval SOLUTION_PATH=<an absolute path to the solution file>"; exit 1; \
	else \
	  echo "Using Docker image: $(FINAL_DOCKER_IMAGE):$(FINAL_DOCKER_TAG)"; \
	  python gitchameleon/eval_wrapper.py --solution-path $(SOLUTION_PATH) --docker-image $(FINAL_DOCKER_IMAGE) --docker-tag $(FINAL_DOCKER_TAG) \
	fi
	