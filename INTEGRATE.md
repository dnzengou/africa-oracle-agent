# Integrate

Copy-paste recipes for consuming the Africa Oracle feed in your app. Every example uses the public endpoint `https://africa-oracle.fly.dev` — swap for your self-hosted URL if you deploy your own.

- [One line (embed widget)](#one-line-embed-widget)
- [cURL](#curl)
- [JavaScript / TypeScript](#javascript--typescript)
- [Next.js (App Router)](#nextjs-app-router)
- [React / Preact / Vue](#react--preact--vue)
- [Python](#python)
- [Node.js](#nodejs)
- [Server-Sent Events (live stream)](#server-sent-events-live-stream)
- [Merchant checkout: show local price in real time](#merchant-checkout-show-local-price-in-real-time)
- [Remittance: price a transfer](#remittance-price-a-transfer)
- [Rate limits, CORS, caching](#rate-limits-cors-caching)

---

## One line (embed widget)

```html
<script src="https://africa-oracle.fly.dev/widget.js"
        data-from="KES" data-to="NGN" data-amount="100"></script>
```

Attributes (all optional): `data-from`, `data-to`, `data-amount`, `data-theme` (`auto` / `dark` / `light`), `data-api` (override the API origin). Refreshes every 30 s.

## cURL

```sh
# Simple rate (GET, cacheable, bookmarkable)
curl -s https://africa-oracle.fly.dev/rate/KES/NGN

# Convert an amount
curl -s -X POST https://africa-oracle.fly.dev/convert \
  -H 'Content-Type: application/json' \
  -d '{"from":"KES","to":"NGN","amount":1000}'

# Full robust feed
curl -s -X POST https://africa-oracle.fly.dev/feeds/robust \
  -H 'Content-Type: application/json' \
  -d '{"min_providers":2,"tukey_k":1.5}'
```

## JavaScript / TypeScript

```ts
async function convert(from: string, to: string, amount: number) {
  const r = await fetch("https://africa-oracle.fly.dev/convert", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({from, to, amount, side: "mid"}),
  });
  if (!r.ok) throw new Error(`oracle: ${r.status}`);
  return r.json(); // { from, to, rate, side, spread_bps, confidence, providers_from, providers_to }
}

// or, even simpler, for a quote without amount:
async function rate(from: string, to: string) {
  const r = await fetch(`https://africa-oracle.fly.dev/rate/${from}/${to}`);
  return r.json();
}
```

## Next.js (App Router)

Server component — cache for 10 s to match the oracle TTL:

```tsx
// app/components/LiveRate.tsx
async function fetchRate(from: string, to: string) {
  const r = await fetch(`https://africa-oracle.fly.dev/rate/${from}/${to}`, {
    next: { revalidate: 10 },
  });
  return r.json();
}

export default async function LiveRate({ from, to }: { from: string; to: string }) {
  const { rate, confidence } = await fetchRate(from, to);
  return (
    <div>
      1 {from} = {rate.toFixed(4)} {to}
      <small> · {(confidence * 100).toFixed(0)}% confidence</small>
    </div>
  );
}
```

## React / Preact / Vue

Use the SDK `@afri/oracle`:

```tsx
import { OracleClient } from "@afri/oracle";

const oracle = new OracleClient({ url: "https://africa-oracle.fly.dev" });

export function Converter() {
  const [amount, setAmount] = useState(100);
  const [out, setOut] = useState<number | null>(null);
  useEffect(() => {
    oracle.convert({ from: "KES", to: "NGN", amount }).then(r => setOut(r.to.amount));
  }, [amount]);
  return <>...</>;
}
```

## Python

```python
import httpx

with httpx.Client(base_url="https://africa-oracle.fly.dev", timeout=10) as c:
    r = c.post("/convert", json={"from": "KES", "to": "NGN", "amount": 1000})
    r.raise_for_status()
    data = r.json()
    print(f"{data['from']['amount']} {data['from']['currency']} = "
          f"{data['to']['amount']} {data['to']['currency']} "
          f"({data['confidence']*100:.0f}% confidence)")
```

Or use the first-party Python SDK:

```sh
pip install africa-oracle
```

```python
from africa_oracle import OracleClient
oracle = OracleClient()  # defaults to the public endpoint
print(oracle.rate("KES", "NGN"))
```

## Node.js

```js
import { request } from "undici";
const r = await request("https://africa-oracle.fly.dev/rate/KES/NGN");
console.log(await r.body.json());
```

## Server-Sent Events (live stream)

```js
const es = new EventSource("https://africa-oracle.fly.dev/feeds/stream?interval=30");
es.onmessage = (ev) => {
  const feed = JSON.parse(ev.data);
  console.log(feed.currencies, "currencies live");
};
```

Server-side with `httpx`:

```python
import httpx
with httpx.stream("GET", "https://africa-oracle.fly.dev/feeds/stream?interval=30") as r:
    for line in r.iter_lines():
        if line.startswith("data: "):
            print(line[6:])
```

## Merchant checkout: show local price in real time

Use case: a Nairobi merchant displays a product priced in USD but accepts KES; keep the KES tag live against the oracle.

```html
<div>
  Price:
  <span id="usd">$29.99</span>
  <span>·</span>
  <span id="kes"></span>
</div>
<script>
  async function refresh() {
    const { rate } = await fetch("https://africa-oracle.fly.dev/rate/USD/KES").then(r => r.json())
      .catch(() => ({ rate: null }));
    // USD→KES not directly in feed — compute via KES mid: 1 USD costs `KES mid-price`
    const r = await fetch("https://africa-oracle.fly.dev/rate/KES/KES").then(r => r.json()); // placeholder
    document.getElementById("kes").textContent = r ? `KES ${(29.99 * r.rate).toFixed(0)}` : "—";
  }
  refresh(); setInterval(refresh, 30000);
</script>
```

Note: the oracle quotes African currencies vs USD internally. To price USD → KES, use `/rate/KES/KES` (identity) with the raw `mid_price` from `/feeds/robust` instead. A cleaner pattern is to anchor product prices in a hard currency and cache the conversion rate for 10–30 s.

## Remittance: price a transfer

```ts
const { to, confidence } = await (await fetch("https://africa-oracle.fly.dev/convert", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ from: "USD", to: "NGN", amount: 100, side: "sell" }),
})).json();
// to.amount = how many NGN the recipient gets for $100
```

Pick `side`:

- `"mid"` — neutral display
- `"buy"` — consumer buying the destination currency (realistic wire cost)
- `"sell"` — consumer selling destination back to source

## Rate limits, CORS, caching

- **Rate limit**: 60 requests / minute / IP on `/hunt`, `/feeds/*`, `/convert`, `/rate/*`. `/health`, `/metrics`, `/`, `/widget.js`, `/llms.txt`, `/ai.txt`, `/.well-known/*` are unlimited.
- **CORS**: `Access-Control-Allow-Origin: *` on all endpoints. You can call the API from any browser.
- **Caching**: the server caches aggregated feeds for 10 s. Rapid successive requests return the same snapshot. Widget refreshes every 30 s by default; adjust via its own timer if you fork it.
- **Self-host**: if you expect >60 req/min from a single IP (e.g. server-side rendering a lot of pages), self-host via `docker compose up` (see [DEPLOY.md](DEPLOY.md)) and bypass the shared rate limit entirely.
