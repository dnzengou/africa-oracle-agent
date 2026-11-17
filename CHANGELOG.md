# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

## [0.9.0] — 2026-11-17

### Added
- **Real MCP server at `POST /mcp`**: JSON-RPC 2.0 streamable-http. Implements `initialize`, `tools/list`, `tools/call`. Four tools: `convert_currency`, `get_rate`, `list_providers`, `robust_feed`. Claude Desktop and Cursor can now connect as native MCP clients.
- **`GET /history/{from}/{to}?since=N`**: in-memory time series from the aggregator ring buffer (last 60 min, 120 snapshots). Powers the dashboard sparklines.
- **`GET /snapshot/{oracle_id}`**: content-addressable frozen feed. AI agents can cite a specific moment and independent parties can verify a claim after the fact. ~2-hour retention.
- **`GET /changelog`**: HTML render of `CHANGELOG.md` with `Article` schema.org JSON-LD so version history is an indexable artifact for AI search.
- **Dashboard sparklines**: inline SVG per currency card, fed by `/history`, theme-aware stroke/fill, no deps.
- **p50/p95 latency on `/metrics`**: reservoir sampler (last 256 timings per aggregator op), Prometheus-formatted.

### Changed
- `_WIDGET_JS` string extracted to `api/static/widget.js` — served from disk with `Cache-Control: max-age=300`. Faster to iterate and CDN-friendly.
- FAQ content moved from Python literal to `api/static/faq.json`. Editors don't need to touch Python to update Q+A.

### Rationale
Round 4 turns the oracle into a **first-class MCP tool** (real JSON-RPC, not just a descriptor) and gives it **durable short-term memory** (history + snapshots) — two features AI agents and commercial integrators ask for first.

---

## [0.8.0] — 2026-11-14

### Added
- **USD as a synthetic base currency** in `convert_amount()`. The aggregator is USD-quoted by construction, so USD↔any works at rate 1.0 on the USD leg. Fixes the merchant/remittance examples in `INTEGRATE.md`.
- **`/robots.txt`**, **`/sitemap.xml`**, **`/feed.xml`** (RSS 2.0): classic + agentic SEO surfaces.
- **`/faq`** HTML page with 15 answers and embedded `FAQPage` schema.org JSON-LD.
- **`/.well-known/agents.json`**: agent-to-agent discovery manifest (A2A / AGNTCY lineage).
- **`/mcp.json`**: static MCP tool catalog (descriptor).
- Dashboard **persona onboarding chips**: Convert / Embed / Call from code / Use in AI agent / FAQ.
- **`ONBOARDING.md`**: persona-based 5-minutes-to-first-value guide.
- **`skills/agentic-seo.md`**: productized SEO pattern reusable across any project, lineage `evoforge > africa-oracle-devflow@0.5.0 > agentic-seo@0.1.0`, fitness `0.90`.

### Changed
- Dashboard JSON-LD `softwareVersion` is now templated server-side (`{{VERSION}}`) so it tracks the running build instead of drifting.

---

## [0.7.0] — 2026-11-08

### Added
- **GEO / AI discoverability**: `/llms.txt`, `/ai.txt`, `/.well-known/ai-plugin.json`, `/.well-known/security.txt`. Dashboard carries OpenGraph meta tags and `schema.org` JSON-LD so LLM search tools (ChatGPT Search, Claude Search, Perplexity, Gemini, Bing Copilot) can index and cite accurately.
- **`GET /rate/{from}/{to}`**: cite-friendly, cacheable simple-GET exchange rate — easier to link from docs, chatbots, and AI agents than the POST form.
- **`GET /widget.js`**: one-line embeddable live-rate widget for any HTML page. Data attributes `data-from`, `data-to`, `data-amount`, `data-theme`. The dashboard shows a live preview + copy-pasteable snippet.
- **Credibility files at repo root**: `FACTS.md` (every public claim mapped to code), `SECURITY.md` (RFC 9116 disclosure policy), `CITATION.cff` (citable metadata), `CONTRIBUTING.md`, `CHANGELOG.md`, `INTEGRATE.md` (end-user integration recipes), `EVOFORGE.md` (self-evolving oracle-skill rationale).

### Changed
- Rate-limit middleware exempts `/llms.txt`, `/ai.txt`, `/widget.js`, `/.well-known/*`, `/openapi.json`, `/docs`, `/redoc` so AI crawlers and docs can read freely.
- Dashboard gets an **Embed anywhere** section with a live widget preview.

### Rationale
Round 2 of the production-readiness pass. Round 1 (`0.6.0`) delivered the commercial UX (`/convert`, dashboard). Round 2 delivers the **distribution** layer: AI agents can now index the project accurately (GEO), fintech sites can drop in a rate widget in one line of JS, and the project is citable (`CITATION.cff`) and credibly documented (every claim maps to code).

---

## [0.6.0] — 2026-11-08

### Added
- **`POST /convert`**: cross-currency conversion (`{from, to, amount, side}`). Powers remittance, merchant pricing, and traveler flows. USD-triangulated, confidence-propagating.
- **Dashboard UI at `/`**: self-contained single-page dashboard. Live rate grid, currency converter with debounce + swap, quorum badges, dark-mode-aware theme toggle. 13 KB, no CDN.
- 10 s in-process TTL cache on `/feeds/*` → ~10× fewer aggregator rebuilds under load.
- CORS middleware → SDKs, extension, PWA can call from a browser.
- Per-IP token-bucket rate limit (60 req/min), exempts `/health`, `/metrics`, `/`.
- Non-root Docker user (uid 1001).
- New metrics: `convert_requests_total`, `cache_hits_total`, `cache_misses_total`, `rate_limited_total`.

### Changed
- Extracted `_collect_prices` / `_group_by_currency` / `_consensus_for_currency` on `OracleAggregator` — eliminated ~65 LOC of duplication between `aggregate()` and `robust_quorum_aggregate()`.

### Fixed
- `/convert` used `min_providers=2` which excluded single-provider currencies (e.g. NGN). Lowered to `min_providers=1` for the converter feed only; outlier filter still applied.

---

## [0.5.0] — pre-2026-11

- Tukey-fence outlier defense (Resilient pillar).

## [0.4.0] — pre-2026-11

- 5-channel SDK distribution: Python, TypeScript, MV3 extension, PWA, VSCode, POSIX installer.

## [0.3.2] — pre-2026-11

- FunC contract TIP-74 rewrite (compiles to BoC).

## [0.3.0] — pre-2026-11

- 5-pillar fine-tune: Resilient / Sovereign / Scalable / Affordable / Alternative.

## [0.2.0] — pre-2026-11

- Deploy scaffold + R²S² hardening.
