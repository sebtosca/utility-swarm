from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from langsmith import Client
from langsmith import trace as ls_trace


def tracing_enabled() -> bool:
    return bool(os.environ.get("LANGCHAIN_TRACING_V2")) and bool(
        os.environ.get("LANGCHAIN_API_KEY")
    )


def build_run_config(run_id: str, video_count: int) -> dict[str, Any]:
    return {
        "metadata": {"cjs_run_id": run_id, "video_count": video_count},
        "tags": ["creative-jury-swarm"],
    }


def invoke_with_tracing(
    compiled: Any,
    state: Any,
    config: dict[str, Any],
    run_id: str,
    video_count: int,
) -> tuple[Any, str | None]:
    if not tracing_enabled():
        return compiled.invoke(state, config=config), None

    try:
        project = os.environ.get("LANGCHAIN_PROJECT", "creative-jury-swarm")
        merged_config = {
            **config,
            "metadata": {
                **config.get("metadata", {}),
                "cjs_run_id": run_id,
                "video_count": video_count,
            },
            "tags": [*config.get("tags", []), "creative-jury-swarm"],
        }

        with ls_trace(
            "jury_run",
            project_name=project,
            metadata={"cjs_run_id": run_id, "video_count": video_count},
            tags=["creative-jury-swarm"],
        ) as rt:
            result = compiled.invoke(state, config=merged_config)

        try:
            url: str | None = Client().get_run_url(run=rt, project_name=project)
        except Exception:
            url = None

        return result, url
    except Exception:
        return compiled.invoke(state, config=config), None


def write_langsmith_url(metrics_path: Path, url: str) -> None:
    existing: dict[str, Any] = {}
    if metrics_path.exists():
        try:
            existing = json.loads(metrics_path.read_text())
        except Exception:
            pass
    existing["langsmith_url"] = url
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(existing, indent=2))
