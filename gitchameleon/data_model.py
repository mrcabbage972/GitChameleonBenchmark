from typing import Optional

from pydantic import BaseModel, ConfigDict, model_validator

from gitchameleon.utils import load_jsonl


class Example(BaseModel):
    example_id: str
    python_version: str
    library: str
    version: str
    problem: str
    starting_code: str
    additional_dependencies: Optional[str]
    solution: str

    model_config = ConfigDict(extra="ignore")

    @staticmethod
    def from_jsonl(file_path: str) -> list["Example"]:
        print("Validating dataset file")
        ds_dicts = load_jsonl(file_path)
        return [Example.model_validate(s) for s in ds_dicts]


class Solution(BaseModel):
    example_id: str
    answer: str

    model_config = ConfigDict(extra="ignore")

    @staticmethod
    def from_jsonl(file_path: str) -> list["Solution"]:
        print("Validating solution file")
        sol_dicts = load_jsonl(file_path)
        return [Solution.model_validate(s) for s in sol_dicts]

    @model_validator(mode="before")
    @classmethod
    def _gather_ids(cls, data: dict) -> dict:
        # look for any of these keys, in priority order
        for alias in ("answer", "solution", "output"):
            if alias in data:
                # map it into the one field you declare
                data["answer"] = data.pop(alias)
                break
        return data
