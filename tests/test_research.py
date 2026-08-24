import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from keyword_research_mcp.errors import (
    InvalidCursor,
    InvalidResearchInput,
    RateLimitExhausted,
    UpstreamGoogleAdsError,
)
from keyword_research_mcp.google_ads_adapter import (
    AdapterGeoTarget,
    AdapterGeoTargetParent,
    AdapterKeywordIdeaPage,
    AdapterKeywordMetrics,
    AdapterKeywordRow,
    AdapterLanguageConstant,
    AdapterMonthlySearchVolume,
    AdapterRateLimitError,
    AdapterTransientError,
)
from keyword_research_mcp.models import (
    GenerateKeywordIdeasInput,
    HistoricalMetricsInput,
)
from keyword_research_mcp.research import KeywordResearch
from tests.fakes import FakeGoogleAdsAdapter


class FakeTime:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.value

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


def english_adapter(
    *,
    keyword_idea_page: AdapterKeywordIdeaPage | None = None,
    keyword_idea_pages: dict[str | None, AdapterKeywordIdeaPage] | None = None,
    on_planning_request: Callable[[], None] | None = None,
) -> FakeGoogleAdsAdapter:
    return FakeGoogleAdsAdapter(
        languages=(
            AdapterLanguageConstant(
                resource_name="languageConstants/1000", code="en", name="English"
            ),
        ),
        keyword_idea_page=keyword_idea_page,
        keyword_idea_pages=keyword_idea_pages,
        on_planning_request=on_planning_request,
    )


def idea_request(
    seed: str = "keyword research", *, cursor: str | None = None, refresh: bool = False
) -> GenerateKeywordIdeasInput:
    return GenerateKeywordIdeasInput(
        seed_topics=(seed,),
        geo_target_resource_names=("geoTargetConstants/2840",),
        language_code="en",
        cursor=cursor,
        refresh=refresh,
    )


def test_keyword_ideas_reject_blank_seed_topics() -> None:
    with pytest.raises(ValidationError, match="seed_topics"):
        GenerateKeywordIdeasInput(
            seed_topics=("  ",),
            geo_target_resource_names=("geoTargetConstants/2840",),
            language_code="en",
        )


def test_keyword_ideas_use_bounded_pagination_defaults() -> None:
    request = GenerateKeywordIdeasInput(
        seed_topics=("local keyword research",),
        geo_target_resource_names=("geoTargetConstants/2840",),
        language_code="en",
    )

    assert request.page_size == 100
    assert request.cursor is None
    assert request.refresh is False


def test_keyword_ideas_reject_page_sizes_above_google_limit() -> None:
    with pytest.raises(ValidationError, match="page_size"):
        GenerateKeywordIdeasInput(
            seed_topics=("local keyword research",),
            geo_target_resource_names=("geoTargetConstants/2840",),
            language_code="en",
            page_size=1001,
        )


def test_historical_metrics_reject_more_than_one_thousand_keywords() -> None:
    with pytest.raises(ValidationError, match="keywords"):
        HistoricalMetricsInput(
            keywords=tuple(f"keyword {index}" for index in range(1_001)),
            geo_target_resource_names=("geoTargetConstants/2840",),
            language_code="en",
        )


def test_historical_metrics_reject_reversed_inclusive_period() -> None:
    with pytest.raises(ValidationError, match="historical period must end"):
        HistoricalMetricsInput(
            keywords=("keyword research",),
            geo_target_resource_names=("geoTargetConstants/2840",),
            language_code="en",
            start_year=2026,
            start_month=7,
            end_year=2026,
            end_month=6,
        )


def test_geo_resolution_rejects_blank_query_without_calling_google() -> None:
    adapter = FakeGoogleAdsAdapter()
    research = KeywordResearch(adapter)

    with pytest.raises(InvalidResearchInput, match="query must not be blank"):
        asyncio.run(research.resolve_geo_targets("  "))

    assert adapter.geo_suggestion_requests == []


def test_geo_resolution_rejects_invalid_country_restriction() -> None:
    adapter = FakeGoogleAdsAdapter()

    with pytest.raises(InvalidResearchInput, match="two-letter country code"):
        asyncio.run(
            KeywordResearch(adapter).resolve_geo_targets(
                "Springfield", country_code="USA"
            )
        )

    assert adapter.geo_suggestion_requests == []


