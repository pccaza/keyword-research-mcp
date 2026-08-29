from keyword_research_mcp.content_ideas import build_content_ideas
from keyword_research_mcp.models import (
    KeywordMetrics,
    KeywordRow,
    MonthlySearchVolume,
)


def _row(text: str, searches: int, *, monthly: tuple[int, ...] = ()) -> KeywordRow:
    return KeywordRow(
        text=text,
        close_variants=(),
        metrics=KeywordMetrics(
            average_monthly_searches=searches,
            monthly_search_volumes=tuple(
                MonthlySearchVolume(year=2026, month=index + 1, searches=value)
                for index, value in enumerate(monthly)
            ),
            paid_competition=None,
            paid_competition_index=None,
            average_cpc=None,
            low_top_of_page_bid=None,
            high_top_of_page_bid=None,
        ),
    )


def test_build_content_ideas_sorts_angles_and_clusters_by_demand() -> None:
    rows = (
        _row("how to run a marathon", 500),
        _row("best running shoes for marathon", 3000),
        _row("marathon training plan", 2000),
        _row("nike vs adidas running shoes", 800),
        _row("running shoes review", 1500),
    )

    ideas = build_content_ideas(rows)

    assert ideas.questions == ("how to run a marathon",)
    assert ideas.comparisons == ("nike vs adidas running shoes",)
    assert "best running shoes for marathon" in ideas.commercial
    themes = [cluster.theme for cluster in ideas.clusters]
    assert "running" in themes or "shoes" in themes or "marathon" in themes
    assert ideas.clusters == tuple(
        sorted(
            ideas.clusters,
            key=lambda cluster: cluster.total_monthly_searches,
            reverse=True,
        )
    )


def test_seasonal_peaks_flag_keywords_with_a_dominant_month() -> None:
    steady = _row("keyword research", 1000, monthly=(100,) * 12)
    spiky = _row("christmas gift ideas", 1000, monthly=(10,) * 11 + (500,))

    ideas = build_content_ideas((steady, spiky))

    assert [peak.keyword for peak in ideas.seasonal_peaks] == ["christmas gift ideas"]
    assert ideas.seasonal_peaks[0].peak_months == (12,)
