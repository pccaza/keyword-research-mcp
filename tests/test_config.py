from pathlib import Path

import pytest

from keyword_research_mcp.config import (
    ServiceAccountConfig,
    UserOAuthConfig,
    load_config,
)
from keyword_research_mcp.errors import InvalidConfiguration


def test_environment_configuration_loads_user_oauth() -> None:
    config = load_config(
        environ={
            "GOOGLE_ADS_DEVELOPER_TOKEN": "developer-token-placeholder",
            "GOOGLE_ADS_CUSTOMER_ID": "123-456-7890",
            "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "987-654-3210",
            "GOOGLE_ADS_CLIENT_ID": "client-id-placeholder",
            "GOOGLE_ADS_CLIENT_SECRET": "client-secret-placeholder",
            "GOOGLE_ADS_REFRESH_TOKEN": "refresh-token-placeholder",
        }
    )

    assert config.customer_id == "1234567890"
    assert config.login_customer_id == "9876543210"
    assert config.cache_capacity == 128
    assert config.log_level == "INFO"
    assert isinstance(config.authentication, UserOAuthConfig)
    assert config.authentication.client_id == "client-id-placeholder"


def test_environment_configuration_loads_service_account() -> None:
    config = load_config(
        environ={
            "GOOGLE_ADS_DEVELOPER_TOKEN": "developer-token-placeholder",
            "GOOGLE_ADS_CUSTOMER_ID": "1234567890",
            "GOOGLE_ADS_JSON_KEY_FILE_PATH": "/credentials/service-account.json",
            "GOOGLE_ADS_IMPERSONATED_EMAIL": "ads-user@example.test",
        }
    )

    assert isinstance(config.authentication, ServiceAccountConfig)
    assert config.authentication.json_key_file_path == (
        "/credentials/service-account.json"
    )
    assert config.authentication.impersonated_email == "ads-user@example.test"


def test_missing_configuration_names_setting_and_readme_section() -> None:
    with pytest.raises(
        InvalidConfiguration,
        match=r"GOOGLE_ADS_DEVELOPER_TOKEN.*README.md#google-ads-configuration",
    ):
        load_config(
            environ={
                "GOOGLE_ADS_CUSTOMER_ID": "1234567890",
                "GOOGLE_ADS_CLIENT_ID": "client-id-placeholder",
                "GOOGLE_ADS_CLIENT_SECRET": "client-secret-placeholder",
                "GOOGLE_ADS_REFRESH_TOKEN": "refresh-token-placeholder",
            }
        )


def test_configuration_rejects_conflicting_authentication_shapes() -> None:
    with pytest.raises(InvalidConfiguration, match="Choose either user OAuth or"):
        load_config(
            environ={
                "GOOGLE_ADS_DEVELOPER_TOKEN": "developer-token-placeholder",
                "GOOGLE_ADS_CUSTOMER_ID": "1234567890",
                "GOOGLE_ADS_CLIENT_ID": "client-id-placeholder",
                "GOOGLE_ADS_CLIENT_SECRET": "client-secret-placeholder",
                "GOOGLE_ADS_REFRESH_TOKEN": "refresh-token-placeholder",
                "GOOGLE_ADS_JSON_KEY_FILE_PATH": ("/credentials/service-account.json"),
            }
        )


def test_google_ads_yaml_configuration_loads(tmp_path: Path) -> None:
    yaml_path = tmp_path / "google-ads.yaml"
    yaml_path.write_text(
        "\n".join(
            (
                "developer_token: developer-token-placeholder",
                "customer_id: '123-456-7890'",
                "client_id: client-id-placeholder",
                "client_secret: client-secret-placeholder",
                "refresh_token: refresh-token-placeholder",
                "login_customer_id: '987-654-3210'",
            )
        ),
        encoding="utf-8",
    )

    config = load_config(yaml_path=yaml_path, environ={})

    assert config.customer_id == "1234567890"
    assert config.login_customer_id == "9876543210"
    assert isinstance(config.authentication, UserOAuthConfig)


def test_configuration_representation_redacts_credentials_and_customer_ids() -> None:
    config = load_config(
        environ={
            "GOOGLE_ADS_DEVELOPER_TOKEN": "sensitive-developer-token",
            "GOOGLE_ADS_CUSTOMER_ID": "1234567890",
            "GOOGLE_ADS_CLIENT_ID": "sensitive-client-id",
            "GOOGLE_ADS_CLIENT_SECRET": "sensitive-client-secret",
            "GOOGLE_ADS_REFRESH_TOKEN": "sensitive-refresh-token",
        }
    )

    rendered = repr(config)

    assert "sensitive" not in rendered
    assert "1234567890" not in rendered


def test_configuration_rejects_invalid_customer_id_without_echoing_it() -> None:
    with pytest.raises(InvalidConfiguration) as captured:
        load_config(
            environ={
                "GOOGLE_ADS_DEVELOPER_TOKEN": "developer-token-placeholder",
                "GOOGLE_ADS_CUSTOMER_ID": "not-a-customer-id",
                "GOOGLE_ADS_CLIENT_ID": "client-id-placeholder",
                "GOOGLE_ADS_CLIENT_SECRET": "client-secret-placeholder",
                "GOOGLE_ADS_REFRESH_TOKEN": "refresh-token-placeholder",
            }
        )

    assert "GOOGLE_ADS_CUSTOMER_ID" in str(captured.value)
    assert "not-a-customer-id" not in str(captured.value)


def test_configuration_rejects_nonpositive_cache_capacity() -> None:
    with pytest.raises(InvalidConfiguration, match="CACHE_CAPACITY"):
        load_config(
            environ={
                "GOOGLE_ADS_DEVELOPER_TOKEN": "developer-token-placeholder",
                "GOOGLE_ADS_CUSTOMER_ID": "1234567890",
                "GOOGLE_ADS_CLIENT_ID": "client-id-placeholder",
                "GOOGLE_ADS_CLIENT_SECRET": "client-secret-placeholder",
                "GOOGLE_ADS_REFRESH_TOKEN": "refresh-token-placeholder",
                "KEYWORD_RESEARCH_CACHE_CAPACITY": "0",
            }
        )


def test_configuration_rejects_unknown_log_level() -> None:
    with pytest.raises(InvalidConfiguration, match="LOG_LEVEL"):
        load_config(
            environ={
                "GOOGLE_ADS_DEVELOPER_TOKEN": "developer-token-placeholder",
                "GOOGLE_ADS_CUSTOMER_ID": "1234567890",
                "GOOGLE_ADS_CLIENT_ID": "client-id-placeholder",
                "GOOGLE_ADS_CLIENT_SECRET": "client-secret-placeholder",
                "GOOGLE_ADS_REFRESH_TOKEN": "refresh-token-placeholder",
                "KEYWORD_RESEARCH_LOG_LEVEL": "verbose",
            }
        )
