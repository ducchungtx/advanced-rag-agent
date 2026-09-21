"""Unit tests cho tool Observation an toàn."""

from app.services.agent.tools import execute_tool, format_tool_error_observation


def test_unknown_tool_returns_observation_not_raise():
    obs = execute_tool("not_a_real_tool", foo=1)
    assert obs.startswith("[TOOL_ERROR]")
    assert "UnknownTool" in obs or "Unknown tool" in obs


def test_format_tool_error_truncates_long_message():
    obs = format_tool_error_observation(
        "demo",
        ValueError("x" * 500),
        error_type="ValueError",
    )
    assert len(obs) < 600
    assert "..." in obs
