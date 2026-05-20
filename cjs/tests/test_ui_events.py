from __future__ import annotations

import anthropic

from cjs.ui.events import handoff, llm_call_complete, llm_call_start, structured_error


def test_llm_call_start_shape():
    e = llm_call_start(node="scoring", agent="creative_strategist", model="claude-sonnet-4-6")
    assert e["type"] == "llm_call_start"
    assert e["node"] == "scoring"
    assert e["agent"] == "creative_strategist"
    assert e["model"] == "claude-sonnet-4-6"
    assert "ts" in e


def test_llm_call_complete_with_thinking():
    e = llm_call_complete(
        node="moderator_node", agent="moderator",
        model="claude-opus-4-7",
        tokens_in=1200, tokens_out=340, latency_ms=1823.4,
        thinking="Step 1: review scores...",
    )
    assert e["type"] == "llm_call_complete"
    assert e["thinking"] == "Step 1: review scores..."
    assert e["tokens_in"] == 1200
    assert round(e["latency_ms"], 1) == 1823.4


def test_llm_call_complete_without_thinking():
    e = llm_call_complete(
        node="scoring", agent=None, model="claude-sonnet-4-6",
        tokens_in=800, tokens_out=200, latency_ms=900.0,
    )
    assert e["thinking"] is None


def test_handoff_shape():
    e = handoff(from_node="scoring", to_node="consistency_checker_node", tokens_in=4200)
    assert e["type"] == "handoff"
    assert e["from_node"] == "scoring"
    assert e["tokens_in"] == 4200


def test_structured_error_low_confidence():
    from cjs.escalation.confidence_gate import LowConfidenceError
    exc = LowConfidenceError("brand_compliance confidence 23/100")
    e = structured_error(exc)
    assert e["type"] == "error"
    assert "Confidence gate" in e["what"]
    assert "23/100" in e["why"]
    assert "Undo" in e["next"]


def test_structured_error_human_review_rejected():
    from cjs.escalation.human_review import HumanReviewRejectedError
    exc = HumanReviewRejectedError("reviewer declined")
    e = structured_error(exc)
    assert e["type"] == "error"
    assert "reviewer declined" in e["why"]
    assert "new run" in e["next"]


def test_structured_error_auth():
    exc = anthropic.AuthenticationError.__new__(anthropic.AuthenticationError)
    e = structured_error(exc)
    assert e["type"] == "error"
    assert "authentication" in e["what"].lower()
    assert "cjs configure" in e["next"]


def test_structured_error_file_not_found():
    exc = FileNotFoundError("brief.pdf not found")
    e = structured_error(exc)
    assert "brief.pdf" in e["why"]
    assert "re-upload" in e["next"]


def test_structured_error_unknown_exception():
    exc = RuntimeError("something broke")
    e = structured_error(exc)
    assert e["what"] == "Unexpected error"
    assert "something broke" in e["why"]
    assert "audit.jsonl" in e["next"]
