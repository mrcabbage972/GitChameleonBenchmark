import hashlib
import json


def generate_venv_cache_key(python_version: str, library: str, version: str, extra_deps: str) -> str:
    """Generates a unique cache key based on inputs."""
    key_parts = [python_version, library, version, extra_deps]
    key_string = "-".join(key_parts)
    return hashlib.sha256(key_string.encode("utf-8")).hexdigest()[0:12]


def load_jsonl(file_path: str) -> list[dict]:
    result = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data = json.loads(line)
                result.append(data)
    return result
