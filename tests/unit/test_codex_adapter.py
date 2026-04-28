from pathlib import Path

from cchwc.adapters.codex_adapter import CodexAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_codex_session():
    adapter = CodexAdapter()
    parsed = adapter.parse_file(FIXTURES / "sample_codex_session.jsonl")

    assert parsed is not None
    assert parsed.agent_type == "codex"
    assert parsed.external_id == "codex-test-001"
    assert parsed.cwd == "C:\\Users\\Test\\project"

    assert len(parsed.messages) >= 2

    roles = [m.role for m in parsed.messages]
    assert "user" in roles
    assert "assistant" in roles
    assert "tool_use" in roles
    assert "tool_result" in roles

    assert parsed.total_usage.input_tokens == 500
    assert parsed.total_usage.output_tokens == 80
    assert parsed.total_usage.cache_read_tokens == 100


def test_extract_cwd_from_env_context():
    adapter = CodexAdapter()
    text = "<environment_context>\n  <cwd>C:\\Users\\Test\\project</cwd>\n</environment_context>"
    assert adapter._extract_cwd_from_env_context(text) == "C:\\Users\\Test\\project"


def test_discover_nonexistent_root():
    adapter = CodexAdapter(root=Path("/nonexistent/path"))
    files = list(adapter.discover_session_files())
    assert files == []
