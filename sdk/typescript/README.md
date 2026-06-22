# @afri/oracle (TypeScript SDK)

```sh
npm i @afri/oracle
```

```ts
import { Client } from "@afri/oracle";

const c = new Client();                     // uses AFRICA_ORACLE_URL or default
console.log(await c.health());
console.log(await c.hunt("mtn", "GH"));
console.log(await c.feedsQuorum(2));

// SSE stream (browsers / Deno / Bun)
const stop = c.streamFeeds((r) => console.log(r.prices));
// stop() when done
```

Zero deps. Works in browsers, Node ≥18, Deno, Bun, Cloudflare Workers.
