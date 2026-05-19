import json
import tempfile
from pathlib import Path

import pytest

from cjs.auction.engine import (
    compute_final_scores,
    select_winner,
    build_verdict,
    run_auction,
)

_RUBRIC = {"weights": {"storytelling": 0.6, "message_clarity": 0.4}, "name": None,
           "description": None, "hard_gates": {}}

_JUDGEMENT = lambda agent, video, st, mc, conf, bid, flags=None: {  # noqa: E731
    "agent_name": agent, "agent_role": None, "video_path": f"/run/input/{video}",
    "scores": {"storytelling": st, "message_clarity": mc},
    "confidence": conf, "token_bid": bid,
    "flags": flags or [], "strengths": [], "weaknesses": [], "evidence": [],
    "metric_comments": {}, "notes": None, "model_info": {},
}

_VERDICT = {
    "winner_video": "ad1.mp4", "winner_rationale": "Compelling narrative.",
    "ranking": ["ad1.mp4", "ad2.mp4"], "per_video_notes": {"ad1.mp4": "Strong."},
    "confidence": 0.85, "flags_resolved": ["logo_timing"],
}


def _make_state(final_judgements, verdict=None, flags_on_brand_compliance=None):
    bj = {}
    if flags_on_brand_compliance is not None:
        bj = {"brand_compliance": [
            _JUDGEMENT("brand_compliance", "ad1.mp4", 7, 7, 80, 60,
                       flags=flags_on_brand_compliance),
            _JUDGEMENT("brand_compliance", "ad2.mp4", 6, 6, 80, 40),
        ]}
    return {
        "run_id": "test_run",
        "rubric": _RUBRIC,
        "final_judgements": {**final_judgements, **bj},
        "verdict": verdict,
        "brief": {}, "brand_rules": {}, "video_dossiers": [],
        "initial_judgements": {}, "consistency_report": None,
    }


# ---------------------------------------------------------------------------
# compute_final_scores
# ---------------------------------------------------------------------------

def test_weighted_aggregation_single_agent():
    state = _make_state({
        "agent_a": [
            _JUDGEMENT("agent_a", "ad1.mp4", 8.0, 6.0, 100, 70),
            _JUDGEMENT("agent_a", "ad2.mp4", 4.0, 4.0, 100, 30),
        ]
    })
    scores = compute_final_scores(state)
    # rubric_score(ad1) = (8*0.6 + 6*0.4)/1.0 = 7.2, conf=1.0, conv=0.7 → 5.04
    # rubric_score(ad2) = (4*0.6 + 4*0.4)/1.0 = 4.0, conf=1.0, conv=0.3 → 1.20
    assert abs(scores["ad1.mp4"] - 5.04) < 0.01
    assert abs(scores["ad2.mp4"] - 1.20) < 0.01


def test_conviction_normalisation_sums_to_one_per_agent():
    state = _make_state({
        "agent_a": [
            _JUDGEMENT("agent_a", "ad1.mp4", 8.0, 6.0, 100, 60),
            _JUDGEMENT("agent_a", "ad2.mp4", 4.0, 4.0, 100, 40),
        ]
    })
    scores = compute_final_scores(state)
    # conviction weights 0.6 + 0.4 = 1.0 — check combined score matches manual calc
    assert abs(scores["ad1.mp4"] - 4.32) < 0.01  # 7.2 * 1.0 * 0.6
    assert abs(scores["ad2.mp4"] - 1.60) < 0.01  # 4.0 * 1.0 * 0.4


def test_risk_penalty_applied_to_brand_compliance_flags():
    state = _make_state(
        final_judgements={
            "agent_a": [
                _JUDGEMENT("agent_a", "ad1.mp4", 8.0, 8.0, 100, 60),
                _JUDGEMENT("agent_a", "ad2.mp4", 8.0, 8.0, 100, 40),
            ]
        },
        flags_on_brand_compliance=["logo_missing", "disclaimer_absent"],
    )
    scores = compute_final_scores(state)
    # ad1 has 2 brand_compliance flags → penalty = 4.0; ad2 has 0 flags
    assert scores["ad1.mp4"] < scores["ad2.mp4"]


