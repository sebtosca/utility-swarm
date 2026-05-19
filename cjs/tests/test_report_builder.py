import json
from pathlib import Path

import pytest

from cjs.report.builder import build_report

_STATE = {
    "run_id": "test_run_001",
    "rubric": {"weights": {"storytelling": 0.6, "message_clarity": 0.4}, "name": "awareness"},
    "brief": {"brand": "TestBrand", "objective": "awareness"},
    "brand_rules": {},
    "video_dossiers": [],
    "initial_judgements": {
        "creative_strategist": [
            {"agent_name": "creative_strategist", "video_path": "/run/input/ad1.mp4",
             "scores": {"storytelling": 8.0, "message_clarity": 7.0},
             "confidence": 85, "token_bid": 60, "flags": [], "strengths": ["Great hook"],
             "weaknesses": [], "evidence": [], "metric_comments": {}, "notes": None, "model_info": {}},
            {"agent_name": "creative_strategist", "video_path": "/run/input/ad2.mp4",
             "scores": {"storytelling": 5.0, "message_clarity": 6.0},
             "confidence": 75, "token_bid": 40, "flags": [], "strengths": [],
             "weaknesses": [], "evidence": [], "metric_comments": {}, "notes": None, "model_info": {}},
        ],
    },
    "final_judgements": {
        "creative_strategist": [
            {"agent_name": "creative_strategist", "video_path": "/run/input/ad1.mp4",
             "scores": {"storytelling": 8.5, "message_clarity": 7.5},
             "confidence": 88, "token_bid": 65, "flags": [], "strengths": ["Great hook"],
             "weaknesses": [], "evidence": [], "metric_comments": {}, "notes": None, "model_info": {}},
            {"agent_name": "creative_strategist", "video_path": "/run/input/ad2.mp4",
             "scores": {"storytelling": 5.0, "message_clarity": 6.0},
             "confidence": 75, "token_bid": 35, "flags": [], "strengths": [],
             "weaknesses": [], "evidence": [], "metric_comments": {}, "notes": None, "model_info": {}},
        ],
    },
    "consistency_report": {
        "flags": [
            {"agent": "creative_strategist", "video": "ad1.mp4",
             "claim": "logo visible", "contradicting_evidence": "dossier says no logo",
             "classification": "FACTUAL_CONTRADICTION"}
        ],
        "checked_agents": ["creative_strategist"],
        "checked_videos": ["ad1.mp4", "ad2.mp4"],
    },
    "verdict": {
        "winner_video": "ad1.mp4", "winner_rationale": "Strongest narrative.",
        "ranking": ["ad1.mp4", "ad2.mp4"], "per_video_notes": {"ad1.mp4": "Strong."},
        "confidence": 0.87, "flags_resolved": [],
    },
}

_VERDICT = {
    "winner_video": "ad1.mp4", "winner_rationale": "Strongest narrative.",
    "ranking": ["ad1.mp4", "ad2.mp4"],
    "per_video_notes": {"ad1.mp4": "Strong.", "ad2.mp4": "Weaker hook."},
    "confidence": 0.87, "flags_resolved": [],
}

_METRICS = {"verdict_confidence": "high", "total_tokens": 12000}


def test_build_report_creates_file(tmp_path):
    path = build_report(tmp_path, _STATE, _VERDICT, _METRICS)
    assert path.exists()
    assert path.suffix == ".html"
    assert path.name == "report.html"


def test_build_report_returns_results_subdir(tmp_path):
    path = build_report(tmp_path, _STATE, _VERDICT, _METRICS)
    assert path.parent.name == "results"


def test_build_report_embeds_cjs_data(tmp_path):
    path = build_report(tmp_path, _STATE, _VERDICT, _METRICS)
    html = path.read_text()
    assert "window.CJS_DATA" in html
    # Extract and parse the embedded JSON
    start = html.index("window.CJS_DATA = ") + len("window.CJS_DATA = ")
    end = html.index(";\n", start)
    data = json.loads(html[start:end])
    assert data["run_id"] == "test_run_001"
    assert data["verdict"]["winner_video"] == "ad1.mp4"
    assert "final_judgements" in data
    assert "consistency_report" in data


def test_build_report_no_external_urls(tmp_path):
    path = build_report(tmp_path, _STATE, _VERDICT, _METRICS)
    html = path.read_text()
    assert "https://" not in html
    # SVG namespace URI (http://www.w3.org/2000/svg) is allowed; no other http:// links
    non_svg = [ln for ln in html.splitlines() if "http://" in ln and "www.w3.org" not in ln]
    assert non_svg == [], f"Unexpected http:// links: {non_svg[:3]}"


def test_build_report_contains_run_id(tmp_path):
    path = build_report(tmp_path, _STATE, _VERDICT, _METRICS)
    assert "test_run_001" in path.read_text()


def test_build_report_loads_escalation_events(tmp_path):
    # Write a sample escalations.jsonl
    escalations = [
        {"ts": "2026-01-01T00:00:00Z", "type": "human_review_required",
         "run_id": "test_run_001", "node": "human_review_gate", "reasons": ["score delta 4.2"]},
    ]
    (tmp_path / "escalations.jsonl").write_text(
        "\n".join(json.dumps(e) for e in escalations)
    )
    path = build_report(tmp_path, _STATE, _VERDICT, _METRICS)
    html = path.read_text()
    assert "human_review_required" in html


def test_build_report_without_escalation_events(tmp_path):
    # escalations.jsonl absent — should not crash
    path = build_report(tmp_path, _STATE, _VERDICT, _METRICS)
    assert path.exists()


def test_build_report_low_confidence_banner(tmp_path):
    low_conf_verdict = {**_VERDICT, "confidence": 0.55}
    path = build_report(tmp_path, _STATE, low_conf_verdict, _METRICS)
    data_str = path.read_text()
    # Low confidence flag should be embedded in data
    start = data_str.index("window.CJS_DATA = ") + len("window.CJS_DATA = ")
    end = data_str.index(";\n", start)
    data = json.loads(data_str[start:end])
    assert data["verdict"]["confidence"] < 0.70
