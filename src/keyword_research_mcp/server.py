"""MCP stdio entry point.

Tool registration is added in the MCP-adapter implementation phase. Keeping the
entry point executable now makes the project foundation independently verifiable.
"""

from mcp.server import MCPServer


def create_server() -> MCPServer:
    """Create the keyword research MCP server."""
    return MCPServer(
        "Keyword Research",
        instructions=(
            "Retrieve and normalize Google Ads keyword-planning evidence. "
            "Paid Competition describes advertiser activity, not organic "
            "ranking difficulty."
        ),
    )


def main() -> None:
    """Run the server over the local stdio transport."""
    create_server().run()


if __name__ == "__main__":
    main()
