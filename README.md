# Africa Oracle Extraction Agent

**Phase 0: Mobile Money Oracle Bootstrapping**

Extract real-time price feeds from mobile money aggregator APIs across Africa. Each mobile money agent becomes a price oracle node by reporting their buy/sell spread for local currency ↔ mobile money balance.

## Architecture

```
Mobile Money APIs (M-Pesa, Airtel Money, Orange Money, MTN MoMo)
    ↓
Oracle Extraction Agents (one per provider per country)
    ↓
Aggregation Layer (median price, volume-weighted, spread analysis)
    ↓
Price Feed API (REST + WebSocket)
    ↓
Stablecoin Smart Contracts (Phase 1+)
```

## Supported Providers

| Provider | Countries | API Type | Status |
|----------|-----------|----------|--------|
| M-Pesa | KE, TZ, UG, RW, ZA, GH, CD, LS, MZ, SO | REST | Planned |
| Airtel Money | KE, UG, RW, ZA, CD, NE, GA, CG, TD | REST | Planned |
| Orange Money | CI, SN, ML, BF, NE, BJ, TG, CM, MG | REST | Planned |
| MTN MoMo | GH, UG, RW, ZA, CI, NG, CM, ZM | REST | Planned |

## Price Feed Format

```json
{
  "provider": "safaricom",
  "country": "KE",
  "currency": "KES",
  "timestamp": 1704067200,
  "buy_price": 150.25,
  "sell_price": 151.50,
  "spread": 0.0083,
  "volume_24h": 12500000.00,
  "confidence": 0.95,
  "sources": 142
}
```

## Deployment

1. Deploy extraction agents on cloud or edge (one per provider per country)
2. Agents poll APIs every 30 seconds
3. Aggregation layer computes median price, volume-weighted average, spread
4. Feed API serves data to stablecoin smart contracts

## Cost

~$5K/month for full deployment across 10 providers × 30 countries
