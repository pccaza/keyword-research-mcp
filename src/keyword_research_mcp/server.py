"""MCP stdio entry point and tool registration.

The server exposes the normalized keyword-research interface as MCP tools. The
Google Ads adapter is built lazily on the first tool call so that the process
(and the tool list) can be inspected without credentials.
"""

from __future__ import annotations

from mcp.server import MCPServer

from keyword_research_mcp.errors import KeywordResearchError
from keyword_research_mcp.models import (
    GenerateKeywordIdeasInput,
    HistoricalMetricsInput,
)
from keyword_research_mcp.research import KeywordResearch

_INSTRUCTIONS = (
    "Retrieve and normalize Google Ads keyword-planning evidence. Start with "
    "explore_keywords for a topic: it resolves plain-text locations, returns the "
    "most-searched keywords, and groups them into content angles. Paid "
    "Competition describes advertiser activity, not organic ranking difficulty."
)


def _build_research() -> KeywordResearch:
    from keyword_research_mcp.config import load_config
    from keyword_research_mcp.google_ads_adapter import GoogleAdsAdapter

    config = load_config()
    return KeywordResearch(
        GoogleAdsAdapter.from_config(config),
        cache_capacity=config.cache_capacity,
    )


def create_server(research: KeywordResearch | None = None) -> MCPServer:
    """Create the keyword research MCP server with its tools registered."""
    server = MCPServer("Keyword Research", instructions=_INSTRUCTIONS)
    holder: dict[str, KeywordResearch | None] = {"research": research}

    def get_research() -> KeywordResearch:
        if holder["research"] is None:
            holder["research"] = _build_research()
        return holder["research"]

    @server.tool(
        description=(
            "Explore a topic end to end: resolve the location, return the "
            "most-searched keywords, and derive content angles (questions, "
            "comparisons, commercial intent, topical clusters, seasonal peaks)."
        )
    )
    async def explore_keywords(
        topic: str,
        location: str = "United States",
        language_code: str = "en",
        country_code: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        refresh: bool = False,
    ) -> dict[str, object]:
        try:
            result = await get_research().explore_topic(
                topic,
                location=location,
                language_code=language_code,
                country_code=country_code,
                limit=limit,
                cursor=cursor,
                refresh=refresh,
            )
        except KeywordResearchError as error:
            raise ValueError(str(error)) from error
        return result.model_dump(mode="json")

    @server.tool(
        description=(
            "List every plausible Google Ads location for a human-readable "
            "query, with parents, so the caller can pick a resource name."
        )
    )
    async def resolve_geo_targets(
        query: str,
        country_code: str | None = None,
        locale: str | None = None,
    ) -> dict[str, object]:
        try:
            result = await get_research().resolve_geo_targets(
                query, country_code=country_code, locale=locale
            )
        except KeywordResearchError as error:
            raise ValueError(str(error)) from error
        return result.model_dump(mode="json")

    @server.tool(
        description=(
            "Discover a bounded page of Keyword Ideas for one or more seed "
            "topics. Give a plain-text location, or explicit geo target "
            "resource names for full control."
        )
    )
    async def generate_keyword_ideas(
        seed_topics: list[str],
        location: str = "United States",
        language_code: str = "en",
        country_code: str | None = None,
        geo_target_resource_names: list[str] | None = None,
        page_size: int = 100,
        cursor: str | None = None,
        refresh: bool = False,
    ) -> dict[str, object]:
        research = get_research()
        try:
            geo_targets = geo_target_resource_names or [
                await research.resolve_primary_geo_target(
                    location, country_code=country_code
                )
            ]
            result = await research.generate_keyword_ideas(
                GenerateKeywordIdeasInput(
                    seed_topics=tuple(seed_topics),
                    geo_target_resource_names=tuple(geo_targets),
                    language_code=language_code,
                    page_size=page_size,
                    cursor=cursor,
                    refresh=refresh,
                )
            )
        except KeywordResearchError as error:
            raise ValueError(str(error)) from error
        return result.model_dump(mode="json")

    @server.tool(
        description=(
            "Enrich an existing keyword list with Historical Metrics: average "
            "monthly searches, monthly volumes, paid competition, and bids."
        )
    )
    async def get_keyword_historical_metrics(
        keywords: list[str],
        location: str = "United States",
        language_code: str = "en",
        country_code: str | None = None,
        geo_target_resource_names: list[str] | None = None,
        start_year: int | None = None,
        start_month: int | None = None,
        end_year: int | None = None,
        end_month: int | None = None,
        refresh: bool = False,
    ) -> dict[str, object]:
        research = get_research()
        try:
            geo_targets = geo_target_resource_names or [
                await research.resolve_primary_geo_target(
                    location, country_code=country_code
                )
            ]
            result = await research.get_keyword_historical_metrics(
                HistoricalMetricsInput(
                    keywords=tuple(keywords),
                    geo_target_resource_names=tuple(geo_targets),
                    language_code=language_code,
                    start_year=start_year,
                    start_month=start_month,
                    end_year=end_year,
                    end_month=end_month,
                    refresh=refresh,
                )
            )
        except KeywordResearchError as error:
            raise ValueError(str(error)) from error
        return result.model_dump(mode="json")

    return server


def main() -> None:
    """Run the server over the local stdio transport."""
    create_server().run()


if __name__ == "__main__":
    main()
