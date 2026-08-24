import asyncio
from collections.abc import Iterator
from typing import cast

import grpc
import pytest
from google.ads.googleads.client import (  # pyright: ignore[reportMissingTypeStubs]
    GoogleAdsClient,
)
from google.ads.googleads.errors import (  # pyright: ignore[reportMissingTypeStubs]
    GoogleAdsException,
)
from google.ads.googleads.v25.common.types.keyword_plan_common import (
    KeywordPlanHistoricalMetrics,
    MonthlySearchVolume,
)
from google.ads.googleads.v25.errors.types.errors import GoogleAdsFailure
from google.ads.googleads.v25.resources.types.customer import Customer
from google.ads.googleads.v25.resources.types.geo_target_constant import (
    GeoTargetConstant,
)
from google.ads.googleads.v25.resources.types.language_constant import (
    LanguageConstant,
)
from google.ads.googleads.v25.services.types.geo_target_constant_service import (
    SuggestGeoTargetConstantsRequest,
    SuggestGeoTargetConstantsResponse,
)
from google.ads.googleads.v25.services.types.google_ads_service import (
    GoogleAdsRow,
    SearchGoogleAdsRequest,
)
from google.ads.googleads.v25.services.types.keyword_plan_idea_service import (
    GenerateKeywordHistoricalMetricsRequest,
    GenerateKeywordHistoricalMetricsResponse,
    GenerateKeywordIdeaResponse,
    GenerateKeywordIdeasRequest,
)
from google.api_core.exceptions import ServiceUnavailable
from google.auth.exceptions import RefreshError

from keyword_research_mcp.config import load_config
from keyword_research_mcp.errors import GoogleAdsAuthorizationError
from keyword_research_mcp.google_ads_adapter import (
    AdapterGenerateKeywordIdeasRequest,
    AdapterHistoricalMetricsRequest,
    AdapterTransientError,
    GeoTargetConstantServicePort,
    GoogleAdsAdapter,
    GoogleAdsServicePort,
    GoogleAdsServices,
    KeywordPlanIdeaServicePort,
)


class FakeGeoTargetConstantService:
    def __init__(self, response: SuggestGeoTargetConstantsResponse) -> None:
        self.response = response
        self.requests: list[SuggestGeoTargetConstantsRequest] = []

    def suggest_geo_target_constants(
        self, request: SuggestGeoTargetConstantsRequest
    ) -> SuggestGeoTargetConstantsResponse:
        self.requests.append(request)
        return self.response


class FailingGeoTargetConstantService:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def suggest_geo_target_constants(
        self, request: SuggestGeoTargetConstantsRequest
    ) -> SuggestGeoTargetConstantsResponse:
        raise self.error


class FakeGoogleAdsService:
    def __init__(self, rows: tuple[GoogleAdsRow, ...]) -> None:
        self.rows = rows
        self.requests: list[SearchGoogleAdsRequest] = []

    def search(self, request: SearchGoogleAdsRequest) -> tuple[GoogleAdsRow, ...]:
        self.requests.append(request)
        return self.rows


class FakeKeywordPlanIdeaService:
    def __init__(
        self,
        historical_response: GenerateKeywordHistoricalMetricsResponse | None = None,
        idea_response: GenerateKeywordIdeaResponse | None = None,
    ) -> None:
        self.historical_response = (
            historical_response or GenerateKeywordHistoricalMetricsResponse()
        )
        self.idea_response = idea_response or GenerateKeywordIdeaResponse()
        self.historical_requests: list[GenerateKeywordHistoricalMetricsRequest] = []
        self.idea_requests: list[GenerateKeywordIdeasRequest] = []

    def generate_keyword_historical_metrics(
        self, request: GenerateKeywordHistoricalMetricsRequest
    ) -> GenerateKeywordHistoricalMetricsResponse:
        self.historical_requests.append(request)
        return self.historical_response

    def generate_keyword_ideas(
        self, request: GenerateKeywordIdeasRequest
    ) -> "FakeKeywordIdeasPager":
        self.idea_requests.append(request)
        return FakeKeywordIdeasPager(self.idea_response)


