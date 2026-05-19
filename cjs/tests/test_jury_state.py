from cjs.graph.state import JuryState, _merge_dicts


def test_merge_dicts_combines_keys():
    a = {"agent_a": [{"video_path": "ad1.mp4"}]}
    b = {"agent_b": [{"video_path": "ad1.mp4"}]}
    result = _merge_dicts(a, b)
    assert "agent_a" in result
    assert "agent_b" in result


def test_merge_dicts_later_wins_on_collision():
    a = {"agent_a": ["old"]}
    b = {"agent_a": ["new"]}
    result = _merge_dicts(a, b)
    assert result["agent_a"] == ["new"]


def test_jury_state_is_typeddict():
    # TypedDict instances are plain dicts at runtime
    state: JuryState = {
        "run_id": "test",
        "brief": {},
        "rubric": {},
        "brand_rules": {},
        "video_dossiers": [],
        "initial_judgements": {},
        "consistency_report": None,
        "final_judgements": {},
        "verdict": None,
    }
    assert state["run_id"] == "test"
    assert state["initial_judgements"] == {}
