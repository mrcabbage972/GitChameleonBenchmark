DOCKER_IMAGE := gc
DOCKER_TAG := 1.0
PYTHON_VERSION ?= 3.9

.PHONY: docker-run

docker-build:
	docker build . -t $(DOCKER_IMAGE):$(DOCKER_TAG)

docker-run:
	docker run --rm -it -v "./.dataset_venvs:/app/.dataset_venvs" $(DOCKER_IMAGE):$(DOCKER_TAG) -c "pyenv global $(PYTHON_VERSION) && exec bash"

evals-setup: docker-build build-venvs

build-venvs:
	docker run --rm -it -v "./.dataset_venvs:/app/.dataset_venvs" $(DOCKER_IMAGE):$(DOCKER_TAG) -c "pyenv global $(PYTHON_VERSION) && poetry run python gitchameleon/create_venvs.py --base_path .dataset_venvs --dataset dataset.jsonl"

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
	  python gitchameleon/eval_wrapper.py --solution-path $(SOLUTION_PATH) --docker-image $(DOCKER_IMAGE) --docker-tag $(DOCKER_TAG) --python-version $(PYTHON_VERSION); \
	fi
	