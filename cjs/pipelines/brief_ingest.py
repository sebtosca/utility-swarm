from pathlib import Path
from typing import Any

import yaml

from cjs.constants import JURY_DIMENSIONS, KPI_DIMENSION_MAP
from cjs.router.model_router import ModelRouter
from cjs.schemas.brand_rules import BrandRules
from cjs.schemas.brief import Brief
from cjs.schemas.rubric import Rubric
from cjs.utils.pdf import extract_text_from_pdf


class BriefIngestError(Exception):
    """Raised when any brief ingestion step fails."""


# ---------------------------------------------------------------------------
# Phase 6 — PDF extraction
# ---------------------------------------------------------------------------


def extract_brief_raw(pdf_path: Path, run_folder: Path, max_pages: int) -> str:
    """Extract raw text from a brief PDF and persist it in the run folder."""
    raw_text = extract_text_from_pdf(pdf_path=pdf_path, max_pages=max_pages)
    brief_dir = run_folder / "brief"
    brief_dir.mkdir(parents=True, exist_ok=True)
    (brief_dir / "brief_raw.txt").write_text(raw_text)
    return raw_text


# ---------------------------------------------------------------------------
# Phase 9.1 — parse_brief
# ---------------------------------------------------------------------------

_PARSE_BRIEF_SYSTEM = """\
You are a creative strategy analyst. Extract all structured information from the creative brief text.
Use the exact wording from the brief wherever possible.
If a field cannot be determined from the text, use an empty string or an empty list as appropriate.\
"""


def parse_brief(raw_text: str, router: ModelRouter) -> Brief:
    """Parse raw brief text into a structured Brief using Claude tool-use."""
    user = f"Extract the structured brief from the following raw text:\n\n<brief>\n{raw_text}\n</brief>"
    result = router.call_structured(
        system=_PARSE_BRIEF_SYSTEM,
        user=user,
        node="brief_parse",
        schema=Brief.model_json_schema(),
        schema_name="Brief",
    )
    try:
        return Brief.model_validate_json(result.content)
    except Exception as exc:
        raise BriefIngestError(f"Failed to parse brief from LLM output: {exc}") from exc


# ---------------------------------------------------------------------------
# Phase 9.2 — generate_rubric
# ---------------------------------------------------------------------------


def _build_kpi_constraint_block(kpi_priority: dict[str, float]) -> str:
    if not kpi_priority:
        return ""
    lines = [
        "KPI priority constraints (must be honoured — distribute these proportions across mapped dimensions):"
    ]
    for kpi, weight in kpi_priority.items():
        mapped = KPI_DIMENSION_MAP.get(kpi.lower(), [])
        mapped_str = ", ".join(mapped) if mapped else "all dimensions"
        lines.append(f"  {kpi} ({weight:.0%}) → primarily drives: {mapped_str}")
    return "\n".join(lines)


def _build_dimension_map_block() -> str:
    lines = ["KPI-to-dimension reference (use to honour kpi_priority above):"]
    for kpi, dims in KPI_DIMENSION_MAP.items():
        lines.append(f"  {kpi} → {', '.join(dims)}")
    return "\n".join(lines)


_RUBRIC_SYSTEM = f"""\
You are a creative evaluation specialist. Generate a scoring rubric that weights evaluation
dimensions for creative ad assessment based on the campaign's goals and primary KPI.

Rules:
- Use exactly these dimension keys: {", ".join(JURY_DIMENSIONS)}
- Weights must sum to exactly 1.0 (round each to 4 decimal places).
- If kpi_priority constraints are provided, distribute weights to honour them — this is mandatory.
- Use emotional_territory as a qualitative signal to fine-tune weights within KPI constraints.
- hard_gates should reflect mandatory compliance thresholds (e.g. brand safety, mandatory element inclusion).

{_build_dimension_map_block()}\
"""


def generate_rubric(brief: Brief, router: ModelRouter) -> Rubric:
    """Generate a weighted scoring rubric derived from the structured Brief."""
    mandatory_str = ", ".join(brief.mandatory) if brief.mandatory else "none specified"
    kpi_block = _build_kpi_constraint_block(brief.kpi_priority)

    user_parts = [
        "Generate a scoring rubric for this campaign:",
        f"- Brand: {brief.brand}",
        f"- Objective: {brief.objective}",
        f"- Primary KPI: {brief.primary_kpi}",
        f"- Platform: {brief.platform}",
        f"- Audience: {brief.audience}",
        f"- Tone: {brief.tone}",
        f"- Key Message: {brief.key_message}",
        f"- Mandatory elements: {mandatory_str}",
    ]
    if brief.emotional_territory:
        user_parts.append(f"- Emotional territory: {brief.emotional_territory}")
    if kpi_block:
        user_parts.append(f"\n{kpi_block}")

    result = router.call_structured(
        system=_RUBRIC_SYSTEM,
        user="\n".join(user_parts),
        node="rubric_generate",
        schema=Rubric.model_json_schema(),
        schema_name="Rubric",
    )
    try:
        rubric = Rubric.model_validate_json(result.content)
    except Exception as exc:
        raise BriefIngestError(f"Failed to parse rubric from LLM output: {exc}") from exc

    total = sum(rubric.weights.values())
    if total > 0:
        rubric.weights = {k: round(v / total, 4) for k, v in rubric.weights.items()}
    return rubric


