import asyncio

from keyword_research_mcp.server import create_server


def test_foundation_server_has_no_tools_before_adapter_phase() -> None:
    server = create_server()

    assert server.name == "Keyword Research"
    assert asyncio.run(server.list_tools()) == []
