# Safe-mode defaults: limits and allowlists to prevent runaway cost or abuse.

# Max videos allowed per run.
MAX_VIDEOS = 3
# Max duration per video (seconds).
MAX_DURATION_SEC = 30
# Max frames to extract per video for vision analysis.
MAX_FRAMES = 12
# Max PDF pages to extract from brief.
MAX_PDF_PAGES = 20
# Max file size (MB) for inputs.
MAX_FILE_MB = 200
# Max LLM calls per run (optional guardrail).
MAX_LLM_CALLS_PER_RUN = 50

# File extensions allowed for brief and videos.
ALLOWED_EXTENSIONS = (".pdf", ".mp4", ".mov", ".webm")

# Standard scoring dimensions used by all jury agents.
# Weights are derived per-brief by generate_rubric(); these are the canonical keys.
JURY_DIMENSIONS = [
    "brief_compliance",
    "brand_alignment",
    "audience_resonance",
    "emotional_impact",
    "message_clarity",
    "performance_potential",
    "storytelling",
]

# Hard-coded mapping from KPI type to the rubric dimensions it primarily drives.
# Injected into the rubric generation prompt so kpi_priority weights are honoured deterministically.
KPI_DIMENSION_MAP: dict[str, list[str]] = {
    "awareness": ["emotional_impact", "storytelling", "audience_resonance"],
    "conversion": ["performance_potential", "message_clarity", "brief_compliance"],
    "engagement": ["emotional_impact", "audience_resonance", "storytelling"],
    "consideration": ["message_clarity", "audience_resonance", "brand_alignment"],
    "brand": ["brand_alignment", "brief_compliance", "storytelling"],
    "retention": ["audience_resonance", "emotional_impact", "message_clarity"],
}