def test_risk_penalty_capped_at_ten():
    state = _make_state(
        final_judgements={
            "agent_a": [_JUDGEMENT("agent_a", "ad1.mp4", 10.0, 10.0, 100, 100)],
        },
        flags_on_brand_compliance=["f1", "f2", "f3", "f4", "f5", "f6", "f7"],
    )
    scores = compute_final_scores(state)
    # Without penalty: 10.0 * 1.0 * 1.0 = 10.0; max penalty = 10 → score ≥ 0
    assert scores.get("ad1.mp4", 0.0) >= 0.0


def test_empty_judgements_returns_empty():
    state = _make_state({})
    assert compute_final_scores(state) == {}


def test_multi_agent_scores_summed():
    state = _make_state({
        "agent_a": [_JUDGEMENT("agent_a", "ad1.mp4", 6.0, 6.0, 100, 50),
                    _JUDGEMENT("agent_a", "ad2.mp4", 6.0, 6.0, 100, 50)],
        "agent_b": [_JUDGEMENT("agent_b", "ad1.mp4", 8.0, 8.0, 100, 80),
                    _JUDGEMENT("agent_b", "ad2.mp4", 2.0, 2.0, 100, 20)],
    })
    scores = compute_final_scores(state)
    assert scores["ad1.mp4"] > scores["ad2.mp4"]


# ---------------------------------------------------------------------------
# select_winner
# ---------------------------------------------------------------------------

def test_select_winner_basic():
    assert select_winner({"ad1.mp4": 5.0, "ad2.mp4": 8.0}) == "ad2.mp4"


def test_select_winner_tie_deterministic():
    # Ties resolve alphabetically (sorted keys, first wins)
    result = select_winner({"b.mp4": 5.0, "a.mp4": 5.0})
    assert result == "a.mp4"


def test_select_winner_raises_on_empty():
    with pytest.raises(ValueError):
        select_winner({})


# ---------------------------------------------------------------------------
# build_verdict
# ---------------------------------------------------------------------------

def test_build_verdict_uses_moderator_rationale():
    state = _make_state({}, verdict=_VERDICT)
    scores = {"ad1.mp4": 9.0, "ad2.mp4": 5.0}
    verdict = build_verdict(scores, state)
    assert verdict["winner_video"] == "ad1.mp4"
    assert verdict["winner_rationale"] == "Compelling narrative."
    assert verdict["ranking"] == ["ad1.mp4", "ad2.mp4"]
    assert verdict["confidence"] == 0.85


def test_build_verdict_without_moderator():
    state = _make_state({}, verdict=None)
    scores = {"ad1.mp4": 9.0, "ad2.mp4": 3.0}
    verdict = build_verdict(scores, state)
    assert verdict["winner_video"] == "ad1.mp4"
    assert verdict["ranking"] == ["ad1.mp4", "ad2.mp4"]
    assert 0 <= verdict["confidence"] <= 1


def test_build_verdict_ranking_order():
    state = _make_state({}, verdict=None)
    scores = {"ad3.mp4": 3.0, "ad1.mp4": 9.0, "ad2.mp4": 6.0}
    verdict = build_verdict(scores, state)
    assert verdict["ranking"] == ["ad1.mp4", "ad2.mp4", "ad3.mp4"]


# ---------------------------------------------------------------------------
# run_auction (integration)
# ---------------------------------------------------------------------------

def test_run_auction_writes_scorecards_and_verdict(tmp_path):
    state = _make_state(
        final_judgements={
            "agent_a": [
                _JUDGEMENT("agent_a", "ad1.mp4", 8.0, 8.0, 90, 70),
                _JUDGEMENT("agent_a", "ad2.mp4", 5.0, 5.0, 90, 30),
            ]
        },
        verdict=_VERDICT,
    )
    results_dir = tmp_path / "results"
    verdict = run_auction(state, tmp_path)

    assert (results_dir / "scorecards.json").exists()
    assert (results_dir / "verdict.json").exists()
    scorecards = json.loads((results_dir / "scorecards.json").read_text())
    assert "final_scores" in scorecards
    assert "ranking" in scorecards
    assert verdict["winner_video"] == "ad1.mp4"
