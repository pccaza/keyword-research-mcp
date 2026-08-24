"""Deep research interface for validated, normalized keyword evidence."""

from __future__ import annotations

import asyncio
import random
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from secrets import token_urlsafe
from time import monotonic
from typing import Generic, TypeVar

from keyword_research_mcp.errors import (
    InvalidCursor,
    InvalidResearchInput,
    InvalidTargeting,
    RateLimitExhausted,
    UpstreamGoogleAdsError,
)
from keyword_research_mcp.google_ads_adapter import (
    AdapterGenerateKeywordIdeasRequest,
    AdapterHistoricalMetricsRequest,
    AdapterKeywordMetrics,
    AdapterRateLimitError,
    AdapterTransientError,
    GoogleAdsPort,
)
from keyword_research_mcp.models import (
    DefaultHistoricalPeriod,
    ExplicitHistoricalPeriod,
    GenerateKeywordIdeasInput,
    GeoResolutionContext,
    GeoTargetMatch,
    GeoTargetMatches,
    GeoTargetParent,
    HistoricalMetricsInput,
    HistoricalMetricsResult,
    KeywordIdeaPage,
    KeywordMetrics,
    KeywordRow,
    Money,
    MonthlySearchVolume,
    PaidCompetition,
    ResearchContext,
)

_MICROS_PER_UNIT = Decimal(1_000_000)
_KNOWN_COMPETITION = {"LOW", "MEDIUM", "HIGH"}
_MIN_REQUEST_INTERVAL_SECONDS = 1.0
_MAX_ATTEMPTS = 3
_INITIAL_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 4.0
_T = TypeVar("_T")

Clock = Callable[[], float]
Sleeper = Callable[[float], Awaitable[None]]
Now = Callable[[], datetime]
Jitter = Callable[[float], float]
CacheKey = tuple[Hashable, ...]


@dataclass(frozen=True, slots=True)
class _CursorState:
    page_token: str
    request_fingerprint: CacheKey


class _LruCache(Generic[_T]):
    """A small process-local LRU with no persistence or TTL."""

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("cache capacity must be positive")
        self._capacity = capacity
        self._entries: OrderedDict[CacheKey, _T] = OrderedDict()

    def get(self, key: CacheKey) -> _T | None:
        value = self._entries.get(key)
        if value is not None:
            self._entries.move_to_end(key)
        return value

    def put(self, key: CacheKey, value: _T) -> None:
        self._entries[key] = value
        self._entries.move_to_end(key)
        if len(self._entries) > self._capacity:
            self._entries.popitem(last=False)


class _RateLimiter:
    """Serialize Google Keyword Planning requests by start time."""

    def __init__(self, *, clock: Clock, sleep: Sleeper) -> None:
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._last_request_started_at: float | None = None

    async def wait(self) -> None:
        async with self._lock:
            now = self._clock()
            if self._last_request_started_at is not None:
                remaining = (
                    self._last_request_started_at + _MIN_REQUEST_INTERVAL_SECONDS - now
                )
                if remaining > 0:
                    await self._sleep(remaining)
                    now = self._clock()
            self._last_request_started_at = now


