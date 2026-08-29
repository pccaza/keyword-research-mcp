# Keyword Research MCP

Keyword Research MCP is a lightweight local MCP server that connects an agent to
real Google Ads keyword-planning data — search volume, monthly volumes, paid
competition, and bid ranges — normalized into stable, typed shapes. It fetches
and normalizes; it does not score, cluster, or label keywords.

## Tools

- `generate_keyword_ideas` — discover keywords. Seed with `seed_keywords` (up to
  20), a `seed_url` (one page), or a `seed_site` (a whole domain); `seed_site`
  cannot be combined with the others. Give a plain-text `location` (default
  `United States`) and `language_code` (default `en`), or explicit
  `geo_target_resource_names`. Ideas come back most-searched first; ideas below
  `min_avg_monthly_searches` (default `10`) are dropped before the page is
  built, so `total_size` stays Google's pre-filter estimate. Paginate with
  `cursor`.
- `resolve_geo_targets` — list every plausible Google Ads location for a
  human-readable query when you need to pin down an exact target.
- `get_keyword_historical_metrics` — enrich an existing keyword list with
  average monthly searches, monthly volumes, paid competition, and bid ranges.

Search volume is real Google demand data. Paid Competition in Google Ads
describes advertiser activity; this project does not present it as organic
ranking difficulty and calculates no composite keyword score. Phrase grouping
and intent classification are left to the calling agent.

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

## Agent skill

[`skills/keyword-research/SKILL.md`](skills/keyword-research/SKILL.md) is a
ready-to-use skill that drives these tools: it takes a niche to a shortlist of
keywords worth planning content around, with sensible defaults meant to be
refined per use case. Copy the `skills/keyword-research/` directory into your
agent's skills directory (for Claude Code, `.claude/skills/`).

## Development

Run the same quality gate used in CI:

```console
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv build
```

`pyright` is configured but not part of the gate: the `mcp` 2.x server SDK
registers tools through decorators that pyright's strict mode reports as unused,
so it produces false positives here.

## License

MIT
