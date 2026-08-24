"""Validated public request and normalized response models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ResearchModel(BaseModel):
    """Shared behavior for immutable, strict research contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class GenerateKeywordIdeasInput(ResearchModel):
    """Validated input for Keyword Idea discovery."""

    seed_topics: tuple[NonBlankString, ...] = Field(min_length=1)
    geo_target_resource_names: tuple[NonBlankString, ...] = Field(min_length=1)
    language_code: NonBlankString
    page_size: int = Field(default=100, ge=1, le=1_000)
    cursor: NonBlankString | None = None
    refresh: bool = False


class HistoricalMetricsInput(ResearchModel):
    """Validated input for enriching an existing keyword list."""

    keywords: tuple[NonBlankString, ...] = Field(min_length=1, max_length=1_000)
    geo_target_resource_names: tuple[NonBlankString, ...] = Field(min_length=1)
    language_code: NonBlankString
    start_year: int | None = None
    start_month: int | None = Field(default=None, ge=1, le=12)
    end_year: int | None = None
    end_month: int | None = Field(default=None, ge=1, le=12)
    refresh: bool = False

    @model_validator(mode="after")
    def validate_historical_period(self) -> HistoricalMetricsInput:
        period_parts = (
            self.start_year,
            self.start_month,
            self.end_year,
            self.end_month,
        )
        if any(part is not None for part in period_parts) and any(
            part is None for part in period_parts
        ):
            raise ValueError(
                "historical period requires start_year, start_month, end_year, "
                "and end_month"
            )
        if all(part is not None for part in period_parts):
            assert self.start_year is not None
            assert self.start_month is not None
            assert self.end_year is not None
            assert self.end_month is not None
            if (self.end_year, self.end_month) < (
                self.start_year,
                self.start_month,
            ):
                raise ValueError("historical period must end on or after it starts")
        return self


class GeoTargetParent(ResearchModel):
    """A parent location attached to a geography match."""

    resource_name: str
    criterion_id: int
    canonical_name: str


class GeoTargetMatch(ResearchModel):
    """One plausible Google Ads geography target."""

    resource_name: str
    criterion_id: int
    canonical_name: str
    country_code: str
    target_type: str
    status: str
    parents: tuple[GeoTargetParent, ...] = ()


class GeoResolutionContext(ResearchModel):
    """Restrictions used for a human-readable geography lookup."""

    country_code: str | None
    locale: str | None


class GeoTargetMatches(ResearchModel):
    """All plausible matches for a human-readable geography query."""

    query: str
    matches: tuple[GeoTargetMatch, ...]
    research_context: GeoResolutionContext
    retrieved_at: datetime


class Money(ResearchModel):
    """An exact monetary value derived from Google Ads micros."""

    micros: int
    amount: Decimal
    currency_code: str


class MonthlySearchVolume(ResearchModel):
    """Search volume for one calendar month."""

    year: int
    month: int = Field(ge=1, le=12)
    searches: int | None


PaidCompetition = Literal["LOW", "MEDIUM", "HIGH"]


class KeywordMetrics(ResearchModel):
    """Normalized Historical Metrics without organic-ranking claims."""

    average_monthly_searches: int | None
    monthly_search_volumes: tuple[MonthlySearchVolume, ...]
    paid_competition: PaidCompetition | None
    paid_competition_index: int | None
    average_cpc: Money | None
    low_top_of_page_bid: Money | None
    high_top_of_page_bid: Money | None


class KeywordRow(ResearchModel):
    """A canonical Google keyword and its distinct close variants."""

    text: str
    close_variants: tuple[str, ...]
    metrics: KeywordMetrics


class ExplicitHistoricalPeriod(ResearchModel):
    """An inclusive caller-supplied historical period."""

    kind: Literal["EXPLICIT"] = "EXPLICIT"
    start_year: int
    start_month: int = Field(ge=1, le=12)
    end_year: int
    end_month: int = Field(ge=1, le=12)


class DefaultHistoricalPeriod(ResearchModel):
    """Google's default past-twelve-month historical period."""

    kind: Literal["GOOGLE_DEFAULT_PAST_12_MONTHS"] = "GOOGLE_DEFAULT_PAST_12_MONTHS"


class ResearchContext(ResearchModel):
    """Market and time assumptions attached to returned evidence."""

    geo_target_resource_names: tuple[str, ...]
    language_code: str
    network: Literal["GOOGLE_SEARCH"] = "GOOGLE_SEARCH"
    historical_period: ExplicitHistoricalPeriod | DefaultHistoricalPeriod


class HistoricalMetricsResult(ResearchModel):
    """Normalized evidence for an existing keyword list."""

    items: tuple[KeywordRow, ...]
    research_context: ResearchContext
    retrieved_at: datetime


class KeywordIdeaPage(ResearchModel):
    """One honest, bounded page of normalized Keyword Ideas."""

    items: tuple[KeywordRow, ...]
    returned_count: int
    total_size: int | None
    has_more: bool
    next_cursor: str | None
    research_context: ResearchContext
    retrieved_at: datetime
