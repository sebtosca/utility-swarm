from __future__ import annotations

import time


def llm_call_start(*, node: str, agent: str | None, model: str) -> dict:
    return {
        "type": "llm_call_start",
        "ts": time.time(),
        "node": node,
        "agent": agent,
        "model": model,
    }


def llm_call_complete(
    *,
    node: str,
    agent: str | None,
    model: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: float,
    thinking: str | None = None,
) -> dict:
    return {
        "type": "llm_call_complete",
        "ts": time.time(),
        "node": node,
        "agent": agent,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": round(latency_ms, 1),
        "thinking": thinking,
    }


def handoff(*, from_node: str, to_node: str, tokens_in: int) -> dict:
    return {
        "type": "handoff",
        "ts": time.time(),
        "from_node": from_node,
        "to_node": to_node,
        "tokens_in": tokens_in,
    }


def structured_error(exc: Exception) -> dict:
    import anthropic as _anthropic

    from cjs.escalation.confidence_gate import LowConfidenceError
    from cjs.escalation.human_review import HumanReviewRejectedError

    if isinstance(exc, LowConfidenceError):
        return {
            "type": "error",
            "ts": time.time(),
            "what": "Confidence gate blocked the run",
            "why": str(exc),
            "next": "Click Undo to return to deliberation, or lower the --strict-confidence threshold",
        }
    if isinstance(exc, HumanReviewRejectedError):
        return {
            "type": "error",
            "ts": time.time(),
            "what": "Human reviewer rejected the run",
            "why": str(exc),
            "next": "Review the jury record in the report, then start a new run",
        }
    if isinstance(exc, _anthropic.AuthenticationError):
        return {
            "type": "error",
            "ts": time.time(),
            "what": "Anthropic API authentication failed",
            "why": "Invalid or missing API key",
            "next": "Run `cjs configure` to set your ANTHROPIC_API_KEY",
        }
    if isinstance(exc, FileNotFoundError):
        return {
            "type": "error",
            "ts": time.time(),
            "what": "Required file not found",
            "why": str(exc),
            "next": "Check the file path and re-upload",
        }
    return {
        "type": "error",
        "ts": time.time(),
        "what": "Unexpected error",
        "why": str(exc),
        "next": "Check audit.jsonl in the run folder for the full traceback",
    }