def test_geo_resolution_preserves_all_plausible_matches_and_parents() -> None:
    adapter = FakeGoogleAdsAdapter(
        geo_targets=(
            AdapterGeoTarget(
                resource_name="geoTargetConstants/1023191",
                criterion_id=1023191,
                canonical_name="Springfield, Illinois, United States",
                country_code="US",
                target_type="City",
                status="ENABLED",
                parents=(
                    AdapterGeoTargetParent(
                        resource_name="geoTargetConstants/21132",
                        criterion_id=21132,
                        canonical_name="Illinois, United States",
                    ),
                ),
            ),
            AdapterGeoTarget(
                resource_name="geoTargetConstants/1023192",
                criterion_id=1023192,
                canonical_name="Springfield, Missouri, United States",
                country_code="US",
                target_type="City",
                status="ENABLED",
            ),
        )
    )

    result = asyncio.run(
        KeywordResearch(adapter).resolve_geo_targets(
            " Springfield ", country_code="us", locale="en"
        )
    )

    assert [match.canonical_name for match in result.matches] == [
        "Springfield, Illinois, United States",
        "Springfield, Missouri, United States",
    ]
    assert result.matches[0].parents[0].canonical_name == "Illinois, United States"
    assert adapter.geo_suggestion_requests == [("Springfield", "US", "en")]


def test_historical_metrics_preserve_zero_null_money_and_canonicalization() -> None:
    adapter = FakeGoogleAdsAdapter(
        languages=(
            AdapterLanguageConstant(
                resource_name="languageConstants/1000", code="en", name="English"
            ),
        ),
        currency_code="USD",
        historical_rows=(
            AdapterKeywordRow(
                text="keyword research tool",
                close_variants=("keyword tool research",),
                metrics=AdapterKeywordMetrics(
                    average_monthly_searches=0,
                    monthly_search_volumes=(
                        AdapterMonthlySearchVolume(year=2026, month=7, searches=None),
                    ),
                    paid_competition="UNKNOWN",
                    paid_competition_index=0,
                    average_cpc_micros=2_450_001,
                    low_top_of_page_bid_micros=None,
                    high_top_of_page_bid_micros=0,
                ),
            ),
        ),
    )
    request = HistoricalMetricsInput(
        keywords=("keyword research tools",),
        geo_target_resource_names=("geoTargetConstants/2840",),
        language_code="en",
    )

    result = asyncio.run(
        KeywordResearch(adapter).get_keyword_historical_metrics(request)
    )

    row = result.items[0]
    assert row.text == "keyword research tool"
    assert row.close_variants == ("keyword tool research",)
    assert row.metrics.average_monthly_searches == 0
    assert row.metrics.monthly_search_volumes[0].searches is None
    assert row.metrics.paid_competition is None
    assert row.metrics.paid_competition_index == 0
    assert row.metrics.low_top_of_page_bid is None
    assert row.metrics.high_top_of_page_bid is not None
    assert row.metrics.high_top_of_page_bid.micros == 0
    assert row.metrics.average_cpc is not None
    assert row.metrics.average_cpc.model_dump(mode="json") == {
        "micros": 2_450_001,
        "amount": "2.450001",
        "currency_code": "USD",
    }


def test_keyword_ideas_normalize_evidence_and_fix_google_request_semantics() -> None:
    adapter = FakeGoogleAdsAdapter(
        languages=(
            AdapterLanguageConstant(
                resource_name="languageConstants/1000", code="en", name="English"
            ),
        ),
        currency_code="USD",
        keyword_idea_page=AdapterKeywordIdeaPage(
            items=(
                AdapterKeywordRow(
                    text="local keyword research",
                    close_variants=(),
                    metrics=AdapterKeywordMetrics(
                        average_monthly_searches=1200,
                        paid_competition="HIGH",
                        average_cpc_micros=2_450_000,
                    ),
                ),
            ),
            total_size=1,
            next_page_token=None,
        ),
    )
    request = GenerateKeywordIdeasInput(
        seed_topics=("keyword research",),
        geo_target_resource_names=("geoTargetConstants/2840",),
        language_code="en",
    )

    result = asyncio.run(KeywordResearch(adapter).generate_keyword_ideas(request))

    assert result.returned_count == 1
    assert result.total_size == 1
    assert result.has_more is False
    assert result.next_cursor is None
    assert result.items[0].metrics.paid_competition == "HIGH"
    assert result.items[0].metrics.average_cpc is not None
    assert result.items[0].metrics.average_cpc.amount == Decimal("2.45")
    adapter_request = adapter.keyword_idea_requests[0]
    assert adapter_request.network == "GOOGLE_SEARCH"
    assert adapter_request.include_adult_keywords is False
    assert adapter_request.page_size == 100


