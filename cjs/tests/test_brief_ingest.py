"""Unit tests for Phase 9 brief ingestion pipeline (mocked router)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from cjs.pipelines.brief_ingest import (
    BriefIngestError,
    generate_rubric,
    generate_starter_brand_yaml,
    load_brand_rules_from_yaml,
    parse_brief,
)
from cjs.router.model_router import RouterResult
from cjs.schemas.brief import Brief
from cjs.schemas.rubric import Rubric

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_router_result(content: str) -> RouterResult:
    return RouterResult(
        content=content, tokens_in=10, tokens_out=20, latency_ms=100.0, model="test-model"
    )


def _mock_router(content: str) -> MagicMock:
    router = MagicMock()
    router.call_structured.return_value = _make_router_result(content)
    router.call_text.return_value = _make_router_result(content)
    return router


def _minimal_brief() -> Brief:
    return Brief(
        brand="Acme",
        objective="Increase brand awareness",
        platform="TikTok",
        audience="18-34 year olds",
        tone="energetic",
        key_message="Live boldly",
        primary_kpi="awareness",
    )


# ---------------------------------------------------------------------------
# parse_brief
# ---------------------------------------------------------------------------


class TestParseBrief:
    def test_returns_brief_on_valid_json(self) -> None:
        brief = _minimal_brief()
        router = _mock_router(brief.model_dump_json())
        result = parse_brief(raw_text="Some brief text", router=router)
        assert result.brand == "Acme"
        assert result.primary_kpi == "awareness"

    def test_calls_router_with_correct_node(self) -> None:
        brief = _minimal_brief()
        router = _mock_router(brief.model_dump_json())
        parse_brief(raw_text="brief text", router=router)
        call_kwargs = router.call_structured.call_args.kwargs
        assert call_kwargs["node"] == "brief_parse"
        assert call_kwargs["schema_name"] == "Brief"

    def test_raises_brief_ingest_error_on_invalid_json(self) -> None:
        router = _mock_router("not valid json at all")
        with pytest.raises(BriefIngestError, match="Failed to parse brief"):
            parse_brief(raw_text="anything", router=router)

    def test_raw_text_included_in_user_prompt(self) -> None:
        brief = _minimal_brief()
        router = _mock_router(brief.model_dump_json())
        parse_brief(raw_text="MY UNIQUE BRIEF CONTENT", router=router)
        user_arg = router.call_structured.call_args.kwargs["user"]
        assert "MY UNIQUE BRIEF CONTENT" in user_arg


# ---------------------------------------------------------------------------
# generate_rubric
# ---------------------------------------------------------------------------


class TestGenerateRubric:
    def _valid_rubric_json(self) -> str:
        rubric = Rubric(
            name="Test rubric",
            weights={
                "brief_compliance": 0.15,
                "brand_alignment": 0.15,
                "audience_resonance": 0.20,
                "emotional_impact": 0.20,
                "message_clarity": 0.10,
                "performance_potential": 0.10,
                "storytelling": 0.10,
            },
        )
        return rubric.model_dump_json()

    def test_returns_rubric_with_normalised_weights(self) -> None:
        router = _mock_router(self._valid_rubric_json())
        brief = _minimal_brief()
        rubric = generate_rubric(brief=brief, router=router)
        assert abs(sum(rubric.weights.values()) - 1.0) < 0.001

    def test_calls_router_with_correct_node(self) -> None:
        router = _mock_router(self._valid_rubric_json())
        generate_rubric(brief=_minimal_brief(), router=router)
        call_kwargs = router.call_structured.call_args.kwargs
        assert call_kwargs["node"] == "rubric_generate"
        assert call_kwargs["schema_name"] == "Rubric"

    def test_emotional_territory_included_when_present(self) -> None:
        router = _mock_router(self._valid_rubric_json())
        brief = _minimal_brief()
        brief.emotional_territory = "nostalgia"
        generate_rubric(brief=brief, router=router)
        user_arg = router.call_structured.call_args.kwargs["user"]
        assert "nostalgia" in user_arg

    def test_emotional_territory_omitted_when_absent(self) -> None:
        router = _mock_router(self._valid_rubric_json())
        brief = _minimal_brief()
        brief.emotional_territory = None
        generate_rubric(brief=brief, router=router)
        user_arg = router.call_structured.call_args.kwargs["user"]
        assert "Emotional territory" not in user_arg

    def test_kpi_priority_included_in_user_prompt(self) -> None:
        router = _mock_router(self._valid_rubric_json())
        brief = _minimal_brief()
        brief.kpi_priority = {"awareness": 0.7, "conversion": 0.3}
        generate_rubric(brief=brief, router=router)
        user_arg = router.call_structured.call_args.kwargs["user"]
        assert "awareness" in user_arg
        assert "conversion" in user_arg

    def test_normalises_weights_that_do_not_sum_to_one(self) -> None:
        rubric = Rubric(
            weights={
                "brief_compliance": 2.0,
                "brand_alignment": 2.0,
                "audience_resonance": 2.0,
                "emotional_impact": 2.0,
                "message_clarity": 0.0,
                "performance_potential": 0.0,
                "storytelling": 0.0,
            }
        )
        router = _mock_router(rubric.model_dump_json())
        result = generate_rubric(brief=_minimal_brief(), router=router)
        assert abs(sum(result.weights.values()) - 1.0) < 0.001

    def test_raises_on_invalid_rubric_json(self) -> None:
        router = _mock_router("{bad json")
        with pytest.raises(BriefIngestError, match="Failed to parse rubric"):
            generate_rubric(brief=_minimal_brief(), router=router)


# ---------------------------------------------------------------------------
# load_brand_rules_from_yaml
# ---------------------------------------------------------------------------


class TestLoadBrandRulesFromYaml:
    def _write_yaml(self, tmp_path: Path, data: dict) -> Path:
        p = tmp_path / "brand.yaml"
        p.write_text(yaml.dump(data))
        return p

    def test_loads_full_yaml(self, tmp_path: Path) -> None:
        data = {
            "brand": {
                "name": "Nike",
                "tone": ["energetic", "aspirational"],
                "mandatory": {
                    "tagline": "Just Do It",
                    "logo_visible_by_seconds": 3,
                    "disclaimer_required": False,
                },
                "forbidden": {
                    "competitor_names": ["Adidas", "Puma"],
                    "phrases": ["cheap"],
                },
                "approved_claims": ["world-class performance"],
                "prohibited_claims": ["best shoe ever made"],
            }
        }
        rules = load_brand_rules_from_yaml(self._write_yaml(tmp_path, data))
        assert rules.brand_name == "Nike"
        assert rules.source == "yaml"
        assert rules.logo_visible_by_sec == 3.0
        assert rules.disclaimer_required is False
        assert "tagline: Just Do It" in rules.mandatory_elements
        assert "competitor: Adidas" in rules.forbidden_elements
        assert "competitor: Puma" in rules.forbidden_elements
        assert "cheap" in rules.forbidden_elements
        assert "world-class performance" in rules.approved_claims
        assert "best shoe ever made" in rules.prohibited_claims
        assert "energetic" in rules.tone_keywords

    def test_handles_missing_optional_fields(self, tmp_path: Path) -> None:
        data = {"brand": {"name": "Acme"}}
        rules = load_brand_rules_from_yaml(self._write_yaml(tmp_path, data))
        assert rules.brand_name == "Acme"
        assert rules.mandatory_elements == []
        assert rules.forbidden_elements == []
        assert rules.logo_visible_by_sec is None
        assert rules.disclaimer_required is False

    def test_handles_list_mandatory(self, tmp_path: Path) -> None:
        data = {"brand": {"name": "X", "mandatory": ["show logo", "say slogan"]}}
        rules = load_brand_rules_from_yaml(self._write_yaml(tmp_path, data))
        assert "show logo" in rules.mandatory_elements

    def test_handles_list_forbidden(self, tmp_path: Path) -> None:
        data = {"brand": {"name": "X", "forbidden": ["violence", "politics"]}}
        rules = load_brand_rules_from_yaml(self._write_yaml(tmp_path, data))
        assert "violence" in rules.forbidden_elements

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(BriefIngestError, match="Could not read brand YAML"):
            load_brand_rules_from_yaml(tmp_path / "nonexistent.yaml")

    def test_raises_on_invalid_yaml(self, tmp_path: Path) -> None:
        p = tmp_path / "brand.yaml"
        p.write_text("brand: {invalid: yaml: content: [")
        with pytest.raises(BriefIngestError, match="Could not read brand YAML"):
            load_brand_rules_from_yaml(p)

    def test_source_is_yaml(self, tmp_path: Path) -> None:
        data = {"brand": {"name": "X"}}
        rules = load_brand_rules_from_yaml(self._write_yaml(tmp_path, data))
        assert rules.source == "yaml"


# ---------------------------------------------------------------------------
# generate_starter_brand_yaml
# ---------------------------------------------------------------------------


class TestGenerateStarterBrandYaml:
    def test_returns_router_content(self) -> None:
        expected = "brand:\n  name: TestBrand\n"
        router = _mock_router(expected)
        result = generate_starter_brand_yaml(raw_text="brief text", router=router)
        assert result == expected

    def test_calls_call_text_not_call_structured(self) -> None:
        router = _mock_router("brand:\n  name: X\n")
        generate_starter_brand_yaml(raw_text="brief", router=router)
        router.call_text.assert_called_once()
        router.call_structured.assert_not_called()

    def test_brief_text_included_in_prompt(self) -> None:
        router = _mock_router("brand:\n  name: X\n")
        generate_starter_brand_yaml(raw_text="UNIQUE BRIEF MARKER", router=router)
        user_arg = router.call_text.call_args.kwargs["user"]
        assert "UNIQUE BRIEF MARKER" in user_arg
