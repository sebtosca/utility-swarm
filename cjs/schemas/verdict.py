from pydantic import BaseModel, Field


class Verdict(BaseModel):
    winner_video: str
    winner_rationale: str
    ranking: list[str]
    per_video_notes: dict[str, str]
    confidence: float = Field(ge=0, le=1)
    flags_resolved: list[str] = Field(default_factory=list)
