import pytest
from pydantic import ValidationError

from cjs.schemas.verdict import Verdict


def test_verdict_valid():
    v = Verdict(
        winner_video="ad1.mp4",
        winner_rationale="Strong hook, clear CTA.",
        ranking=["ad1.mp4", "ad2.mp4"],
        per_video_notes={"ad1.mp4": "Best overall.", "ad2.mp4": "Weak ending."},
        confidence=0.87,
        flags_resolved=["agent claimed no CTA but dossier shows cta_detected=True"],
    )
    assert v.winner_video == "ad1.mp4"
    assert v.confidence == 0.87


def test_verdict_confidence_out_of_range():
    with pytest.raises(ValidationError):
        Verdict(
            winner_video="ad1.mp4",
            winner_rationale="x",
            ranking=["ad1.mp4"],
            per_video_notes={},
            confidence=1.5,
        )


def test_verdict_flags_resolved_defaults_empty():
    v = Verdict(
        winner_video="ad1.mp4",
        winner_rationale="x",
        ranking=["ad1.mp4"],
        per_video_notes={},
        confidence=0.9,
    )
    assert v.flags_resolved == []
