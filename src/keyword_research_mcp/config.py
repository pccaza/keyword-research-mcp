"""Credential-safe configuration loading for one Google Ads customer."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from os import environ as process_environ
from pathlib import Path
from typing import cast

import yaml

from keyword_research_mcp.errors import InvalidConfiguration

_CONFIG_HELP = "README.md#google-ads-configuration"
_OAUTH_SETTINGS = (
    "GOOGLE_ADS_CLIENT_ID",
    "GOOGLE_ADS_CLIENT_SECRET",
    "GOOGLE_ADS_REFRESH_TOKEN",
)
_YAML_TO_ENV = {
    "developer_token": "GOOGLE_ADS_DEVELOPER_TOKEN",
    "customer_id": "GOOGLE_ADS_CUSTOMER_ID",
    "login_customer_id": "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
    "client_id": "GOOGLE_ADS_CLIENT_ID",
    "client_secret": "GOOGLE_ADS_CLIENT_SECRET",
    "refresh_token": "GOOGLE_ADS_REFRESH_TOKEN",
    "json_key_file_path": "GOOGLE_ADS_JSON_KEY_FILE_PATH",
    "impersonated_email": "GOOGLE_ADS_IMPERSONATED_EMAIL",
    "cache_capacity": "KEYWORD_RESEARCH_CACHE_CAPACITY",
    "log_level": "KEYWORD_RESEARCH_LOG_LEVEL",
}
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@dataclass(frozen=True, slots=True)
class UserOAuthConfig:
    """Google Ads user OAuth credentials."""

    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    refresh_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ServiceAccountConfig:
    """Google Ads service-account credentials."""

    json_key_file_path: str = field(repr=False)
    impersonated_email: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class GoogleAdsConfig:
    """Validated process configuration for one target customer."""

    developer_token: str = field(repr=False)
    customer_id: str = field(repr=False)
    authentication: UserOAuthConfig | ServiceAccountConfig
    login_customer_id: str | None = field(default=None, repr=False)
    cache_capacity: int = 128
    log_level: str = "INFO"


def load_config(
    *,
    environ: Mapping[str, str] | None = None,
    yaml_path: str | Path | None = None,
) -> GoogleAdsConfig:
    """Load Google Ads configuration from environment variables or YAML."""
    environment = process_environ if environ is None else environ
    configured_yaml_path = yaml_path or environment.get(
        "GOOGLE_ADS_CONFIGURATION_FILE_PATH"
    )
    values = (
        _load_yaml_values(Path(configured_yaml_path))
        if configured_yaml_path is not None
        else {}
    )
    values.update(environment)
    login_customer_id = values.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
    if "GOOGLE_ADS_JSON_KEY_FILE_PATH" in values and any(
        setting in values for setting in _OAUTH_SETTINGS
    ):
        raise InvalidConfiguration(
            f"Choose either user OAuth or service-account settings; see {_CONFIG_HELP}."
        )
    if "GOOGLE_ADS_JSON_KEY_FILE_PATH" in values:
        authentication: UserOAuthConfig | ServiceAccountConfig = ServiceAccountConfig(
            json_key_file_path=_required(values, "GOOGLE_ADS_JSON_KEY_FILE_PATH"),
            impersonated_email=values.get("GOOGLE_ADS_IMPERSONATED_EMAIL"),
        )
    else:
        authentication = UserOAuthConfig(
            client_id=_required(values, "GOOGLE_ADS_CLIENT_ID"),
            client_secret=_required(values, "GOOGLE_ADS_CLIENT_SECRET"),
            refresh_token=_required(values, "GOOGLE_ADS_REFRESH_TOKEN"),
        )
    return GoogleAdsConfig(
        developer_token=_required(values, "GOOGLE_ADS_DEVELOPER_TOKEN"),
        customer_id=_normalize_customer_id(
            _required(values, "GOOGLE_ADS_CUSTOMER_ID"),
            "GOOGLE_ADS_CUSTOMER_ID",
        ),
        login_customer_id=(
            _normalize_customer_id(login_customer_id, "GOOGLE_ADS_LOGIN_CUSTOMER_ID")
            if login_customer_id is not None
            else None
        ),
        authentication=authentication,
        cache_capacity=_cache_capacity(values),
        log_level=_log_level(values),
    )


def _normalize_customer_id(value: str, setting: str) -> str:
    normalized = value.replace("-", "").strip()
    if len(normalized) != 10 or not normalized.isdigit():
        raise InvalidConfiguration(
            f"{setting} must be a 10-digit customer ID; see {_CONFIG_HELP}."
        )
    return normalized


def _required(values: Mapping[str, str], setting: str) -> str:
    value = values.get(setting, "").strip()
    if not value:
        raise InvalidConfiguration(
            f"Missing required setting {setting}; see {_CONFIG_HELP}."
        )
    return value


def _cache_capacity(values: Mapping[str, str]) -> int:
    try:
        capacity = int(values.get("KEYWORD_RESEARCH_CACHE_CAPACITY", "128"))
    except ValueError as error:
        raise InvalidConfiguration(
            f"KEYWORD_RESEARCH_CACHE_CAPACITY must be a positive integer; "
            f"see {_CONFIG_HELP}."
        ) from error
    if capacity < 1:
        raise InvalidConfiguration(
            f"KEYWORD_RESEARCH_CACHE_CAPACITY must be a positive integer; "
            f"see {_CONFIG_HELP}."
        )
    return capacity


def _log_level(values: Mapping[str, str]) -> str:
    level = values.get("KEYWORD_RESEARCH_LOG_LEVEL", "INFO").strip().upper()
    if level not in _LOG_LEVELS:
        raise InvalidConfiguration(
            f"KEYWORD_RESEARCH_LOG_LEVEL must be one of "
            f"{', '.join(sorted(_LOG_LEVELS))}; see {_CONFIG_HELP}."
        )
    return level


def _load_yaml_values(path: Path) -> dict[str, str]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise InvalidConfiguration(
            f"Could not load Google Ads YAML configuration; see {_CONFIG_HELP}."
        ) from error
    if not isinstance(loaded, dict):
        raise InvalidConfiguration(
            f"Google Ads YAML must contain a mapping; see {_CONFIG_HELP}."
        )
    mapping = cast(dict[object, object], loaded)
    values: dict[str, str] = {}
    for yaml_name, environment_name in _YAML_TO_ENV.items():
        value = mapping.get(yaml_name)
        if value is not None:
            values[environment_name] = str(value)
    return values
