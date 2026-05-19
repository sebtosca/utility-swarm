from typing import Annotated

from typing_extensions import TypedDict


def _merge_dicts(a: dict, b: dict) -> dict:
    return {**a, **b}


class JuryState(TypedDict):
    run_id: str
    brief: dict
    rubric: dict
    brand_rules: dict
    video_dossiers: list[dict]
    initial_judgements: Annotated[dict[str, list[dict]], _merge_dicts]
    consistency_report: dict | None
    final_judgements: Annotated[dict[str, list[dict]], _merge_dicts]
    verdict: dict | None
