"""Internal, protobuf-free port for the Google Ads boundary."""

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar, cast

from google.ads.googleads.client import (  # pyright: ignore[reportMissingTypeStubs]
    GoogleAdsClient,
)
from google.ads.googleads.errors import (  # pyright: ignore[reportMissingTypeStubs]
    GoogleAdsException,
)
from google.ads.googleads.v25.common.types.keyword_plan_common import (
    KeywordPlanHistoricalMetrics,
)
from google.ads.googleads.v25.enums.types.month_of_year import MonthOfYearEnum
from google.ads.googleads.v25.errors.types.errors import GoogleAdsFailure
from google.ads.googleads.v25.resources.types.geo_target_constant import (
    GeoTargetConstant,
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
from google.api_core.exceptions import (
    DeadlineExceeded,
    GoogleAPICallError,
    ResourceExhausted,
    ServiceUnavailable,
)
from google.auth.exceptions import GoogleAuthError

from keyword_research_mcp.config import (
    GoogleAdsConfig,
    UserOAuthConfig,
)
from keyword_research_mcp.errors import (
    GoogleAdsAuthorizationError,
    GoogleAdsPolicyError,
    InvalidConfiguration,
    UpstreamGoogleAdsError,
)

_API_VERSION = "v25"
_T = TypeVar("_T")


class AdapterTransientError(UpstreamGoogleAdsError):
    """A retryable Google transport or availability failure."""


class AdapterRateLimitError(UpstreamGoogleAdsError):
    """A retryable Google Ads quota exhaustion failure."""


@dataclass(frozen=True, slots=True)
class AdapterGeoTargetParent:
    resource_name: str
    criterion_id: int
    canonical_name: str


@dataclass(frozen=True, slots=True)
class AdapterGeoTarget:
    resource_name: str
    criterion_id: int
    canonical_name: str
    country_code: str
    target_type: str
    status: str
    parents: tuple[AdapterGeoTargetParent, ...] = ()


@dataclass(frozen=True, slots=True)
class AdapterLanguageConstant:
    resource_name: str
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class AdapterMonthlySearchVolume:
    year: int
    month: int
    searches: int | None


@dataclass(frozen=True, slots=True)
class AdapterKeywordMetrics:
    average_monthly_searches: int | None = None
    monthly_search_volumes: tuple[AdapterMonthlySearchVolume, ...] = ()
    paid_competition: str | None = None
    paid_competition_index: int | None = None
    average_cpc_micros: int | None = None
    low_top_of_page_bid_micros: int | None = None
    high_top_of_page_bid_micros: int | None = None


@dataclass(frozen=True, slots=True)
class AdapterKeywordRow:
    text: str
    close_variants: tuple[str, ...]
    metrics: AdapterKeywordMetrics


@dataclass(frozen=True, slots=True)
class AdapterHistoricalMetricsRequest:
    keywords: tuple[str, ...]
    geo_target_resource_names: tuple[str, ...]
    language_resource_name: str
    network: Literal["GOOGLE_SEARCH"] = "GOOGLE_SEARCH"
    include_adult_keywords: bool = False
    include_average_cpc: bool = True
    start_year: int | None = None
    start_month: int | None = None
    end_year: int | None = None
    end_month: int | None = None


@dataclass(frozen=True, slots=True)
class AdapterGenerateKeywordIdeasRequest:
    seed_topics: tuple[str, ...]
    geo_target_resource_names: tuple[str, ...]
    language_resource_name: str
    page_size: int
    page_token: str | None = None
    network: Literal["GOOGLE_SEARCH"] = "GOOGLE_SEARCH"
    include_adult_keywords: bool = False


@dataclass(frozen=True, slots=True)
class AdapterKeywordIdeaPage:
    items: tuple[AdapterKeywordRow, ...]
    total_size: int | None
    next_page_token: str | None


class GeoTargetConstantServicePort(Protocol):
    def suggest_geo_target_constants(
        self, request: SuggestGeoTargetConstantsRequest
    ) -> SuggestGeoTargetConstantsResponse: ...


class KeywordPlanIdeaServicePort(Protocol):
    """Structural seam for the generated Keyword Plan Idea service."""

    def generate_keyword_historical_metrics(
        self, request: GenerateKeywordHistoricalMetricsRequest
    ) -> GenerateKeywordHistoricalMetricsResponse: ...

    def generate_keyword_ideas(
        self, request: GenerateKeywordIdeasRequest
    ) -> "KeywordIdeasPagerPort": ...


class KeywordIdeasPagerPort(Protocol):
    @property
    def pages(self) -> Iterator[GenerateKeywordIdeaResponse]: ...


class GoogleAdsServicePort(Protocol):
    """Structural seam for the generated Google Ads search service."""

    def search(self, request: SearchGoogleAdsRequest) -> Iterable[GoogleAdsRow]: ...


class GoogleAdsClientPort(Protocol):
    def get_service(self, name: str, *, version: str) -> object: ...


@dataclass(frozen=True, slots=True)
class GoogleAdsServices:
    geo_target_constant: GeoTargetConstantServicePort
    keyword_plan_idea: KeywordPlanIdeaServicePort
    google_ads: GoogleAdsServicePort


class GoogleAdsAdapter:
    """Production Google Ads v25 adapter."""

    def __init__(self, *, customer_id: str, services: GoogleAdsServices) -> None:
        self._customer_id = customer_id
        self._services = services

    @property
    def api_version(self) -> str:
        return _API_VERSION

    @classmethod
    def from_config(cls, config: GoogleAdsConfig) -> "GoogleAdsAdapter":
        """Construct the production services using the official v25 client."""
        client_values: dict[str, str | bool] = {
            "developer_token": config.developer_token,
            "use_proto_plus": True,
        }
        if config.login_customer_id is not None:
            client_values["login_customer_id"] = config.login_customer_id
        if isinstance(config.authentication, UserOAuthConfig):
            client_values.update(
                {
                    "client_id": config.authentication.client_id,
                    "client_secret": config.authentication.client_secret,
                    "refresh_token": config.authentication.refresh_token,
                }
            )
        else:
            client_values["json_key_file_path"] = (
                config.authentication.json_key_file_path
            )
            if config.authentication.impersonated_email is not None:
                client_values["impersonated_email"] = (
                    config.authentication.impersonated_email
                )
        try:
            client = GoogleAdsClient.load_from_dict(
                client_values,
                version=_API_VERSION,
            )
        except GoogleAuthError as error:
            raise GoogleAdsAuthorizationError(
                "Google Ads credentials could not be authenticated."
            ) from error
        except (OSError, ValueError) as error:
            raise InvalidConfiguration(
                "Google Ads client configuration is invalid; see "
                "README.md#google-ads-configuration."
            ) from error
        client_port = cast(GoogleAdsClientPort, client)
        return cls(
            customer_id=config.customer_id,
            services=GoogleAdsServices(
                geo_target_constant=cast(
                    GeoTargetConstantServicePort,
                    client_port.get_service(
                        "GeoTargetConstantService", version=_API_VERSION
                    ),
                ),
                keyword_plan_idea=cast(
                    KeywordPlanIdeaServicePort,
                    client_port.get_service(
                        "KeywordPlanIdeaService", version=_API_VERSION
                    ),
                ),
                google_ads=cast(
                    GoogleAdsServicePort,
                    client_port.get_service("GoogleAdsService", version=_API_VERSION),
                ),
            ),
        )

    async def suggest_geo_targets(
        self,
        query: str,
        *,
        country_code: str | None,
        locale: str | None,
    ) -> tuple[AdapterGeoTarget, ...]:
        request = SuggestGeoTargetConstantsRequest()
        request.location_names.names.append(query)
        if country_code is not None:
            request.country_code = country_code
        if locale is not None:
            request.locale = locale
        response = _call_google(
            lambda: self._services.geo_target_constant.suggest_geo_target_constants(
                request
            )
        )
        return tuple(
            AdapterGeoTarget(
                resource_name=suggestion.geo_target_constant.resource_name,
                criterion_id=_criterion_id(suggestion.geo_target_constant),
                canonical_name=suggestion.geo_target_constant.canonical_name,
                country_code=suggestion.geo_target_constant.country_code,
                target_type=suggestion.geo_target_constant.target_type,
                status=suggestion.geo_target_constant.status.name,
                parents=tuple(
                    AdapterGeoTargetParent(
                        resource_name=parent.resource_name,
                        criterion_id=_criterion_id(parent),
                        canonical_name=parent.canonical_name,
                    )
                    for parent in suggestion.geo_target_constant_parents
                ),
            )
            for suggestion in response.geo_target_constant_suggestions
        )

    async def resolve_language_code(
        self, language_code: str
    ) -> tuple[AdapterLanguageConstant, ...]:
        escaped_code = _escape_gaql_string(language_code)
        request = SearchGoogleAdsRequest(
            customer_id=self._customer_id,
            query=(
                "SELECT language_constant.resource_name, language_constant.code, "
                "language_constant.name FROM language_constant "
                f"WHERE language_constant.code = '{escaped_code}'"
            ),
        )
        rows = _call_google(lambda: self._services.google_ads.search(request))
        return tuple(
            AdapterLanguageConstant(
                resource_name=row.language_constant.resource_name,
                code=row.language_constant.code,
                name=row.language_constant.name,
            )
            for row in rows
        )

    async def get_customer_currency_code(self) -> str:
        request = SearchGoogleAdsRequest(
            customer_id=self._customer_id,
            query="SELECT customer.currency_code FROM customer LIMIT 1",
        )
        rows = _call_google(lambda: self._services.google_ads.search(request))
        row = next(iter(rows), None)
        if row is None or not row.customer.currency_code:
            raise UpstreamGoogleAdsError(
                "Google Ads did not return the configured customer's currency."
            )
        return row.customer.currency_code

    async def get_keyword_historical_metrics(
        self, request: AdapterHistoricalMetricsRequest
    ) -> tuple[AdapterKeywordRow, ...]:
        google_request = GenerateKeywordHistoricalMetricsRequest(
            customer_id=self._customer_id,
            keywords=request.keywords,
            language=request.language_resource_name,
            include_adult_keywords=request.include_adult_keywords,
            geo_target_constants=request.geo_target_resource_names,
            keyword_plan_network=request.network,
        )
        google_request.historical_metrics_options.include_average_cpc = (
            request.include_average_cpc
        )
        if request.start_year is not None:
            assert request.start_month is not None
            assert request.end_year is not None
            assert request.end_month is not None
            date_range = google_request.historical_metrics_options.year_month_range
            date_range.start.year = request.start_year
            date_range.start.month = _month_value(request.start_month)
            date_range.end.year = request.end_year
            date_range.end.month = _month_value(request.end_month)
        response = _call_google(
            lambda: (
                self._services.keyword_plan_idea.generate_keyword_historical_metrics(
                    google_request
                )
            )
        )
        return tuple(
            AdapterKeywordRow(
                text=result.text,
                close_variants=tuple(result.close_variants),
                metrics=_historical_metrics(result.keyword_metrics),
            )
            for result in response.results
        )

    async def generate_keyword_ideas(
        self, request: AdapterGenerateKeywordIdeasRequest
    ) -> AdapterKeywordIdeaPage:
        google_request = GenerateKeywordIdeasRequest(
            customer_id=self._customer_id,
            language=request.language_resource_name,
            geo_target_constants=request.geo_target_resource_names,
            include_adult_keywords=request.include_adult_keywords,
            page_size=request.page_size,
            keyword_plan_network=request.network,
            keyword_seed={"keywords": request.seed_topics},
        )
        if request.page_token is not None:
            google_request.page_token = request.page_token
        pager = _call_google(
            lambda: self._services.keyword_plan_idea.generate_keyword_ideas(
                google_request
            )
        )
        try:
            response = next(pager.pages)
        except StopIteration as error:
            raise UpstreamGoogleAdsError(
                "Google Ads returned no Keyword Ideas response page."
            ) from error
        return AdapterKeywordIdeaPage(
            items=tuple(
                AdapterKeywordRow(
                    text=result.text,
                    close_variants=tuple(result.close_variants),
                    metrics=_historical_metrics(result.keyword_idea_metrics),
                )
                for result in response.results
            ),
            total_size=response.total_size,
            next_page_token=response.next_page_token or None,
        )


def _criterion_id(target: GeoTargetConstant) -> int:
    if "id" in target:
        return target.id
    return int(target.resource_name.rsplit("/", maxsplit=1)[-1])


def _escape_gaql_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _call_google(operation: Callable[[], _T]) -> _T:
    try:
        return operation()
    except GoogleAdsException as error:
        failure = cast(GoogleAdsFailure, error.failure)
        if any("quota_error" in item.error_code for item in failure.errors):
            raise AdapterRateLimitError(
                "Google Ads rate limits temporarily prevented the request."
            ) from error
        if any(
            "authentication_error" in item.error_code
            or "authorization_error" in item.error_code
            for item in failure.errors
        ):
            raise GoogleAdsAuthorizationError(
                "Google Ads authentication or authorization failed; check the "
                "configured credentials and customer access."
            ) from error
        if any(
            "policy_finding_error" in item.error_code
            or "policy_violation_error" in item.error_code
            or "operation_access_denied_error" in item.error_code
            or "resource_access_denied_error" in item.error_code
            or "not_allowlisted_error" in item.error_code
            for item in failure.errors
        ):
            raise GoogleAdsPolicyError(
                "Google Ads access level or policy does not permit this operation."
            ) from error
        raise UpstreamGoogleAdsError(
            "Google Ads could not complete the request."
        ) from error
    except ResourceExhausted as error:
        raise AdapterRateLimitError(
            "Google Ads rate limits temporarily prevented the request."
        ) from error
    except (DeadlineExceeded, ServiceUnavailable) as error:
        raise AdapterTransientError(
            "Google Ads is temporarily unavailable; retry the request."
        ) from error
    except GoogleAPICallError as error:
        raise UpstreamGoogleAdsError(
            "Google Ads could not complete the request."
        ) from error


_MONTH_NAMES = (
    "JANUARY",
    "FEBRUARY",
    "MARCH",
    "APRIL",
    "MAY",
    "JUNE",
    "JULY",
    "AUGUST",
    "SEPTEMBER",
    "OCTOBER",
    "NOVEMBER",
    "DECEMBER",
)
_MONTH_NUMBERS = {name: number for number, name in enumerate(_MONTH_NAMES, start=1)}
_MONTH_VALUES = (
    MonthOfYearEnum.MonthOfYear.JANUARY,
    MonthOfYearEnum.MonthOfYear.FEBRUARY,
    MonthOfYearEnum.MonthOfYear.MARCH,
    MonthOfYearEnum.MonthOfYear.APRIL,
    MonthOfYearEnum.MonthOfYear.MAY,
    MonthOfYearEnum.MonthOfYear.JUNE,
    MonthOfYearEnum.MonthOfYear.JULY,
    MonthOfYearEnum.MonthOfYear.AUGUST,
    MonthOfYearEnum.MonthOfYear.SEPTEMBER,
    MonthOfYearEnum.MonthOfYear.OCTOBER,
    MonthOfYearEnum.MonthOfYear.NOVEMBER,
    MonthOfYearEnum.MonthOfYear.DECEMBER,
)


def _month_value(month: int) -> MonthOfYearEnum.MonthOfYear:
    return _MONTH_VALUES[month - 1]


def _historical_metrics(
    metrics: KeywordPlanHistoricalMetrics,
) -> AdapterKeywordMetrics:
    return AdapterKeywordMetrics(
        average_monthly_searches=(
            metrics.avg_monthly_searches if "avg_monthly_searches" in metrics else None
        ),
        monthly_search_volumes=tuple(
            AdapterMonthlySearchVolume(
                year=volume.year,
                month=_MONTH_NUMBERS[volume.month.name],
                searches=(
                    volume.monthly_searches if "monthly_searches" in volume else None
                ),
            )
            for volume in metrics.monthly_search_volumes
        ),
        paid_competition=metrics.competition.name,
        paid_competition_index=(
            metrics.competition_index if "competition_index" in metrics else None
        ),
        average_cpc_micros=(
            metrics.average_cpc_micros if "average_cpc_micros" in metrics else None
        ),
        low_top_of_page_bid_micros=(
            metrics.low_top_of_page_bid_micros
            if "low_top_of_page_bid_micros" in metrics
            else None
        ),
        high_top_of_page_bid_micros=(
            metrics.high_top_of_page_bid_micros
            if "high_top_of_page_bid_micros" in metrics
            else None
        ),
    )


class GoogleAdsPort(Protocol):
    """Google Ads operations required by the research module."""

    async def suggest_geo_targets(
        self,
        query: str,
        *,
        country_code: str | None,
        locale: str | None,
    ) -> tuple[AdapterGeoTarget, ...]: ...

    async def resolve_language_code(
        self, language_code: str
    ) -> tuple[AdapterLanguageConstant, ...]: ...

    async def get_customer_currency_code(self) -> str: ...

    async def get_keyword_historical_metrics(
        self, request: AdapterHistoricalMetricsRequest
    ) -> tuple[AdapterKeywordRow, ...]: ...

    async def generate_keyword_ideas(
        self, request: AdapterGenerateKeywordIdeasRequest
    ) -> AdapterKeywordIdeaPage: ...
