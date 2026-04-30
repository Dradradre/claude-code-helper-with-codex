import pytest

from cchwc.orchestrator import claude_runner, codex_runner
from cchwc.orchestrator.runner import AgentResult


@pytest.mark.asyncio
async def test_claude_runner_uses_model_option(local_tmp_path, monkeypatch):
    config_path = local_tmp_path / "config.toml"
    config_path.write_text(
        """
[agents]
claude_bin = "claude-test"
claude_model = "sonnet"
claude_effort = "high"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CCHWC_CONFIG_FILE", str(config_path))
    captured = {}

    async def fake_run_agent(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["stdin_payload"] = kwargs.get("stdin_payload")
        return AgentResult(stdout="ok")

    monkeypatch.setattr(claude_runner, "run_agent", fake_run_agent)

    await claude_runner.run_claude_p("hello", model="opus", effort="xhigh")

    assert captured["cmd"] == [
        "claude-test",
        "-p",
        "--output-format",
        "text",
        "--model",
        "opus",
        "--effort",
        "xhigh",
    ]
    assert captured["stdin_payload"] == "hello"


@pytest.mark.asyncio
async def test_codex_runner_uses_model_option(local_tmp_path, monkeypatch):
    config_path = local_tmp_path / "config.toml"
    config_path.write_text(
        """
[agents]
codex_bin = "codex-test"
codex_model = "gpt-default"
codex_reasoning_effort = "high"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CCHWC_CONFIG_FILE", str(config_path))
    captured = {}

    async def fake_run_agent(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["stdin_payload"] = kwargs.get("stdin_payload")
        return AgentResult(stdout="")

    monkeypatch.setattr(codex_runner, "run_agent", fake_run_agent)

    await codex_runner.run_codex_exec("hello", model="gpt-5.1-codex", reasoning_effort="xhigh")

    assert captured["cmd"] == [
        "codex-test",
        "exec",
        "--json",
        "--model",
        "gpt-5.1-codex",
        "-c",
        'model_reasoning_effort="xhigh"',
        "-",
    ]
    assert captured["stdin_payload"] == "hello"
