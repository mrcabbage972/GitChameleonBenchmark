from pydantic import BaseModel, ConfigDict, model_validator

from gitchameleon.utils import load_jsonl


class Solution(BaseModel):
    example_id: str
    answer: str

    model_config = ConfigDict(extra="ignore")

    @staticmethod
    def from_jsonl(file_path: str) -> list["Solution"]:
        print(f"Validating solution file")
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
