from collections.abc import Callable

from keyword_research_mcp.google_ads_adapter import (
    AdapterGenerateKeywordIdeasRequest,
    AdapterGeoTarget,
    AdapterHistoricalMetricsRequest,
    AdapterKeywordIdeaPage,
    AdapterKeywordRow,
    AdapterLanguageConstant,
)


class FakeGoogleAdsAdapter:
    def __init__(
        self,
        *,
        geo_targets: tuple[AdapterGeoTarget, ...] = (),
        languages: tuple[AdapterLanguageConstant, ...] = (),
        currency_code: str = "USD",
        historical_rows: tuple[AdapterKeywordRow, ...] = (),
        keyword_idea_page: AdapterKeywordIdeaPage | None = None,
        keyword_idea_pages: dict[str | None, AdapterKeywordIdeaPage] | None = None,
        on_planning_request: Callable[[], None] | None = None,
    ) -> None:
        self.geo_targets = geo_targets
        self.languages = languages
        self.currency_code = currency_code
        self.historical_rows = historical_rows
        self.keyword_idea_page = keyword_idea_page or AdapterKeywordIdeaPage(
            items=(), total_size=0, next_page_token=None
        )
        self.keyword_idea_pages = keyword_idea_pages or {}
        self.on_planning_request = on_planning_request
        self.geo_errors: list[Exception] = []
        self.historical_errors: list[Exception] = []
        self.keyword_idea_errors: list[Exception] = []
        self.geo_suggestion_requests: list[object] = []
        self.language_requests: list[str] = []
        self.currency_requests = 0
        self.historical_metrics_requests: list[AdapterHistoricalMetricsRequest] = []
        self.keyword_idea_requests: list[AdapterGenerateKeywordIdeasRequest] = []

    async def suggest_geo_targets(
        self,
        query: str,
        *,
        country_code: str | None,
        locale: str | None,
    ) -> tuple[AdapterGeoTarget, ...]:
        self.geo_suggestion_requests.append((query, country_code, locale))
        self._planning_request(self.geo_errors)
        return self.geo_targets

    async def resolve_language_code(
        self, language_code: str
    ) -> tuple[AdapterLanguageConstant, ...]:
        self.language_requests.append(language_code)
        return tuple(item for item in self.languages if item.code == language_code)

    async def get_customer_currency_code(self) -> str:
        self.currency_requests += 1
        return self.currency_code

    async def get_keyword_historical_metrics(
        self, request: AdapterHistoricalMetricsRequest
    ) -> tuple[AdapterKeywordRow, ...]:
        self.historical_metrics_requests.append(request)
        self._planning_request(self.historical_errors)
        return self.historical_rows

    async def generate_keyword_ideas(
        self, request: AdapterGenerateKeywordIdeasRequest
    ) -> AdapterKeywordIdeaPage:
        self.keyword_idea_requests.append(request)
        self._planning_request(self.keyword_idea_errors)
        return self.keyword_idea_pages.get(request.page_token, self.keyword_idea_page)

    def _planning_request(self, errors: list[Exception]) -> None:
        if self.on_planning_request is not None:
            self.on_planning_request()
        if errors:
            raise errors.pop(0)