def test_equivalent_idea_requests_use_cache_and_refresh_replaces_it() -> None:
    fake_time = FakeTime()
    adapter = english_adapter()
    research = KeywordResearch(
        adapter,
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        now=lambda: datetime(2026, 8, 23, tzinfo=timezone.utc),
        jitter=lambda _maximum: 0,
    )

    first = asyncio.run(research.generate_keyword_ideas(idea_request()))
    cached = asyncio.run(research.generate_keyword_ideas(idea_request()))
    refreshed = asyncio.run(research.generate_keyword_ideas(idea_request(refresh=True)))

    assert first is cached
    assert refreshed.retrieved_at == datetime(2026, 8, 23, tzinfo=timezone.utc)
    assert len(adapter.keyword_idea_requests) == 2
    assert adapter.language_requests == ["en"]
    assert adapter.currency_requests == 1


def test_lru_cache_evicts_the_least_recently_used_request() -> None:
    fake_time = FakeTime()
    adapter = english_adapter()
    research = KeywordResearch(
        adapter,
        cache_capacity=2,
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        jitter=lambda _maximum: 0,
    )

    for seed in ("one", "two", "one", "three", "two"):
        asyncio.run(research.generate_keyword_ideas(idea_request(seed)))

    assert [request.seed_topics for request in adapter.keyword_idea_requests] == [
        ("one",),
        ("two",),
        ("three",),
        ("two",),
    ]


def test_cursor_continues_the_bound_request_and_partial_page_is_honest() -> None:
    fake_time = FakeTime()
    first_page = AdapterKeywordIdeaPage(
        items=(), total_size=250, next_page_token="google-page-2"
    )
    second_page = AdapterKeywordIdeaPage(items=(), total_size=250, next_page_token=None)
    adapter = english_adapter(
        keyword_idea_pages={None: first_page, "google-page-2": second_page}
    )
    research = KeywordResearch(
        adapter,
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        jitter=lambda _maximum: 0,
    )

    first = asyncio.run(research.generate_keyword_ideas(idea_request()))

    assert first.returned_count == 0
    assert first.total_size == 250
    assert first.has_more is True
    assert first.next_cursor is not None
    second = asyncio.run(
        research.generate_keyword_ideas(idea_request(cursor=first.next_cursor))
    )
    assert second.has_more is False
    assert adapter.keyword_idea_requests[-1].page_token == "google-page-2"

    with pytest.raises(InvalidCursor, match="different request"):
        asyncio.run(
            research.generate_keyword_ideas(
                idea_request("different seed", cursor=first.next_cursor)
            )
        )


def test_cursor_is_process_local() -> None:
    first_page = AdapterKeywordIdeaPage(
        items=(), total_size=2, next_page_token="google-page-2"
    )
    first_research = KeywordResearch(english_adapter(keyword_idea_page=first_page))
    first = asyncio.run(first_research.generate_keyword_ideas(idea_request()))
    assert first.next_cursor is not None

    with pytest.raises(InvalidCursor, match="invalid, expired"):
        asyncio.run(
            KeywordResearch(english_adapter()).generate_keyword_ideas(
                idea_request(cursor=first.next_cursor)
            )
        )


