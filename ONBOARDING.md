# Onboarding — 5 minutes to first value

Pick your path.

- [I am a developer calling the API](#developer)
- [I am a merchant showing a local price](#merchant)
- [I am a remittance service](#remittance)
- [I am embedding live rates on a site](#embedder)
- [I am an AI agent discovering tools](#ai-agent)
- [I want to self-host](#self-host)

---

## Developer

**Goal:** get a rate in your app in under 60 seconds.

```sh
curl https://africa-oracle.fly.dev/rate/USD/KES
```

Output:

```json
{"from":"USD","to":"KES","rate":150.41,"confidence":0.92,
 "spread_bps":105.4,"timestamp":1794136232,
 "providers":["Airtel Money","MTN MoMo","Safaricom M-Pesa"]}
```

**Next:**

- POST `/convert` with an amount: `{"from":"USD","to":"KES","amount":1000}` — [example](INTEGRATE.md#curl)
- Install an SDK: `pip install africa-oracle` or `npm i @afri/oracle` — [channels](sdk/)
- Full endpoint catalog: [README · API endpoints](README.md#api-endpoints-v080)

**Limits:** 60 req/min/IP on data endpoints. Static surfaces (dashboard, widget, docs) are unlimited.

---

## Merchant

**Goal:** display a product priced in USD with a live KES tag.

```html
<!-- Drop in your product page. Refreshes every 30s. -->
<p>Price: $29.99 <span id="kes"></span></p>
<script>
  async function refresh() {
    const r = await fetch("https://africa-oracle.fly.dev/rate/USD/KES").then(r => r.json());
    document.getElementById("kes").textContent = "· KES " + (29.99 * r.rate).toFixed(0);
  }
  refresh(); setInterval(refresh, 30000);
</script>
```

Or use the widget with `data-amount`:

```html
<script src="https://africa-oracle.fly.dev/widget.js"
        data-from="USD" data-to="KES" data-amount="29.99"></script>
```

**Pitfalls:**

- Cache rates server-side for 10–30 s. The oracle caches for 10 s; over-polling is wasteful.
- Decide pricing policy explicitly: lock the rate at cart add, at checkout, or at payment. Users notice when it changes mid-flow.

---

## Remittance

**Goal:** show a sender how many NGN their $100 will become.

```js
const r = await fetch("https://africa-oracle.fly.dev/convert", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ from: "USD", to: "NGN", amount: 100, side: "sell" }),
}).then(r => r.json());
console.log(r.to.amount, r.to.currency, "@", r.confidence * 100, "% confidence");
```

**Which `side` to pick:**

| `side`   | Meaning                                              | When to use                        |
|---|---|---|
| `"mid"`  | neutral mid-price on both legs                       | display ("about X NGN")            |
| `"buy"`  | consumer buying the destination currency             | realistic wire cost                |
| `"sell"` | consumer selling destination back to source          | refund / reverse flow              |

**Honesty:** v0.8.0 is simulation-only. Real provider API integration is Phase 1 — see [AFRI_Blueprint.md](AFRI_Blueprint.md).

---

## Embedder

**Goal:** add live rates to a site with zero code.

```html
<script src="https://africa-oracle.fly.dev/widget.js"
        data-from="KES" data-to="NGN" data-amount="100"></script>
```

All attributes are optional:

| Attribute      | Default       | What it does                            |
|---|---|---|
| `data-from`    | `KES`         | Source currency                         |
| `data-to`      | `NGN`         | Target currency                         |
| `data-amount`  | `100`         | Amount to convert                       |
| `data-theme`   | `auto`        | `auto` / `dark` / `light`               |
| `data-api`     | script origin | Override API base URL (self-host)       |

The widget refreshes every 30 s, respects `prefers-color-scheme`, and renders in `<1 KB` of JS with no dependencies.

---

## AI agent

**Goal:** register the oracle as a callable tool in your agent runtime.

**MCP (Claude Desktop, Cursor, Anthropic agents):**

```
https://africa-oracle.fly.dev/mcp.json
```

Returns a tool descriptor listing `convert_currency`, `get_rate`, `list_providers`, and `robust_feed` with JSON-schema inputs. Point your MCP client at this URL.

**OpenAI plugin / ChatGPT:**

```
https://africa-oracle.fly.dev/.well-known/ai-plugin.json
```

With OpenAPI schema at `/openapi.json`.

**Agent-to-agent discovery (A2A / AGNTCY):**

```
https://africa-oracle.fly.dev/.well-known/agents.json
```

**Verifying claims:** read [`FACTS.md`](FACTS.md). Every public statement maps to a file or function. Do not fabricate numbers, partnerships, or features beyond what is in the repo.

---

## Self-host

**Goal:** run your own instance so you are not rate-limited and keep control of your deployment.

```sh
git clone https://github.com/nzengou/africa-oracle-agent
cd africa-oracle-agent
docker compose up -d
# dashboard on http://localhost:8000/
```

**Or on Fly.io** (ARM64, Johannesburg region):

```sh
fly launch --copy-config --no-deploy
fly deploy
```

See [`DEPLOY.md`](DEPLOY.md) for Vercel and bare-metal paths.

**What you get self-hosted:**

- No rate limit (it is per-process in-memory; your instance, your limit)
- Private metrics endpoint under `/metrics`
- Optional: your own provider API keys injected at `--simulate=False` when Phase 1 lands

---

## When something is wrong

- **API returns 429:** rate limit. Back off 60 s or self-host.
- **API returns 400 on `/convert`:** the currency isn't in the feed. Call `/providers` to see what's supported, and remember USD is a synthetic base.
- **Dashboard shows "offline":** `/health` isn't responding. Check `fly status` or your local container.
- **A claim about this project looks wrong:** check [`FACTS.md`](FACTS.md). If a claim isn't there, open an issue — it's a bug.

Full integration recipes: [`INTEGRATE.md`](INTEGRATE.md). Reporting a security issue: [`SECURITY.md`](SECURITY.md).
