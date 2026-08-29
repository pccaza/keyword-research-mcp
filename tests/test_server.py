import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from keyword_research_mcp.google_ads_adapter import (
    AdapterGeoTarget,
    AdapterKeywordIdeaPage,
    AdapterKeywordMetrics,
    AdapterKeywordRow,
    AdapterLanguageConstant,
)
from keyword_research_mcp.research import KeywordResearch
from keyword_research_mcp.server import create_server
from tests.fakes import FakeGoogleAdsAdapter


def _research() -> KeywordResearch:
    adapter = FakeGoogleAdsAdapter(
        geo_targets=(
            AdapterGeoTarget(
                resource_name="geoTargetConstants/2840",
                criterion_id=2840,
                canonical_name="United States",
                country_code="US",
                target_type="Country",
                status="ENABLED",
            ),
        ),
        languages=(
            AdapterLanguageConstant(
                resource_name="languageConstants/1000", code="en", name="English"
            ),
        ),
        keyword_idea_page=AdapterKeywordIdeaPage(
            items=(
                AdapterKeywordRow(
                    text="how to do keyword research",
                    close_variants=(),
                    metrics=AdapterKeywordMetrics(average_monthly_searches=900),
                ),
                AdapterKeywordRow(
                    text="best keyword research tool",
                    close_variants=(),
                    metrics=AdapterKeywordMetrics(average_monthly_searches=2400),
                ),
            ),
            total_size=2,
            next_page_token=None,
        ),
    )
    return KeywordResearch(adapter)


def test_server_registers_every_research_tool() -> None:
    tools = asyncio.run(create_server(_research()).list_tools())

    assert {tool.name for tool in tools} == {
        "explore_keywords",
        "resolve_geo_targets",
        "generate_keyword_ideas",
        "get_keyword_historical_metrics",
    }


def test_explore_keywords_tool_returns_ranked_keywords_and_content_ideas() -> None:
    server = create_server(_research())

    result = asyncio.run(
        server.call_tool("explore_keywords", {"topic": "keyword research"})
    )

    payload = result.structured_content
    assert payload is not None
    assert [row["text"] for row in payload["keywords"]] == [
        "best keyword research tool",
        "how to do keyword research",
    ]
    assert "how to do keyword research" in payload["content_ideas"]["questions"]
    assert "best keyword research tool" in payload["content_ideas"]["commercial"]


def test_explore_keywords_tool_reports_domain_errors_as_tool_errors() -> None:
    server = create_server(KeywordResearch(FakeGoogleAdsAdapter()))

    with pytest.raises(ToolError, match="no Google Ads location matched"):
        asyncio.run(server.call_tool("explore_keywords", {"topic": "keyword research"}))
