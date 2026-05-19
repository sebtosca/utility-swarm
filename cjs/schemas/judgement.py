from pydantic import BaseModel, Field


class AgentJudgement(BaseModel):
    agent_name: str = Field(
        ...,
        description="Name or identifier of the jury member (agent).",
    )
    agent_role: str | None = Field(
        default=None,
        description="High-level role or persona of the agent (e.g. CreativeDirector, BrandStrategist).",
    )
    video_path: str = Field(
        ...,
        description="Path of the video this judgement refers to.",
    )
    rubric_version: str | None = Field(
        default=None,
        description="Identifier for the rubric configuration used for this judgement.",
    )
    scores: dict[str, float] = Field(
        default_factory=dict,
        description="Per-metric scores from this agent (0–10 scale, keyed by rubric metric name).",
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="Bullet-point strengths observed by this agent for this video.",
    )
    weaknesses: list[str] = Field(
        default_factory=list,
        description="Bullet-point weaknesses observed by this agent for this video.",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Concrete references (timestamps, transcript excerpts, scene notes) supporting the judgement.",
    )
    metric_comments: dict[str, str] = Field(
        default_factory=dict,
        description="Optional short comments per metric, keyed by metric name.",
    )
    confidence: int = Field(
        ...,
        ge=0,
        le=100,
        description="Agent's confidence in this judgement on a 0–100 scale.",
    )
    token_bid: int = Field(
        ...,
        ge=0,
        description="Integer bid used by the auction engine to weight this agent's influence.",
    )
    flags: list[str] = Field(
        default_factory=list,
        description="Flags or concerns raised by this agent (e.g. 'legal_risk', 'off_brief').",
    )
    notes: str | None = Field(
        default=None,
        description="Free-text notes that do not fit into scores, strengths, or weaknesses.",
    )
    model_info: dict[str, str] = Field(
        default_factory=dict,
        description="Metadata about the underlying model/provider used to generate this judgement.",
    )
