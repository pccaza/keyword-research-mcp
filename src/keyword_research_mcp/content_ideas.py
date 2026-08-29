"""Derive content angles from normalized keyword evidence.

Every function here is pure: it reads a sequence of already-normalized
``KeywordRow`` values and never calls Google Ads. The goal is to turn a flat
keyword list into the groupings an agent needs to plan content -- question
phrases, comparison phrases, commercial-intent phrases, topical clusters, and
seasonal peaks -- without inventing an organic-difficulty score.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from statistics import median

from keyword_research_mcp.models import (
    ContentIdeas,
    KeywordCluster,
    KeywordRow,
    SeasonalPeak,
)

_QUESTION_PREFIXES = (
    "how",
    "what",
    "why",
    "when",
    "where",
    "which",
    "who",
    "can",
    "does",
    "do",
    "is",
    "are",
    "will",
    "should",
)
_COMPARISON_MARKERS = (" vs ", " vs. ", " versus ", " or ")
_COMMERCIAL_MARKERS = (
    "best",
    "top",
    "cheap",
    "cheapest",
    "affordable",
    "price",
    "pricing",
    "cost",
    "buy",
    "deal",
    "deals",
    "discount",
    "review",
    "reviews",
    "near me",
    "alternative",
    "alternatives",
)
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "the",
        "for",
        "to",
        "of",
        "in",
        "on",
        "with",
        "without",
        "your",
        "you",
        "my",
        "me",
        "is",
        "are",
        "be",
        "how",
        "what",
        "why",
        "vs",
        "or",
        "best",
        "top",
        "near",
        "at",
        "by",
        "from",
        "it",
        "this",
        "that",
    }
)
_MIN_CLUSTER_SIZE = 2
_MAX_CLUSTER_KEYWORDS = 25
_SEASONAL_PEAK_RATIO = 1.5


def _searches(row: KeywordRow) -> int:
    return row.metrics.average_monthly_searches or 0


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in "".join(
            char if char.isalnum() or char.isspace() else " " for char in text.lower()
        ).split()
        if token not in _STOP_WORDS and len(token) > 2
    ]


def question_keywords(rows: Iterable[KeywordRow]) -> tuple[str, ...]:
    """Keywords phrased as a natural-language question."""
    found: list[str] = []
    for row in rows:
        first, _, _ = row.text.strip().lower().partition(" ")
        if first in _QUESTION_PREFIXES or row.text.rstrip().endswith("?"):
            found.append(row.text)
    return tuple(found)


def comparison_keywords(rows: Iterable[KeywordRow]) -> tuple[str, ...]:
    """Keywords that pit one option against another."""
    return tuple(
        row.text
        for row in rows
        if any(marker in f" {row.text.lower()} " for marker in _COMPARISON_MARKERS)
    )


def commercial_keywords(rows: Iterable[KeywordRow]) -> tuple[str, ...]:
    """Keywords that signal buying or vendor-evaluation intent."""
    return tuple(
        row.text
        for row in rows
        if any(marker in row.text.lower() for marker in _COMMERCIAL_MARKERS)
    )


def cluster_by_theme(rows: Sequence[KeywordRow]) -> tuple[KeywordCluster, ...]:
    """Group keywords by their most distinctive shared word.

    Each keyword is assigned to the single token it shares with the most other
    keywords (ties broken by the longer, more specific token). Singleton groups
    are dropped. Clusters are returned most-searched first.
    """
    document_frequency: Counter[str] = Counter()
    for row in rows:
        document_frequency.update(set(_tokens(row.text)))

    buckets: dict[str, list[KeywordRow]] = {}
    for row in rows:
        candidates = sorted(
            set(_tokens(row.text)),
            key=lambda token: (document_frequency[token], len(token)),
            reverse=True,
        )
        if not candidates or document_frequency[candidates[0]] < _MIN_CLUSTER_SIZE:
            continue
        buckets.setdefault(candidates[0], []).append(row)

    clusters = [
        KeywordCluster(
            theme=theme,
            total_monthly_searches=sum(_searches(row) for row in members),
            keywords=tuple(
                row.text
                for row in sorted(members, key=_searches, reverse=True)[
                    :_MAX_CLUSTER_KEYWORDS
                ]
            ),
        )
        for theme, members in buckets.items()
        if len(members) >= _MIN_CLUSTER_SIZE
    ]
    return tuple(
        sorted(
            clusters, key=lambda cluster: cluster.total_monthly_searches, reverse=True
        )
    )


def seasonal_peaks(rows: Iterable[KeywordRow]) -> tuple[SeasonalPeak, ...]:
    """Keywords whose best month runs well above their typical month."""
    peaks: list[SeasonalPeak] = []
    for row in rows:
        volumes = [
            volume for volume in row.metrics.monthly_search_volumes if volume.searches
        ]
        if len(volumes) < 6:
            continue
        counts = [volume.searches or 0 for volume in volumes]
        typical = median(counts)
        if typical <= 0:
            continue
        peak = max(counts)
        ratio = peak / typical
        if ratio < _SEASONAL_PEAK_RATIO:
            continue
        peaks.append(
            SeasonalPeak(
                keyword=row.text,
                peak_months=tuple(
                    volume.month for volume in volumes if (volume.searches or 0) == peak
                ),
                peak_ratio=round(ratio, 2),
            )
        )
    return tuple(sorted(peaks, key=lambda item: item.peak_ratio, reverse=True))


def build_content_ideas(rows: Sequence[KeywordRow]) -> ContentIdeas:
    """Bundle every content angle derivable from a keyword list."""
    return ContentIdeas(
        questions=question_keywords(rows),
        comparisons=comparison_keywords(rows),
        commercial=commercial_keywords(rows),
        clusters=cluster_by_theme(rows),
        seasonal_peaks=seasonal_peaks(rows),
    )
