---
name: keyword-research
description: Turn a niche into a shortlist of keywords worth planning content around, using the keyword-research MCP server for real Google Ads search data. Use when the user wants keywords to grow organic search traffic, a keyword plan for a site or topic, content ideas backed by search demand, or search-volume data for a list of terms.
user-invocable: true
---

# Keyword Research

Turn a niche into a shortlist of keywords worth building content around, backed
by real Google Ads search-volume data.

**Prerequisite:** the `keyword-research` MCP server must be connected. It exposes
three tools:

- `generate_keyword_ideas` — discover keywords. Seed with `seed_keywords` (up to
  20), `seed_url` (one page), or `seed_site` (a whole domain). Plain-text
  `location` (default `United States`) and `language_code` (default `en`).
  Returns rows sorted by average monthly searches, descending; rows below
  `min_avg_monthly_searches` (default `10`) are dropped. Paginate with `cursor`.
- `resolve_geo_targets` — list exact Google Ads locations for a place name. Only
  needed when a plain-text `location` is ambiguous and the tool says so.
- `get_keyword_historical_metrics` — fetch metrics for a keyword list you
  already have (brainstormed, from a competitor, from the user).

The server only fetches and normalizes data. Grouping keywords, judging ranking
feasibility, and planning content are your job — this skill covers how.

## Default workflow

1. **Frame the niche.** Establish three things, asking only if genuinely
   unclear: the topic/niche, the target website or page (if any), and the
   target market (country). A site or page URL is a strong seed — use it.

2. **Discover.** Call `generate_keyword_ideas` once:
   - If you have a target site: `seed_site` = the domain (or `seed_url` = a
     specific page you're planning content for).
   - Otherwise: `seed_keywords` = 3–8 tightly on-topic core terms for the niche.
     Off-topic seeds pollute every downstream result.
   - `location` = the target country in plain text; keep `min_avg_monthly_searches`
     and `page_size` at their defaults.

3. **Expand once.** Take the 5–10 most relevant results and run
   `generate_keyword_ideas` again with them as `seed_keywords`. This surfaces
   the long-tail around the terms that matter. Paginate the first call with
   `cursor` only if you still need a bigger pool.

4. **Read the data.** For each keyword you keep:
   - `average_monthly_searches` — demand. The headline number.
   - `monthly_search_volumes` — the trend. Compare the last 3 months to the
     prior 9: rising, flat, declining, or spiky (seasonal).
   - `paid_competition` / `paid_competition_index` — how hard advertisers
     compete. A rough proxy for commercial value. **Not** organic ranking
     difficulty.
   - `low_top_of_page_bid` / `high_top_of_page_bid` — what advertisers pay.
     Higher bids mean higher commercial intent.

5. **Shortlist.** Default heuristic for growing organic traffic:
   - **Relevance first.** Drop anything not genuinely about the niche, whatever
     its volume.
   - **Weight toward long-tail.** Specific 3+ word phrases with clear intent are
     where a new or small site actually ranks. Keep a few higher-volume head
     terms for structure, but the bulk of the list should be long-tail.
   - **Label intent yourself:** informational (`how to`, `what is`, `ideas`,
     `guide`, `examples`), commercial (`best`, `vs`, `review`, `for beginners`),
     transactional (`buy`, `price`, `near me`, `cost`). Organic content
     strategies usually live in informational + commercial.
   - **Prioritise rising and steady demand** over declining. Flag strongly
     seasonal terms with their peak months so content ships ahead of the peak.
   - **Judge feasibility yourself** — the data has no organic-difficulty score.
     New or low-authority site: lean hard on long-tail, lower-volume terms.
     Established site: head terms are in reach. If you have web-search or SERP
     tools, spot-check what currently ranks for your top few candidates.

6. **Deliver.** Produce a keyword table — keyword, avg monthly searches, trend,
   intent, paid competition, top-of-page bid — grouped by intent or topic. If
   the user wants a content plan, cluster the keywords into pieces: one primary
   keyword plus 3–8 supporting keywords per article. Then hand off to whatever
   comes next (outline, draft, write to a file) — that's outside this skill.

## Good defaults

| Setting | Default | Change it when |
| --- | --- | --- |
| `location` | user's target market, else `United States` | always set it to the real market |
| `language_code` | `en` | market's primary language differs |
| `min_avg_monthly_searches` | `10` | raise to `50`–`100` for broad/competitive niches; set `0` only when deliberately mining ultra-long-tail for a brand-new site |
| `page_size` | `100` | fine as-is; use `cursor` for a deeper pool |
| seeds | 3–8 keyword seeds, or the site URL | keep them tightly on-topic |

## Refining for specific cases

These defaults target the general goal of growing organic traffic to a content
site. Adjust:

- **Local business:** set `location` to the city; keep transactional and
  `near me` terms; head terms are more reachable locally.
- **Ecommerce / affiliate:** weight toward commercial and transactional intent;
  watch `high_top_of_page_bid` as a value signal; category + modifier phrases
  (`<product> for <use case>`) are the sweet spot.
- **YMYL or competitive niche** (finance, health, law): raise
  `min_avg_monthly_searches`, lean almost entirely on specific long-tail, and
  spot-check SERPs before committing.
- **Non-US / non-English:** set both `location` and `language_code`.
- **Established, high-authority site:** allow more head terms into the shortlist.
- **Planning one specific article:** seed with that page's `seed_url` and skip
  the expansion step.
