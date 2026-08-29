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
                AdapterKeywordRow(
                    text="keyword research spreadsheet template 2019",
                    close_variants=(),
                    metrics=AdapterKeywordMetrics(average_monthly_searches=4),
                ),
            ),
            total_size=3,
            next_page_token=None,
        ),
    )
    return KeywordResearch(adapter)


def test_server_registers_every_research_tool() -> None:
    tools = asyncio.run(create_server(_research()).list_tools())

    assert {tool.name for tool in tools} == {
        "resolve_geo_targets",
        "generate_keyword_ideas",
        "get_keyword_historical_metrics",
    }


def test_generate_keyword_ideas_tool_ranks_by_volume_and_drops_noise() -> None:
    server = create_server(_research())

    result = asyncio.run(
        server.call_tool(
            "generate_keyword_ideas", {"seed_keywords": ["keyword research"]}
        )
    )

    payload = result.structured_content
    assert payload is not None
    assert [row["text"] for row in payload["items"]] == [
        "best keyword research tool",
        "how to do keyword research",
    ]
    assert payload["returned_count"] == 2


def test_generate_keyword_ideas_tool_reports_domain_errors_as_tool_errors() -> None:
    server = create_server(KeywordResearch(FakeGoogleAdsAdapter()))

    with pytest.raises(ToolError, match="no Google Ads location matched"):
        asyncio.run(
            server.call_tool(
                "generate_keyword_ideas", {"seed_keywords": ["keyword research"]}
            )
        )
