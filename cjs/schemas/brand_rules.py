from typing import Literal

from pydantic import BaseModel, Field


class BrandRules(BaseModel):
    brand_name: str = Field(description="Name of the brand.")
    mandatory_elements: list[str] = Field(
        default_factory=list,
        description="Creative elements that must appear in the ad (taglines, CTAs, product shots, etc.).",
    )
    forbidden_elements: list[str] = Field(
        default_factory=list,
        description="Content that must not appear in the ad (competitor names, phrases, themes, etc.).",
    )
    tone_keywords: list[str] = Field(
        default_factory=list,
        description="Brand voice and tone keywords (e.g. energetic, premium, authoritative).",
    )
    approved_claims: list[str] = Field(
        default_factory=list,
        description="Claims the brand is permitted to make (e.g. 'clinically proven', 'award-winning').",
    )
    prohibited_claims: list[str] = Field(
        default_factory=list,
        description="Claims the brand must never make (e.g. 'best in class', direct competitor comparisons).",
    )
    logo_visible_by_sec: float | None = Field(
        default=None,
        description="Logo must appear on screen by this many seconds into the ad. None if no requirement.",
    )
    disclaimer_required: bool = Field(
        default=False,
        description="Whether a legal disclaimer must be present in the ad.",
    )
    source: Literal["yaml", "brief_extracted"] = Field(
        default="brief_extracted",
        description="Whether these rules came from a brand YAML file or were extracted from the brief.",
    )
