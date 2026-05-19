from pydantic import BaseModel, Field

from .brief import Brief


class FinalDecision(BaseModel):
    winner_video_path: str = Field(
        ...,
        description="Path of the winning video selected by the auction engine.",
    )
    scores: dict[str, float] = Field(
        default_factory=dict,
        description="Final per-video scores, keyed by video path.",
    )
    rationale: str = Field(
        ...,
        description="Short natural-language explanation of why this winner was selected.",
    )


class RunReport(BaseModel):
    run_id: str = Field(
        ...,
        description="Unique identifier for the run this report belongs to.",
    )
    brief: Brief = Field(
        ...,
        description="Structured representation of the client brief used for this run.",
    )
    decision: FinalDecision = Field(
        ...,
        description="Final decision and scores for this run.",
    )
    per_video_summary: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Per-video bullet point summaries, keyed by video path.",
    )
    improvements: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Suggested improvements, typically keyed by 'winner' and/or individual video paths.",
    )
    ranking: list[str] = Field(
        default_factory=list,
        description="Ordered list of video paths from best to worst, as determined by the Moderator.",
    )
    unresolved_concerns: list[str] = Field(
        default_factory=list,
        description=(
            "Concerns flagged by the Moderator that the client must be aware of: "
            "split jury decisions, low-confidence scores, or brand risk flags not resolved by Brand Compliance."
        ),
    )
