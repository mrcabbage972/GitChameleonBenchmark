FROM ubuntu:20.04

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH" \
    PYTHONPATH="/app"

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    libssl-dev \
    zlib1g-dev \
    libbz2-dev \
    liblzma-dev \
    libffi-dev \
    libsqlite3-dev \
    gfortran \
    libopenblas-dev \
    libspatialindex-dev \
    ffmpeg \
    libsndfile1-dev \
    xz-utils && rm -rf /var/lib/apt/lists/*

ENV PYENV_ROOT="/root/.pyenv"
ENV PATH="$PYENV_ROOT/bin:$PYENV_ROOT/shims:$PATH"

RUN curl -fsSL https://pyenv.run | bash

# Ensure that pyenv is initialized on every new shell.
RUN echo 'export PYENV_ROOT="/root/.pyenv"' >> /root/.bashrc && \
    echo 'export PATH="$PYENV_ROOT/bin:$PYENV_ROOT/shims:$PATH"' >> /root/.bashrc && \
    echo 'eval "$(pyenv init --path)"' >> /root/.bashrc && \
    echo 'eval "$(pyenv init -)"' >> /root/.bashrc

# Install the desired Python versions, rehash to update pyenv shims, and set the global versions.
RUN pyenv install 3.9.19 && \
    pyenv install 3.10.14 && \
    pyenv install 3.7.17 && \
    pyenv rehash && \
    pyenv global 3.9.19 3.10.14 3.7.17


ENV POETRY_VERSION=1.8.5

# Install Poetry
RUN curl -sSL "https://install.python-poetry.org" -o get-poetry.py && \
    python3 get-poetry.py --version $POETRY_VERSION && \
    rm get-poetry.py

# Copy pyproject.toml and poetry.lock (if available)
COPY ./pyproject.toml ./poetry.lock /app/

# Set the working directory
WORKDIR /app


# Install Python dependencies using Poetry
RUN poetry install --no-root

COPY ./gitchameleon /app/gitchameleon  
COPY ./dataset/dataset.jsonl /app/dataset.jsonl
COPY ./dataset/hidden_tests /app/hidden_tests
COPY ./dataset/visible_tests /app/visible_tests

# Use bash as the entrypoint.
ENTRYPOINT ["/bin/bash"]