class KeywordResearch:
    """Validate, retrieve, cache, and normalize keyword-planning evidence."""

    def __init__(
        self,
        adapter: GoogleAdsPort,
        *,
        customer_cache_key: str = "configured-customer",
        cache_capacity: int = 128,
        clock: Clock = monotonic,
        sleep: Sleeper = asyncio.sleep,
        now: Now | None = None,
        jitter: Jitter | None = None,
    ) -> None:
        self._adapter = adapter
        self._customer_cache_key = customer_cache_key
        self._cache: _LruCache[object] = _LruCache(cache_capacity)
        self._cursors: dict[str, _CursorState] = {}
        self._language_resource_names: dict[str, str] = {}
        self._currency_code: str | None = None
        self._limiter = _RateLimiter(clock=clock, sleep=sleep)
        self._planning_lock = asyncio.Lock()
        self._sleep = sleep
        self._now = now or _utc_now
        self._jitter = jitter or _random_jitter

    async def resolve_geo_targets(
        self,
        query: str,
        *,
        country_code: str | None = None,
        locale: str | None = None,
    ) -> GeoTargetMatches:
        """Resolve a human-readable location without choosing ambiguities."""
        normalized_query = query.strip()
        if not normalized_query:
            raise InvalidResearchInput("query must not be blank")
        normalized_country_code = None
        if country_code is not None:
            normalized_country_code = country_code.strip().upper()
            if (
                len(normalized_country_code) != 2
                or not normalized_country_code.isalpha()
            ):
                raise InvalidResearchInput(
                    "country_code must be a two-letter country code"
                )
        normalized_locale = locale.strip() if locale is not None else None
        if normalized_locale == "":
            raise InvalidResearchInput("locale must not be blank")
        cache_key: CacheKey = (
            "geo",
            self._customer_cache_key,
            normalized_query,
            normalized_country_code,
            normalized_locale,
        )
        cached = self._cache.get(cache_key)
        if isinstance(cached, GeoTargetMatches):
            return cached

        adapter_matches = await self._call_with_retry(
            lambda: self._adapter.suggest_geo_targets(
                normalized_query,
                country_code=normalized_country_code,
                locale=normalized_locale,
            ),
            rate_limited=True,
        )
        result = GeoTargetMatches(
            query=normalized_query,
            matches=tuple(
                GeoTargetMatch(
                    resource_name=match.resource_name,
                    criterion_id=match.criterion_id,
                    canonical_name=match.canonical_name,
                    country_code=match.country_code,
                    target_type=match.target_type,
                    status=match.status,
                    parents=tuple(
                        GeoTargetParent(
                            resource_name=parent.resource_name,
                            criterion_id=parent.criterion_id,
                            canonical_name=parent.canonical_name,
                        )
                        for parent in match.parents
                    ),
                )
                for match in adapter_matches
            ),
            research_context=GeoResolutionContext(
                country_code=normalized_country_code,
                locale=normalized_locale,
            ),
            retrieved_at=self._now(),
        )
        self._cache.put(cache_key, result)
        return result

    async def get_keyword_historical_metrics(
        self, request: HistoricalMetricsInput
    ) -> HistoricalMetricsResult:
        """Retrieve and normalize Historical Metrics for existing keywords."""
        fingerprint = self._historical_fingerprint(request)
        cache_key: CacheKey = ("historical", *fingerprint)
        if not request.refresh:
            cached = self._cache.get(cache_key)
            if isinstance(cached, HistoricalMetricsResult):
                return cached

        language_resource_name = await self._resolve_language_resource_name(
            request.language_code
        )
        currency_code = await self._get_currency_code()
        rows = await self._call_with_retry(
            lambda: self._adapter.get_keyword_historical_metrics(
                AdapterHistoricalMetricsRequest(
                    keywords=request.keywords,
                    geo_target_resource_names=request.geo_target_resource_names,
                    language_resource_name=language_resource_name,
                    start_year=request.start_year,
                    start_month=request.start_month,
                    end_year=request.end_year,
                    end_month=request.end_month,
                )
            ),
            rate_limited=True,
        )
        result = HistoricalMetricsResult(
            items=tuple(
                KeywordRow(
                    text=row.text,
                    close_variants=row.close_variants,
                    metrics=_normalize_metrics(row.metrics, currency_code),
                )
                for row in rows
            ),
            research_context=ResearchContext(
                geo_target_resource_names=request.geo_target_resource_names,
                language_code=request.language_code,
                historical_period=_historical_period(request),
            ),
            retrieved_at=self._now(),
        )
        self._cache.put(cache_key, result)
        return result

    async def generate_keyword_ideas(
        self, request: GenerateKeywordIdeasInput
    ) -> KeywordIdeaPage:
        """Discover and normalize a bounded page of Keyword Ideas."""
        fingerprint = self._idea_fingerprint(request)
        page_token: str | None = None
        if request.cursor is not None:
            cursor_state = self._cursors.get(request.cursor)
            if cursor_state is None or cursor_state.request_fingerprint != fingerprint:
                raise InvalidCursor(
                    "cursor is invalid, expired, or belongs to a different request"
                )
            page_token = cursor_state.page_token

        cache_key: CacheKey = ("ideas", *fingerprint, page_token)
        if not request.refresh:
            cached = self._cache.get(cache_key)
            if isinstance(cached, KeywordIdeaPage):
                return cached

        language_resource_name = await self._resolve_language_resource_name(
            request.language_code
        )
        currency_code = await self._get_currency_code()
        page = await self._call_with_retry(
            lambda: self._adapter.generate_keyword_ideas(
                AdapterGenerateKeywordIdeasRequest(
                    seed_topics=request.seed_topics,
                    geo_target_resource_names=request.geo_target_resource_names,
                    language_resource_name=language_resource_name,
                    page_size=request.page_size,
                    page_token=page_token,
                )
            ),
            rate_limited=True,
        )
        next_cursor = None
        if page.next_page_token is not None:
            next_cursor = token_urlsafe(24)
            self._cursors[next_cursor] = _CursorState(
                page_token=page.next_page_token,
                request_fingerprint=fingerprint,
            )
        items = tuple(
            KeywordRow(
                text=row.text,
                close_variants=row.close_variants,
                metrics=_normalize_metrics(row.metrics, currency_code),
            )
            for row in page.items
        )
        result = KeywordIdeaPage(
            items=items,
            returned_count=len(items),
            total_size=page.total_size,
            has_more=page.next_page_token is not None,
            next_cursor=next_cursor,
            research_context=ResearchContext(
                geo_target_resource_names=request.geo_target_resource_names,
                language_code=request.language_code,
                historical_period=DefaultHistoricalPeriod(),
            ),
            retrieved_at=self._now(),
        )
        self._cache.put(cache_key, result)
        return result

    async def _resolve_language_resource_name(self, language_code: str) -> str:
        cached = self._language_resource_names.get(language_code)
        if cached is not None:
            return cached
        languages = await self._call_with_retry(
            lambda: self._adapter.resolve_language_code(language_code),
            rate_limited=False,
        )
        if len(languages) != 1:
            raise InvalidTargeting(
                f"language code {language_code!r} did not resolve uniquely"
            )
        resource_name = languages[0].resource_name
        self._language_resource_names[language_code] = resource_name
        return resource_name

    async def _get_currency_code(self) -> str:
        if self._currency_code is None:
            self._currency_code = await self._call_with_retry(
                self._adapter.get_customer_currency_code,
                rate_limited=False,
            )
        return self._currency_code

    async def _call_with_retry(
        self,
        operation: Callable[[], Awaitable[_T]],
        *,
        rate_limited: bool,
    ) -> _T:
        for attempt in range(_MAX_ATTEMPTS):
            try:
                if rate_limited:
                    async with self._planning_lock:
                        await self._limiter.wait()
                        return await operation()
                return await operation()
            except (AdapterRateLimitError, AdapterTransientError) as error:
                if attempt == _MAX_ATTEMPTS - 1:
                    if isinstance(error, AdapterRateLimitError):
                        raise RateLimitExhausted(
                            "Google Ads rate limits remained exhausted after retries; "
                            "try again later."
                        ) from error
                    raise UpstreamGoogleAdsError(
                        "Google Ads remained temporarily unavailable after retries."
                    ) from error
                maximum_jitter = min(
                    _INITIAL_BACKOFF_SECONDS * (2**attempt),
                    _MAX_BACKOFF_SECONDS,
                )
                await self._sleep(maximum_jitter + self._jitter(maximum_jitter))
        raise AssertionError("bounded retry loop did not return or raise")

    def _historical_fingerprint(self, request: HistoricalMetricsInput) -> CacheKey:
        return (
            self._customer_cache_key,
            request.keywords,
            request.geo_target_resource_names,
            request.language_code,
            "GOOGLE_SEARCH",
            False,
            True,
            request.start_year,
            request.start_month,
            request.end_year,
            request.end_month,
        )

    def _idea_fingerprint(self, request: GenerateKeywordIdeasInput) -> CacheKey:
        return (
            self._customer_cache_key,
            request.seed_topics,
            request.geo_target_resource_names,
            request.language_code,
            "GOOGLE_SEARCH",
            False,
            request.page_size,
        )


