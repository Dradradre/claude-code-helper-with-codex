from pathlib import Path

from cchwc.adapters.claude_adapter import ClaudeAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_claude_session():
    adapter = ClaudeAdapter()
    parsed = adapter.parse_file(FIXTURES / "sample_claude_session.jsonl")

    assert parsed is not None
    assert parsed.agent_type == "claude"
    assert parsed.external_id == "test-session-001"
    assert parsed.cwd == "C:\\Users\\Test\\project"
    assert len(parsed.messages) == 4

    user_msgs = [m for m in parsed.messages if m.role == "user"]
    assistant_msgs = [m for m in parsed.messages if m.role == "assistant"]
    assert len(user_msgs) == 2
    assert len(assistant_msgs) == 2

    assert parsed.total_usage.input_tokens == 250
    assert parsed.total_usage.output_tokens == 55
    assert parsed.total_usage.cache_read_tokens == 500
    assert parsed.total_usage.cache_creation_tokens == 50


def test_extract_text_from_content():
    adapter = ClaudeAdapter()
    assert adapter._extract_text("hello") == "hello"
    assert adapter._extract_text([{"type": "text", "text": "world"}]) == "world"
    assert adapter._extract_text(None) is None


def test_discover_nonexistent_root():
    adapter = ClaudeAdapter(root=Path("/nonexistent/path"))
    files = list(adapter.discover_session_files())
    assert files == []
