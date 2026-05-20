"""
Integration test for the full LangGraph jury swarm.
Requires a live ANTHROPIC_API_KEY. Run with:
    pytest cjs/tests/test_jury_graph_integration.py -v -m integration
"""
import tempfile
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver

from cjs.config import AuthSettings, LimitSettings, ModelSettings, RunSettings, Settings
from cjs.graph.jury_graph import build_jury_graph
from cjs.graph.state import JuryState
from cjs.router.model_router import ModelRouter
from cjs.schemas.verdict import Verdict


@pytest.mark.integration
def test_full_jury_swarm_produces_verdict():
    """Full graph with live API — two minimal video dossiers, verify verdict produced."""
    config = Settings(
        models=ModelSettings(
            text="claude-haiku-4-5-20251001",
            vision="claude-haiku-4-5-20251001",
            extended_thinking="claude-haiku-4-5-20251001",
        ),
        auth=AuthSettings(api_key_env="ANTHROPIC_API_KEY"),
        limits=LimitSettings(
            max_videos=2, max_duration_sec=60, max_frames=6,
            max_pdf_pages=10,
        ),
        run=RunSettings(out_dir="~/.cjs/runs"),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        run_folder = Path(tmpdir)
        run_id = "integration_test_run"
        router = ModelRouter(run_id=run_id, run_folder=run_folder, config=config)

        initial_state: JuryState = {
            "run_id": run_id,
            "brief": {
                "brand": "TestBrand", "objective": "Drive brand awareness",
                "platform": "YouTube", "audience": "18-34 urban consumers",
                "tone": "energetic and bold", "key_message": "Choose boldness",
                "primary_kpi": "awareness", "emotional_territory": "excitement",
                "mandatory": ["show logo by 3 seconds"], "forbidden": ["competitor names"],
                "kpi_priority": {}, "constraints": {},
            },
            "rubric": {
                "name": "awareness", "description": "Awareness campaign rubric",
                "weights": {
                    "storytelling": 0.3, "message_clarity": 0.3,
                    "audience_resonance": 0.2, "emotional_impact": 0.2,
                },
                "hard_gates": {},
            },
            "brand_rules": {
                "brand_name": "TestBrand", "mandatory_elements": ["logo visible by 3s"],
                "forbidden_elements": [], "tone_keywords": ["energetic"],
                "approved_claims": [], "prohibited_claims": [],
                "logo_visible_by_sec": 3.0, "disclaimer_required": False,
                "source": "brief_extracted",
            },
            "video_dossiers": [
                {
                    "video_path": "/test/ad1.mp4", "duration_sec": 30.0,
                    "transcript": "Be bold. Choose TestBrand. Shop now.",
                    "hook_summary": "Quick cut to product with energetic music.",
                    "scenes": [
                        {"order": 0, "timestamp_sec": 0.0,
                         "short_text_description": "Product close-up", "frame_image_paths": []},
                        {"order": 1, "timestamp_sec": 15.0,
                         "short_text_description": "Brand logo reveal", "frame_image_paths": []},
                    ],
                    "pacing": "fast", "logo_first_appearance_sec": 2.5,
                    "cta_detected": True, "cta_text": "Shop now",
                    "frames_analyzed": 6, "metadata": {},
                },
                {
                    "video_path": "/test/ad2.mp4", "duration_sec": 25.0,
                    "transcript": "Feel the difference with TestBrand.",
                    "hook_summary": "Slow reveal, emotional music.",
                    "scenes": [
                        {"order": 0, "timestamp_sec": 0.0,
                         "short_text_description": "Lifestyle shot", "frame_image_paths": []},
                    ],
                    "pacing": "slow", "logo_first_appearance_sec": 5.0,
                    "cta_detected": False, "cta_text": None,
                    "frames_analyzed": 4, "metadata": {},
                },
            ],
            "initial_judgements": {},
            "consistency_report": None,
            "final_judgements": {},
            "verdict": None,
        }

        checkpoints_db = run_folder / "checkpoints.db"
        with SqliteSaver.from_conn_string(str(checkpoints_db)) as saver:
            compiled = build_jury_graph().compile(checkpointer=saver)
            thread_config: RunnableConfig = {"configurable": {"thread_id": run_id, "router": router}}

            final_state = compiled.invoke(initial_state, config=thread_config)  # type: ignore[arg-type]

        assert len(final_state["initial_judgements"]) == 5
        assert final_state["consistency_report"] is not None
        assert len(final_state["final_judgements"]) == 5
        assert final_state["verdict"] is not None
        verdict = Verdict(**final_state["verdict"])
        assert verdict.winner_video in ["ad1.mp4", "ad2.mp4"]
        assert 0 <= verdict.confidence <= 1
        assert len(verdict.ranking) == 2
