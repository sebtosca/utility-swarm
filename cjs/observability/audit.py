import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path


class AuditLogger:
    def __init__(self, run_folder: Path, run_id: str) -> None:
        self._path = run_folder / "audit.jsonl"
        self._run_id = run_id
        self._lock = threading.Lock()

    def log(
        self,
        *,
        node: str,
        agent: str | None,
        model: str,
        prompt: str,
        tokens_in: int,
        tokens_out: int,
        latency_ms: float,
        trace_id: str = "",
        error: str | None = None,
    ) -> None:
        entry: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self._run_id,
            "trace_id": trace_id,
            "node": node,
            "agent": agent,
            "model": model,
            "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest()[:16],
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": round(latency_ms, 2),
        }
        if error:
            entry["error"] = error

        with self._lock:
            with self._path.open("a") as f:
                f.write(json.dumps(entry) + "\n")
