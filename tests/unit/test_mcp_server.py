import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_mcp_server_starts_over_stdio_and_lists_its_tools():
    # Start the real server process: an SDK upgrade that breaks the import or the protocol fails here,
    # not in a user's Claude Code session.
    params = StdioServerParameters(command=sys.executable, args=["-c", "from cchwc.mcp_server import run; run()"])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = {tool.name for tool in (await session.list_tools()).tools}
    assert tools == {"compare", "review", "debate"}
