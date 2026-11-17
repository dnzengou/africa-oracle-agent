# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

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
