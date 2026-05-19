from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cjs.graph.state import JuryState


def compute_final_scores(state: JuryState) -> dict[str, float]:
    rubric_weights: dict[str, float] = state["rubric"].get("weights", {})
    total_weight = sum(rubric_weights.values()) or 1.0
    video_scores: dict[str, float] = {}

    for agent_judgements in state["final_judgements"].values():
        for j in agent_judgements:
            filename = Path(j["video_path"]).name
            scores: dict[str, float] = j.get("scores", {})
            if not scores:
                continue
            rubric_score = (
                sum(scores.get(dim, 0.0) * w for dim, w in rubric_weights.items())
                / total_weight
            )
            confidence = j.get("confidence", 0) / 100.0
            conviction_weight = j.get("token_bid", 0) / 100.0
            video_scores[filename] = (
                video_scores.get(filename, 0.0)
                + rubric_score * confidence * conviction_weight
            )

    for video, penalty in _compute_risk_penalties(state).items():
        if video in video_scores:
            video_scores[video] = max(0.0, video_scores[video] - penalty)

    return video_scores


def _compute_risk_penalties(state: JuryState) -> dict[str, float]:
    penalties: dict[str, float] = {}
    for j in state["final_judgements"].get("brand_compliance", []):
        filename = Path(j["video_path"]).name
        penalties[filename] = min(len(j.get("flags", [])) * 2.0, 10.0)
    return penalties


def select_winner(scores: dict[str, float]) -> str:
    if not scores:
        raise ValueError("No scores to select winner from")
    return min(scores, key=lambda v: (-scores[v], v))


def build_verdict(scores: dict[str, float], state: JuryState) -> dict:
    if not scores:
        raise ValueError("No scores to build verdict from")
    ranking = sorted(scores, key=lambda v: (-scores[v], v))
    winner = ranking[0]
    mod = state.get("verdict") or {}
    confidence = mod.get("confidence") if mod.get("confidence") is not None else _margin_confidence(scores)
    return {
        "winner_video": winner,
        "winner_rationale": mod.get("winner_rationale", ""),
        "ranking": ranking,
        "per_video_notes": mod.get("per_video_notes", {}),
        "confidence": confidence,
        "flags_resolved": mod.get("flags_resolved", []),
    }


def _margin_confidence(scores: dict[str, float]) -> float:
    if len(scores) < 2:
        return 1.0
    sorted_vals = sorted(scores.values(), reverse=True)
    margin = sorted_vals[0] - sorted_vals[1]
    return min(1.0, margin / max(sorted_vals[0], 1.0))


def run_auction(state: JuryState, run_folder: Path) -> dict:
    scores = compute_final_scores(state)
    verdict = build_verdict(scores, state) if scores else (state.get("verdict") or {})

    results_dir = run_folder / "results"
    results_dir.mkdir(exist_ok=True)

    scorecards = {
        "final_scores": scores,
        "ranking": verdict["ranking"],
        "winner": verdict["winner_video"],
        "risk_penalties": _compute_risk_penalties(state),
        "per_agent_contributions": _per_agent_contributions(state),
    }
    (results_dir / "scorecards.json").write_text(json.dumps(scorecards, indent=2))
    (results_dir / "verdict.json").write_text(json.dumps(verdict, indent=2))

    return verdict


def _per_agent_contributions(state: JuryState) -> dict[str, dict[str, float]]:
    rubric_weights: dict[str, float] = state["rubric"].get("weights", {})
    total_weight = sum(rubric_weights.values()) or 1.0
    contributions: dict[str, dict[str, float]] = {}
    for agent_name, agent_judgements in state["final_judgements"].items():
        per_video: dict[str, float] = {}
        for j in agent_judgements:
            filename = Path(j["video_path"]).name
            scores: dict[str, float] = j.get("scores", {})
            if not scores:
                continue
            rubric_score = (
                sum(scores.get(dim, 0.0) * w for dim, w in rubric_weights.items())
                / total_weight
            )
            confidence = j.get("confidence", 0) / 100.0
            conviction_weight = j.get("token_bid", 0) / 100.0
            per_video[filename] = rubric_score * confidence * conviction_weight
        contributions[agent_name] = per_video
    return contributions
