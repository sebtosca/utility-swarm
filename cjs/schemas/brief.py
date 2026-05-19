from pydantic import BaseModel, Field


class Brief(BaseModel):
    brand: str = Field(description="Brand or product name.")
    objective: str = Field(description="What success looks like for this campaign.")
    platform: str = Field(
        description="Primary platform where the ads will run (e.g. TikTok, YouTube, TV)."
    )
    audience: str = Field(
        description="Target audience for the campaign (who the creative is speaking to)."
    )
    tone: str = Field(
        description="Desired brand voice for this campaign (e.g. playful, premium, authoritative)."
    )
    key_message: str = Field(
        description="Single most important message viewers should remember or act on."
    )
    primary_kpi: str = Field(
        description="Primary KPI for the campaign (e.g. awareness, conversion, engagement, consideration)."
    )
    emotional_territory: str | None = Field(
        default=None,
        description="Intended emotional territory for the creative (e.g. excitement, reassurance, nostalgia).",
    )
    mandatory: list[str] = Field(
        default_factory=list,
        description="Items that must appear in the creative (taglines, CTAs, product shots, legal copy, etc.).",
    )
    forbidden: list[str] = Field(
        default_factory=list,
        description="Items that must not appear in the creative (phrases, claims, themes, competitors, etc.).",
    )
    kpi_priority: dict[str, float] = Field(
        default_factory=dict,
        description="Optional weights per KPI when custom weighting is needed (e.g. {'awareness': 0.6, 'conversion': 0.4}).",
    )
    constraints: dict[str, str] = Field(
        default_factory=dict,
        description="Additional structured constraints for the campaign (regions, length, legal notes, brand assets, etc.).",
    )