# ---------------------------------------------------------------------------
# Phase 9.3 — brand rules from YAML (required path)
# ---------------------------------------------------------------------------


def _mandatory_elements_from_dict(data: dict[str, Any]) -> list[str]:
    elements: list[str] = []
    if data.get("tagline"):
        elements.append(f"tagline: {data['tagline']}")
    if data.get("cta"):
        elements.append(f"cta: {data['cta']}")
    skip = {"logo_visible_by_seconds", "disclaimer_required", "tagline", "cta"}
    for key, val in data.items():
        if key not in skip and isinstance(val, str):
            elements.append(f"{key}: {val}")
    return elements


def _logo_sec_from_dict(data: dict[str, Any]) -> float | None:
    raw = data.get("logo_visible_by_seconds")
    return float(raw) if raw is not None else None


def _disclaimer_from_dict(data: dict[str, Any]) -> bool:
    return bool(data.get("disclaimer_required", False))


def _forbidden_elements_from_dict(data: dict[str, Any]) -> list[str]:
    elements: list[str] = []
    for name in data.get("competitor_names", []):
        elements.append(f"competitor: {name}")
    for phrase in data.get("phrases", []):
        elements.append(str(phrase))
    for color in data.get("colors", []):
        if color:
            elements.append(f"color: {color}")
    for theme in data.get("themes", []):
        elements.append(f"theme: {theme}")
    return elements


def load_brand_rules_from_yaml(yaml_path: Path) -> BrandRules:
    """Load brand compliance rules from a required brand pack YAML file."""
    try:
        data: Any = yaml.safe_load(yaml_path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise BriefIngestError(f"Could not read brand YAML at {yaml_path}: {exc}") from exc

    brand: dict[str, Any] = data.get("brand", data) if isinstance(data, dict) else {}
    tone_raw = brand.get("tone", [])
    tone_keywords: list[str] = tone_raw if isinstance(tone_raw, list) else [str(tone_raw)]

    mandatory_raw = brand.get("mandatory", {})
    if isinstance(mandatory_raw, dict):
        mandatory_elements = _mandatory_elements_from_dict(mandatory_raw)
        logo_visible_by_sec = _logo_sec_from_dict(mandatory_raw)
        disclaimer_required = _disclaimer_from_dict(mandatory_raw)
    else:
        mandatory_elements = (
            [str(item) for item in mandatory_raw] if isinstance(mandatory_raw, list) else []
        )
        logo_visible_by_sec = None
        disclaimer_required = False

    forbidden_raw = brand.get("forbidden", {})
    if isinstance(forbidden_raw, dict):
        forbidden_elements = _forbidden_elements_from_dict(forbidden_raw)
    else:
        forbidden_elements = (
            [str(item) for item in forbidden_raw] if isinstance(forbidden_raw, list) else []
        )

    return BrandRules(
        brand_name=brand.get("name", "Unknown"),
        mandatory_elements=mandatory_elements,
        forbidden_elements=forbidden_elements,
        approved_claims=brand.get("approved_claims", []),
        prohibited_claims=brand.get("prohibited_claims", []),
        tone_keywords=tone_keywords,
        logo_visible_by_sec=logo_visible_by_sec,
        disclaimer_required=disclaimer_required,
        source="yaml",
    )


# ---------------------------------------------------------------------------
# cjs brand init — starter YAML generator
# ---------------------------------------------------------------------------

_BRAND_INIT_SYSTEM = """\
You are a brand compliance specialist. Based on a creative brief, generate a starter brand pack YAML
that the user can review, edit, and save for future use.

The YAML must follow this schema exactly:
brand:
  name: <brand name>
  tone:
    - <tone keyword>
  mandatory:
    tagline: <tagline if found, else omit>
    logo_visible_by_seconds: <number if specified, else omit>
    disclaimer_required: <true or false>
  forbidden:
    competitor_names: [<list or empty>]
    phrases: [<list or empty>]
    themes: [<list or empty>]
  approved_claims: [<list of things the brand is permitted to say, or empty>]
  prohibited_claims: [<list of things the brand must never claim, or empty>]

Extract as much as possible from the brief. Leave empty lists where information is not available.
Return only valid YAML — no markdown fences, no explanation.\
"""


def generate_starter_brand_yaml(raw_text: str, router: ModelRouter) -> str:
    """Generate a starter brand YAML from brief text for `cjs brand init`."""
    user = (
        f"Generate a starter brand YAML from this creative brief:\n\n<brief>\n{raw_text}\n</brief>"
    )
    result = router.call_text(
        system=_BRAND_INIT_SYSTEM,
        user=user,
        node="brand_init",
    )
    return result.content