def test_rate_limiter_is_shared_across_all_three_research_operations() -> None:
    fake_time = FakeTime()
    request_times: list[float] = []
    adapter = english_adapter(
        on_planning_request=lambda: request_times.append(fake_time.clock())
    )
    research = KeywordResearch(
        adapter,
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        jitter=lambda _maximum: 0,
    )

    async def run_operations() -> None:
        await research.resolve_geo_targets("United States")
        await research.get_keyword_historical_metrics(
            HistoricalMetricsInput(
                keywords=("keyword research",),
                geo_target_resource_names=("geoTargetConstants/2840",),
                language_code="en",
            )
        )
        await research.generate_keyword_ideas(idea_request())

    asyncio.run(run_operations())

    assert request_times == [0.0, 1.0, 2.0]


def test_transient_failures_retry_with_bounded_exponential_backoff() -> None:
    fake_time = FakeTime()
    adapter = english_adapter()
    adapter.keyword_idea_errors = [
        AdapterTransientError("temporary"),
        AdapterTransientError("temporary"),
    ]
    research = KeywordResearch(
        adapter,
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        jitter=lambda _maximum: 0,
    )

    asyncio.run(research.generate_keyword_ideas(idea_request()))

    assert len(adapter.keyword_idea_requests) == 3
    assert fake_time.sleeps == [1.0, 2.0]


def test_rate_limit_exhaustion_becomes_stable_domain_error() -> None:
    fake_time = FakeTime()
    adapter = english_adapter()
    adapter.keyword_idea_errors = [
        AdapterRateLimitError("quota"),
        AdapterRateLimitError("quota"),
        AdapterRateLimitError("quota"),
    ]
    research = KeywordResearch(
        adapter,
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        jitter=lambda _maximum: 0,
    )

    with pytest.raises(RateLimitExhausted, match="after retries"):
        asyncio.run(research.generate_keyword_ideas(idea_request()))

    assert len(adapter.keyword_idea_requests) == 3


def test_transient_exhaustion_becomes_upstream_error() -> None:
    fake_time = FakeTime()
    adapter = english_adapter()
    adapter.keyword_idea_errors = [
        AdapterTransientError("temporary"),
        AdapterTransientError("temporary"),
        AdapterTransientError("temporary"),
    ]
    research = KeywordResearch(
        adapter,
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        jitter=lambda _maximum: 0,
    )

    with pytest.raises(UpstreamGoogleAdsError, match="after retries"):
        asyncio.run(research.generate_keyword_ideas(idea_request()))

    assert len(adapter.keyword_idea_requests) == 3


def test_geo_resolution_is_cached_after_normalization() -> None:
    adapter = FakeGoogleAdsAdapter()
    retrieved_at = datetime(2026, 8, 23, tzinfo=timezone.utc)
    research = KeywordResearch(adapter, now=lambda: retrieved_at)

    first = asyncio.run(
        research.resolve_geo_targets(" Springfield ", country_code="us", locale="en")
    )
    second = asyncio.run(
        research.resolve_geo_targets("Springfield", country_code="US", locale=" en ")
    )

    assert first is second
    assert first.research_context.country_code == "US"
    assert first.research_context.locale == "en"
    assert first.retrieved_at == retrieved_at
    assert adapter.geo_suggestion_requests == [("Springfield", "US", "en")]


def test_historical_cache_key_includes_period_and_context_is_reproducible() -> None:
    fake_time = FakeTime()
    retrieved_at = datetime(2026, 8, 23, tzinfo=timezone.utc)
    adapter = english_adapter()
    research = KeywordResearch(
        adapter,
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        now=lambda: retrieved_at,
        jitter=lambda _maximum: 0,
    )
    default_request = HistoricalMetricsInput(
        keywords=("keyword research",),
        geo_target_resource_names=("geoTargetConstants/2840",),
        language_code="en",
    )
    explicit_request = default_request.model_copy(
        update={
            "start_year": 2026,
            "start_month": 1,
            "end_year": 2026,
            "end_month": 6,
        }
    )

    default = asyncio.run(research.get_keyword_historical_metrics(default_request))
    cached = asyncio.run(research.get_keyword_historical_metrics(default_request))
    explicit = asyncio.run(research.get_keyword_historical_metrics(explicit_request))

    assert default is cached
    assert default.research_context.historical_period.kind == (
        "GOOGLE_DEFAULT_PAST_12_MONTHS"
    )
    assert explicit.research_context.historical_period.kind == "EXPLICIT"
    assert explicit.retrieved_at == retrieved_at
    assert len(adapter.historical_metrics_requests) == 2