class FakeKeywordIdeasPager:
    def __init__(self, response: GenerateKeywordIdeaResponse) -> None:
        self.response = response

    @property
    def pages(self) -> Iterator[GenerateKeywordIdeaResponse]:
        yield self.response


def test_geo_suggestions_translate_v25_protobufs_without_choosing_a_match() -> None:
    response = SuggestGeoTargetConstantsResponse(
        geo_target_constant_suggestions=(
            {
                "geo_target_constant": GeoTargetConstant(
                    resource_name="geoTargetConstants/1023191",
                    id=1023191,
                    canonical_name="Springfield, Illinois, United States",
                    country_code="US",
                    target_type="City",
                    status="ENABLED",
                ),
                "geo_target_constant_parents": (
                    GeoTargetConstant(
                        resource_name="geoTargetConstants/21132",
                        id=21132,
                        canonical_name="Illinois, United States",
                    ),
                ),
            },
            {
                "geo_target_constant": GeoTargetConstant(
                    resource_name="geoTargetConstants/1023192",
                    id=1023192,
                    canonical_name="Springfield, Missouri, United States",
                    country_code="US",
                    target_type="City",
                    status="ENABLED",
                ),
            },
        )
    )
    geo_service = FakeGeoTargetConstantService(response)
    adapter = GoogleAdsAdapter(
        customer_id="1234567890",
        services=GoogleAdsServices(
            geo_target_constant=geo_service,
            keyword_plan_idea=cast(KeywordPlanIdeaServicePort, object()),
            google_ads=cast(GoogleAdsServicePort, object()),
        ),
    )

    matches = asyncio.run(
        adapter.suggest_geo_targets("Springfield", country_code="US", locale="en")
    )

    assert [match.canonical_name for match in matches] == [
        "Springfield, Illinois, United States",
        "Springfield, Missouri, United States",
    ]
    assert matches[0].parents[0].criterion_id == 21132
    assert matches[0].status == "ENABLED"
    sent = geo_service.requests[0]
    assert sent.location_names.names == ["Springfield"]
    assert sent.country_code == "US"
    assert sent.locale == "en"


def test_language_resolution_uses_v25_constants_without_protobuf_leakage() -> None:
    google_ads_service = FakeGoogleAdsService(
        (
            GoogleAdsRow(
                language_constant=LanguageConstant(
                    resource_name="languageConstants/1000",
                    code="en",
                    name="English",
                )
            ),
        )
    )
    adapter = GoogleAdsAdapter(
        customer_id="1234567890",
        services=GoogleAdsServices(
            geo_target_constant=cast(GeoTargetConstantServicePort, object()),
            keyword_plan_idea=cast(KeywordPlanIdeaServicePort, object()),
            google_ads=google_ads_service,
        ),
    )

    matches = asyncio.run(adapter.resolve_language_code("en"))

    assert matches[0].resource_name == "languageConstants/1000"
    assert matches[0].code == "en"
    sent = google_ads_service.requests[0]
    assert sent.customer_id == "1234567890"
    assert "language_constant.code = 'en'" in sent.query


def test_customer_currency_lookup_returns_configured_account_currency() -> None:
    google_ads_service = FakeGoogleAdsService(
        (GoogleAdsRow(customer=Customer(currency_code="USD")),)
    )
    adapter = GoogleAdsAdapter(
        customer_id="1234567890",
        services=GoogleAdsServices(
            geo_target_constant=cast(GeoTargetConstantServicePort, object()),
            keyword_plan_idea=cast(KeywordPlanIdeaServicePort, object()),
            google_ads=google_ads_service,
        ),
    )

    currency_code = asyncio.run(adapter.get_customer_currency_code())

    assert currency_code == "USD"
    assert "customer.currency_code" in google_ads_service.requests[0].query


