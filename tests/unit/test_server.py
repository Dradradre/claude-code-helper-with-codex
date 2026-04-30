import pytest
from httpx import ASGITransport, AsyncClient

from cchwc.server.app import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_health(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_settings_api_saves_agent_model_and_effort(local_tmp_path, monkeypatch):
    monkeypatch.setenv("CCHWC_CONFIG_FILE", str(local_tmp_path / "config.toml"))
    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/settings",
            json={
                "agents": {
                    "claude_model": "sonnet",
                    "codex_model": "gpt-5.5",
                    "claude_effort": "high",
                    "codex_reasoning_effort": "xhigh",
                }
            },
        )

    assert response.status_code == 200
    agents = response.json()["user_config"]["agents"]
    assert agents["claude_model"] == "sonnet"
    assert agents["codex_model"] == "gpt-5.5"
    assert agents["claude_effort"] == "high"
    assert agents["codex_reasoning_effort"] == "xhigh"
