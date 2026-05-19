from pydantic import BaseModel, Field


class Rubric(BaseModel):
    name: str | None = Field(
        default=None,
        description="Optional human-readable name for this rubric (e.g. 'Awareness default').",
    )
    description: str | None = Field(
        default=None,
        description="Short description of how/why this rubric was constructed.",
    )
    weights: dict[str, float] = Field(
        default_factory=dict,
        description="Per-metric weights, e.g. {'brief_compliance': 0.3, 'brand_alignment': 0.3}.",
    )
    hard_gates: dict[str, bool] = Field(
        default_factory=dict,
        description="Hard gate flags, e.g. {'must_include_mandatories': True}.",
    )