def test_historical_metrics_preserve_v25_optional_scalar_presence() -> None:
    keyword_service = FakeKeywordPlanIdeaService(
        GenerateKeywordHistoricalMetricsResponse(
            results=(
                {
                    "text": "keyword research tool",
                    "close_variants": ("keyword tool research",),
                    "keyword_metrics": KeywordPlanHistoricalMetrics(
                        avg_monthly_searches=0,
                        monthly_search_volumes=(
                            MonthlySearchVolume(year=2026, month="JULY"),
                        ),
                        competition="UNKNOWN",
                        competition_index=0,
                        average_cpc_micros=2_450_001,
                        high_top_of_page_bid_micros=0,
                    ),
                },
            )
        )
    )
    adapter = GoogleAdsAdapter(
        customer_id="1234567890",
        services=GoogleAdsServices(
            geo_target_constant=cast(GeoTargetConstantServicePort, object()),
            keyword_plan_idea=cast(KeywordPlanIdeaServicePort, keyword_service),
            google_ads=cast(GoogleAdsServicePort, object()),
        ),
    )

    rows = asyncio.run(
        adapter.get_keyword_historical_metrics(
            AdapterHistoricalMetricsRequest(
                keywords=("keyword research tools",),
                geo_target_resource_names=("geoTargetConstants/2840",),
                language_resource_name="languageConstants/1000",
                start_year=2026,
                start_month=1,
                end_year=2026,
                end_month=7,
            )
        )
    )

    metrics = rows[0].metrics
    assert metrics.average_monthly_searches == 0
    assert metrics.monthly_search_volumes[0].searches is None
    assert metrics.low_top_of_page_bid_micros is None
    assert metrics.high_top_of_page_bid_micros == 0
    assert metrics.average_cpc_micros == 2_450_001
    sent = keyword_service.historical_requests[0]
    assert sent.customer_id == "1234567890"
    assert sent.keyword_plan_network.name == "GOOGLE_SEARCH"
    assert sent.include_adult_keywords is False
    assert sent.historical_metrics_options.include_average_cpc is True
    assert sent.historical_metrics_options.year_month_range.start.month.name == (
        "JANUARY"
    )
    assert sent.historical_metrics_options.year_month_range.end.month.name == "JULY"


def test_keyword_ideas_return_only_the_requested_v25_page() -> None:
    keyword_service = FakeKeywordPlanIdeaService(
        idea_response=GenerateKeywordIdeaResponse(
            results=(
                {
                    "text": "local keyword research",
                    "close_variants": (),
                    "keyword_idea_metrics": KeywordPlanHistoricalMetrics(
                        avg_monthly_searches=1200,
                        competition="MEDIUM",
                    ),
                },
            ),
            total_size=250,
            next_page_token="google-next-page-token",
        )
    )
    adapter = GoogleAdsAdapter(
        customer_id="1234567890",
        services=GoogleAdsServices(
            geo_target_constant=cast(GeoTargetConstantServicePort, object()),
            keyword_plan_idea=cast(KeywordPlanIdeaServicePort, keyword_service),
            google_ads=cast(GoogleAdsServicePort, object()),
        ),
    )

    page = asyncio.run(
        adapter.generate_keyword_ideas(
            AdapterGenerateKeywordIdeasRequest(
                seed_topics=("keyword research", "content research"),
                geo_target_resource_names=("geoTargetConstants/2840",),
                language_resource_name="languageConstants/1000",
                page_size=100,
                page_token="google-current-page-token",
            )
        )
    )

    assert len(page.items) == 1
    assert page.items[0].text == "local keyword research"
    assert page.total_size == 250
    assert page.next_page_token == "google-next-page-token"
    sent = keyword_service.idea_requests[0]
    assert sent.keyword_seed.keywords == ["keyword research", "content research"]
    assert sent.page_size == 100
    assert sent.page_token == "google-current-page-token"
    assert sent.keyword_plan_network.name == "GOOGLE_SEARCH"
    assert sent.include_adult_keywords is False


