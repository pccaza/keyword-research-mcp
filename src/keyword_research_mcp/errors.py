"""Stable errors exposed by the research interface."""


class KeywordResearchError(Exception):
    """Base class for correctable and upstream research failures."""


class InvalidResearchInput(KeywordResearchError):
    """The caller supplied an invalid research request."""


class InvalidTargeting(KeywordResearchError):
    """A geography or language target is invalid or ambiguous."""


class InvalidCursor(KeywordResearchError):
    """A continuation cursor is invalid or no longer available."""


class InvalidConfiguration(KeywordResearchError):
    """Required Google Ads configuration is missing or conflicting."""


class GoogleAdsAuthorizationError(KeywordResearchError):
    """Google Ads rejected authentication or authorization."""


class GoogleAdsPolicyError(KeywordResearchError):
    """Google Ads access level or policy prevents the operation."""


class RateLimitExhausted(KeywordResearchError):
    """A rate-limited request still failed after bounded retries."""


class UpstreamGoogleAdsError(KeywordResearchError):
    """Google Ads failed in a way the caller cannot directly correct."""