def _historical_period(
    request: HistoricalMetricsInput,
) -> ExplicitHistoricalPeriod | DefaultHistoricalPeriod:
    if request.start_year is None:
        return DefaultHistoricalPeriod()
    assert request.start_month is not None
    assert request.end_year is not None
    assert request.end_month is not None
    return ExplicitHistoricalPeriod(
        start_year=request.start_year,
        start_month=request.start_month,
        end_year=request.end_year,
        end_month=request.end_month,
    )


def _normalize_metrics(
    metrics: AdapterKeywordMetrics, currency_code: str
) -> KeywordMetrics:
    return KeywordMetrics(
        average_monthly_searches=metrics.average_monthly_searches,
        monthly_search_volumes=tuple(
            MonthlySearchVolume(
                year=volume.year,
                month=volume.month,
                searches=volume.searches,
            )
            for volume in metrics.monthly_search_volumes
        ),
        paid_competition=_normalize_competition(metrics.paid_competition),
        paid_competition_index=metrics.paid_competition_index,
        average_cpc=_money(metrics.average_cpc_micros, currency_code),
        low_top_of_page_bid=_money(metrics.low_top_of_page_bid_micros, currency_code),
        high_top_of_page_bid=_money(metrics.high_top_of_page_bid_micros, currency_code),
    )


def _normalize_competition(value: str | None) -> PaidCompetition | None:
    if value not in _KNOWN_COMPETITION:
        return None
    if value == "LOW":
        return "LOW"
    if value == "MEDIUM":
        return "MEDIUM"
    return "HIGH"


def _money(micros: int | None, currency_code: str) -> Money | None:
    if micros is None:
        return None
    return Money(
        micros=micros,
        amount=Decimal(micros) / _MICROS_PER_UNIT,
        currency_code=currency_code,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _random_jitter(maximum: float) -> float:
    return random.uniform(0, maximum)
