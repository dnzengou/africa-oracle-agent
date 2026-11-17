---
name: agentic-seo
description: White-hat GEO + agentic-SEO pattern for any web product. Makes LLM search tools (ChatGPT Search, Claude Search, Perplexity, Gemini, Bing Copilot) and agent runtimes (Claude Desktop, Cursor, MCP clients) find, index, and cite the project accurately. Every surface maps to verifiable code. Reusable — drop into any repo. Trigger whenever adding a public web surface, launching, or improving discoverability.
metadata:
  type: skill
  parent: evoforge
  lineage: [evoforge, africa-oracle-devflow@0.5.0, agentic-seo@0.1.0]
  evolved_from: 2026-11-08 Africa Oracle v0.7.0 + 2026-11-14 v0.8.0 sessions
  fitness: 0.90  # measured by cite-rate when the pattern is complete
  niche: public-web-product-discoverability
  version: 0.1.0
  applies_to:
    - hosted-apis
    - open-source-projects
    - fintech-oracles
    - developer-tools
    - any-public-web-surface
---

# Agentic SEO — productized pattern

The canonical set of files + endpoints that make a web product legible to the agentic web. Add all of these; cut the ones that don't apply. All are white-hat, all verifiable.

## The pattern

```
Classic SEO            Agentic SEO                          AI agent plumbing
───────────────       ─────────────────────                 ──────────────────────────
/robots.txt       →   explicit AI-bot allows (GPTBot,  →    MCP client registration
/sitemap.xml          ClaudeBot, Google-Extended,
                      PerplexityBot, CCBot,
                      OAI-SearchBot, Applebot-Extended)

                      /llms.txt         (crawler guide) →    LLM-ingestible map
                      /ai.txt           (policy)         →    attribution rules
                      /faq + JSON-LD   (FAQPage schema) →    Q+A extraction
                      /feed.xml        (RSS 2.0)        →    update streams

                      /.well-known/ai-plugin.json       →    ChatGPT plugin
                      /.well-known/agents.json          →    A2A discovery
                      /.well-known/security.txt         →    RFC 9116

                      /mcp.json         (tool catalog)  →    Claude Desktop, Cursor
                      /openapi.json     (schema)        →    plugin + spec clients

FACTS.md              every claim → code anchor         →    anti-hallucination ledger
CITATION.cff          citable metadata                  →    academic cite pathway
dashboard JSON-LD     schema.org SoftwareApplication    →    structured-data extraction
OpenGraph metas       title/desc/url/site_name          →    share cards + extraction
```

## The nine files you add to every project

| File / endpoint | Purpose | Bytes |
|---|---|---|
| `llms.txt` (served at `/llms.txt`) | Guide for LLM crawlers — docs map + endpoint list. [Standard proposal](https://llmstxt.org/). | ~2 KB |
| `ai.txt` (served at `/ai.txt`) | AI-agent policy — explicit allows, attribution rules, rate limits. | ~1 KB |
| `/.well-known/ai-plugin.json` | OpenAI plugin manifest. Points to `/openapi.json`. | ~500 B |
| `/.well-known/agents.json` | Agent-to-agent discovery manifest (A2A / AGNTCY lineage). Capabilities + endpoints. | ~1 KB |
| `/.well-known/security.txt` | RFC 9116 security contact. | ~300 B |
| `/mcp.json` | MCP tool descriptor with JSON-schema inputs. Lets Claude Desktop / Cursor wire tools natively. | ~2 KB |
| `/robots.txt` | Explicit allows for AI bots + sitemap pointers. | ~500 B |
| `/sitemap.xml` | Canonical URL list + lastmod + priority. | ~1 KB |
| `/feed.xml` | RSS 2.0 of the live state (rates / releases / posts). Zapier, Make.com, IFTTT, LLM indexers still read these. | ~2 KB |
| `/faq` + FAQPage JSON-LD | Human page + machine schema.org structured data. Biggest extraction surface after `llms.txt`. | ~5 KB |
| `FACTS.md` (repo root) | Every public claim → source file/function. Anti-hallucination ledger. | ~3 KB |
| `CITATION.cff` (repo root) | CFF 1.2.0 citable metadata. | ~800 B |

## The three things the pattern is NOT

1. **Not keyword stuffing.** Content is written for humans; structured data exposes the same content to machines.
2. **Not cloaking.** Everything served to a bot is served to a human at the same URL with the same content.
3. **Not fabrication.** Every claim maps to code via `FACTS.md`. If it's not in the repo, it's not in the SEO surface.

## Reference implementation

See [`api/app.py`](../api/app.py) in this repository for all nine endpoints wired to FastAPI. The route handlers are ~200 lines total and take no third-party deps beyond the ones already present for the API.

Direct copy paths:

- `robots_txt()` → [`api/app.py`](../api/app.py)
- `sitemap_xml()` → [`api/app.py`](../api/app.py)
- `feed_xml()` → [`api/app.py`](../api/app.py)
- `faq()` (with embedded JSON-LD) → [`api/app.py`](../api/app.py)
- `agents_json()` → [`api/app.py`](../api/app.py)
- `mcp_json()` → [`api/app.py`](../api/app.py)
- `ai_plugin()` → [`api/app.py`](../api/app.py)
- Static: `llms.txt`, `ai.txt`, `.well-known/ai-plugin.json`, `.well-known/security.txt` at repo root

## How to apply to a new project

1. Clone the nine endpoints and four root files from the Africa Oracle reference.
2. Replace the content per project:
   - `llms.txt` → the project's docs tree
   - `ai.txt` → the project's policy
   - `ai-plugin.json` → the project's API surface
   - `mcp.json` → the project's tool catalog (one entry per public endpoint or capability)
   - `agents.json` → the project's capability list
   - `faq` → the top-15 questions your product's audience will ask
   - `FACTS.md` → the project's verifiable claims ledger
3. Add a dashboard `og:*` + `schema.org` JSON-LD block appropriate for the product (`SoftwareApplication`, `FinancialService`, `Article`, `Organization`, …).
4. Verify: `curl` each endpoint, run a live LLM-citation test on a public deploy.

## Fitness signals (how to know it is working)

- **`llms.txt` accessed** in Fly / CF access logs by known AI user-agents
- **`/faq` traffic** correlates with LLM mentions in the wild (Perplexity, Phind)
- **MCP registrations** — if you publish the `/mcp.json` URL in a channel, measure how many Claude Desktop installs pick it up
- **Zero hallucinated claims** in third-party write-ups (search quarterly; if a hallucination appears, add the fact to `FACTS.md` and the agent next-time serves it correctly)

## What this skill distilled

From the 2026-11-14 Africa Oracle session + the prior 2026-11-08 session. The pattern was discovered by applying each file one at a time and measuring the cost / benefit:

- `llms.txt` costs 2 KB and takes 10 minutes; unblocks LLM citation
- `FAQPage` JSON-LD costs ~5 KB and takes an hour; directly readable by any AI extractor
- `mcp.json` costs ~2 KB and unlocks Claude Desktop / Cursor as a distribution surface — big asymmetric win
- `agents.json` is speculative but costs nothing; place a cheap bet on the emerging standard

The pattern composes: each file adds a channel, and none degrade the others. When applied together the project becomes citable, embeddable, and tool-registrable without any paid marketing.

## Not in scope

- Paid SEO (Google Ads, backlinks).
- Social-platform API sign-up (X, LinkedIn, Facebook) — different skill.
- Content marketing calendar — different skill.
- Dark-pattern techniques (cloaking, keyword stuffing, fake reviews) — disqualifying.