def test_production_adapter_constructs_explicit_v25_google_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config(
        environ={
            "GOOGLE_ADS_DEVELOPER_TOKEN": "developer-token-placeholder",
            "GOOGLE_ADS_CUSTOMER_ID": "1234567890",
            "GOOGLE_ADS_CLIENT_ID": "client-id-placeholder",
            "GOOGLE_ADS_CLIENT_SECRET": "client-secret-placeholder",
            "GOOGLE_ADS_REFRESH_TOKEN": "refresh-token-placeholder",
        }
    )

    captured: list[tuple[dict[str, str | bool], str | None]] = []

    class FakeClient:
        def get_service(self, name: str, *, version: str) -> object:
            assert name in {
                "GeoTargetConstantService",
                "KeywordPlanIdeaService",
                "GoogleAdsService",
            }
            assert version == "v25"
            return object()

    def fake_load_from_dict(
        values: dict[str, str | bool], version: str | None = None
    ) -> FakeClient:
        captured.append((values, version))
        return FakeClient()

    monkeypatch.setattr(
        GoogleAdsClient, "load_from_dict", staticmethod(fake_load_from_dict)
    )

    adapter = GoogleAdsAdapter.from_config(config)

    assert adapter.api_version == "v25"
    assert captured[0][1] == "v25"
    assert captured[0][0]["use_proto_plus"] is True


def test_google_authentication_failure_becomes_secret_safe_domain_error() -> None:
    failure = GoogleAdsFailure(
        errors=(
            {
                "error_code": {"authentication_error": "OAUTH_TOKEN_INVALID"},
                "message": "sensitive-upstream-message",
            },
        )
    )
    google_error = GoogleAdsException(
        cast(grpc.RpcError, object()),
        cast(grpc.Call, object()),
        failure,
        "sensitive-request-id",
    )
    adapter = GoogleAdsAdapter(
        customer_id="1234567890",
        services=GoogleAdsServices(
            geo_target_constant=FailingGeoTargetConstantService(google_error),
            keyword_plan_idea=cast(KeywordPlanIdeaServicePort, object()),
            google_ads=cast(GoogleAdsServicePort, object()),
        ),
    )

    with pytest.raises(GoogleAdsAuthorizationError) as captured:
        asyncio.run(
            adapter.suggest_geo_targets("Chicago", country_code="US", locale="en")
        )

    assert "authentication or authorization" in str(captured.value)
    assert "sensitive" not in str(captured.value)
    assert "1234567890" not in str(captured.value)


def test_retryable_transport_failure_becomes_secret_safe_adapter_error() -> None:
    adapter = GoogleAdsAdapter(
        customer_id="1234567890",
        services=GoogleAdsServices(
            geo_target_constant=FailingGeoTargetConstantService(
                ServiceUnavailable("sensitive-transport-details")
            ),
            keyword_plan_idea=cast(KeywordPlanIdeaServicePort, object()),
            google_ads=cast(GoogleAdsServicePort, object()),
        ),
    )

    with pytest.raises(AdapterTransientError) as captured:
        asyncio.run(
            adapter.suggest_geo_targets("Chicago", country_code="US", locale="en")
        )

    assert "temporarily unavailable" in str(captured.value)
    assert "sensitive" not in str(captured.value)


def test_client_authentication_startup_failure_is_secret_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config(
        environ={
            "GOOGLE_ADS_DEVELOPER_TOKEN": "developer-token-placeholder",
            "GOOGLE_ADS_CUSTOMER_ID": "1234567890",
            "GOOGLE_ADS_CLIENT_ID": "client-id-placeholder",
            "GOOGLE_ADS_CLIENT_SECRET": "client-secret-placeholder",
            "GOOGLE_ADS_REFRESH_TOKEN": "refresh-token-placeholder",
        }
    )

    def fail_to_load(values: dict[str, str | bool], version: str | None = None) -> None:
        raise RefreshError("sensitive-oauth-details")

    monkeypatch.setattr(GoogleAdsClient, "load_from_dict", staticmethod(fail_to_load))

    with pytest.raises(GoogleAdsAuthorizationError) as captured:
        GoogleAdsAdapter.from_config(config)

    assert "credentials" in str(captured.value)
    assert "sensitive" not in str(captured.value)
