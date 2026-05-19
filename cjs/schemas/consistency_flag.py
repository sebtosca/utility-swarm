from typing import Literal

from pydantic import BaseModel, Field


class ConsistencyFlag(BaseModel):
    agent: str = Field(description="Name of the agent the flag applies to.")
    video: str = Field(description="Path of the video the flag applies to.")
    claim: str = Field(description="The specific claim or score that is inconsistent.")
    contradicting_evidence: str = Field(
        description="The dossier data or scorecard entry that contradicts the claim."
    )
    classification: Literal["FACTUAL_CONTRADICTION", "SCORE_NARRATIVE_MISMATCH"] = Field(
        description="Type of inconsistency detected."
    )


class ConsistencyReport(BaseModel):
    flags: list[ConsistencyFlag] = Field(default_factory=list)
    checked_agents: list[str] = Field(
        default_factory=list,
        description="All agent names that were audited.",
    )
    checked_videos: list[str] = Field(
        default_factory=list,
        description="All video paths that were audited.",
    )
