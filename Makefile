DOCKER_IMAGE := gc
DOCKER_TAG := 1.0

REMOTE_DOCKER_IMAGE := mrcabbage972/gitchameleon
REMOTE_DOCKER_TAG := latest

PYTHON_VERSION ?= 3.9

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
	docker run --rm -it -v "./.dataset_venvs:/app/.dataset_venvs" $(FINAL_DOCKER_IMAGE):$(FINAL_DOCKER_TAG) -c "pyenv global $(PYTHON_VERSION) && poetry run python gitchameleon/create_venvs.py --base_path .dataset_venvs --dataset dataset.jsonl"

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
	  python gitchameleon/eval_wrapper.py --solution-path $(SOLUTION_PATH) --docker-image $(FINAL_DOCKER_IMAGE) --docker-tag $(FINAL_DOCKER_TAG) --python-version $(PYTHON_VERSION); \
	fi
	