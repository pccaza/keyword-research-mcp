# Keyword Research MCP

Keyword Research MCP is a lightweight local MCP server for retrieving and
normalizing Google Ads keyword-planning evidence, built so that an agent can
explore a topic in a single call.

## Tools

- `explore_keywords` — the fast path. Give a `topic` (and optionally a
  plain-text `location`, default `United States`, and `language_code`, default
  `en`). Returns the most-searched keywords for the topic plus derived content
  angles: question phrases, comparison phrases, commercial-intent phrases,
  topical clusters, and seasonal demand peaks. Paginate with `cursor`.
- `resolve_geo_targets` — list every plausible Google Ads location for a
  human-readable query when you need to pin down an exact target.
- `generate_keyword_ideas` — a bounded page of Keyword Ideas for one or more
  seed topics; accepts a plain-text `location` or explicit
  `geo_target_resource_names`.
- `get_keyword_historical_metrics` — enrich an existing keyword list with
  average monthly searches, monthly volumes, paid competition, and bid ranges.

Paid Competition in Google Ads describes advertiser activity. This project does
not present it as organic ranking difficulty and does not calculate a composite
keyword score.

## Requirements

- Python 3.10 through 3.14
- [uv](https://docs.astral.sh/uv/)

Google Ads credentials are not needed for tests. They are required when the
production adapter connects to Google Ads.

## Google Ads configuration

The production adapter uses `google-ads==31.2.0` and explicitly selects Google
Ads API `v25`. Configure exactly one target customer and one authentication
method. Customer IDs may contain hyphens; they are normalized in memory.

For user OAuth, set:

```console
export GOOGLE_ADS_DEVELOPER_TOKEN="developer-token-placeholder"
export GOOGLE_ADS_CUSTOMER_ID="123-456-7890"
export GOOGLE_ADS_LOGIN_CUSTOMER_ID="987-654-3210" # optional manager account
export GOOGLE_ADS_CLIENT_ID="client-id-placeholder"
export GOOGLE_ADS_CLIENT_SECRET="client-secret-placeholder"
export GOOGLE_ADS_REFRESH_TOKEN="refresh-token-placeholder"
```

For a service account, omit the three user-OAuth settings and set:

```console
export GOOGLE_ADS_DEVELOPER_TOKEN="developer-token-placeholder"
export GOOGLE_ADS_CUSTOMER_ID="123-456-7890"
export GOOGLE_ADS_JSON_KEY_FILE_PATH="/path/to/service-account.json"
export GOOGLE_ADS_IMPERSONATED_EMAIL="ads-user@example.test" # optional
```

Alternatively, point `GOOGLE_ADS_CONFIGURATION_FILE_PATH` at a local
`google-ads.yaml`:

```yaml
developer_token: developer-token-placeholder
customer_id: "123-456-7890"
login_customer_id: "987-654-3210"
client_id: client-id-placeholder
client_secret: client-secret-placeholder
refresh_token: refresh-token-placeholder
```

Optional process settings are `KEYWORD_RESEARCH_CACHE_CAPACITY` (default `128`)
and `KEYWORD_RESEARCH_LOG_LEVEL` (default `INFO`). Credential files,
`google-ads.yaml`, and `.env` files are ignored by Git.

## Set up and run

```console
uv sync
uv run keyword-research-mcp
```

The command runs over `stdio`, so it waits silently for an MCP client and writes
protocol messages only to standard output.

## Development

Run the same quality gate used in CI:

```console
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv build
```

See [the implementation plan](docs/implementation-plan.md) for the intended tool
contracts, architecture, delivery phases, and product boundaries.

## License

MIT
