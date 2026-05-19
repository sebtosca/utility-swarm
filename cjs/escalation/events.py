import json
from datetime import datetime, timezone
from pathlib import Path


def write_escalation_event(path: Path, **fields: object) -> None:
    entry = {"ts": datetime.now(timezone.utc).isoformat(), **fields}
    with open(path, "a") as fh:
        fh.write(json.dumps(entry) + "\n")
