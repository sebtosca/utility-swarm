import json
import tempfile
from pathlib import Path

from cjs.escalation.events import write_escalation_event


def test_write_creates_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "escalations.jsonl"
        write_escalation_event(path, type="test", run_id="r1")
        assert path.exists()


def test_write_appends_multiple_lines():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "escalations.jsonl"
        write_escalation_event(path, type="a", run_id="r1")
        write_escalation_event(path, type="b", run_id="r1")
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["type"] == "a"
        assert json.loads(lines[1])["type"] == "b"


def test_write_includes_ts_and_fields():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "escalations.jsonl"
        write_escalation_event(path, type="model_fallback", run_id="r1",
                               node="scoring", from_model="opus", to_model="haiku")
        entry = json.loads(path.read_text())
        assert "ts" in entry
        assert entry["type"] == "model_fallback"
        assert entry["run_id"] == "r1"
        assert entry["node"] == "scoring"
        assert entry["from_model"] == "opus"
        assert entry["to_model"] == "haiku"
