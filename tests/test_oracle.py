"""Tests for oracle_agent.py — provider/country mapping, simulation, aggregation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle_agent import PROVIDERS, REFERENCE_RATES, OracleAgent, OracleAggregator


# ─── Provider configuration ──────────────────────────────────────────────────


def test_four_providers_registered():
    assert set(PROVIDERS.keys()) == {"safaricom", "airtel", "orange", "mtn"}


@pytest.mark.parametrize("slug", ["safaricom", "airtel", "orange", "mtn"])
def test_provider_has_required_fields(slug):
    p = PROVIDERS[slug]
    assert "name" in p and isinstance(p["name"], str)
    assert "countries" in p and len(p["countries"]) >= 1
    assert "currency" in p
    assert p["agent_count"] > 0
    for country in p["countries"]:
        assert country in p["currency"], f"{slug}/{country} missing currency"


def test_every_currency_has_reference_rate():
    for p in PROVIDERS.values():
        for ccy in p["currency"].values():
            assert ccy in REFERENCE_RATES, f"missing rate: {ccy}"


# ─── OracleAgent ─────────────────────────────────────────────────────────────


def test_agent_rejects_unknown_provider():
    with pytest.raises(ValueError):
        OracleAgent("zelle", "US")


def test_agent_rejects_unsupported_country():
    with pytest.raises(ValueError):
        OracleAgent("safaricom", "ZZ")


def test_agent_simulates_price():
    a = OracleAgent("safaricom", "KE", simulate=True)
    feed = a.fetch_price()
    assert feed["currency"] == "KES"
    assert feed["country"] == "KE"
    assert feed["simulated"] is True
    assert feed["buy_price"] > 0
    assert feed["sell_price"] > feed["buy_price"]
    assert 0 < feed["spread"] < 0.5
    assert 0 < feed["confidence"] <= 0.99
    assert len(feed["agent_id"]) == 16


def test_real_fetch_not_implemented():
    a = OracleAgent("mtn", "GH", simulate=False)
    with pytest.raises(NotImplementedError):
        a.fetch_price()


# ─── Aggregator ──────────────────────────────────────────────────────────────


def test_aggregator_empty_returns_error():
    agg = OracleAggregator()
    out = agg.aggregate()
    assert "error" in out


def test_aggregator_consensus_per_currency():
    agg = OracleAggregator()
    agg.add_agent(OracleAgent("safaricom", "KE"))
    agg.add_agent(OracleAgent("airtel", "KE"))
    out = agg.aggregate()
    assert out["agents_reporting"] == 2
    kes = [c for c in out["prices"] if c["currency"] == "KES"]
    assert len(kes) == 1
    assert kes[0]["agent_count"] == 2
    assert kes[0]["buy_price"] > 0


def test_aggregator_groups_xof_across_orange_countries():
    agg = OracleAggregator()
    for country in ("CI", "SN", "ML"):
        agg.add_agent(OracleAgent("orange", country))
    out = agg.aggregate()
    xof = [c for c in out["prices"] if c["currency"] == "XOF"]
    assert len(xof) == 1
    assert xof[0]["agent_count"] == 3
    assert set(xof[0]["countries"]) == {"CI", "SN", "ML"}


def test_aggregator_volume_weighted_spread_in_range():
    agg = OracleAggregator()
    agg.add_agent(OracleAgent("mtn", "NG"))
    out = agg.aggregate()
    ngn = next(c for c in out["prices"] if c["currency"] == "NGN")
    assert 0 < ngn["spread"] < 0.05  # < 5%


# ─── Quorum (Resilient pillar) ───────────────────────────────────────────────


def test_quorum_drops_single_provider_currencies():
    """A currency with only one provider must NOT pass quorum=2."""
    agg = OracleAggregator()
    agg.add_agent(OracleAgent("mtn", "NG"))  # NGN only on mtn → 1 provider
    agg.add_agent(OracleAgent("safaricom", "KE"))
    agg.add_agent(OracleAgent("airtel", "KE"))  # KES has 2 providers
    out = agg.quorum_aggregate(min_providers=2)
    currencies_passed = {p["currency"] for p in out["prices"]}
    currencies_failed = {p["currency"] for p in out["quorum_failed"]}
    assert "KES" in currencies_passed
    assert "NGN" in currencies_failed
    assert out["quorum_threshold"] == 2


def test_quorum_one_admits_everything():
    agg = OracleAggregator()
    agg.add_agent(OracleAgent("mtn", "NG"))
    out = agg.quorum_aggregate(min_providers=1)
    assert len(out["prices"]) == 1
    assert out["quorum_failed"] == []


def test_quorum_empty_input():
    out = OracleAggregator().quorum_aggregate(min_providers=2)
    assert "error" in out


# ─── FastAPI endpoint smoke (Resilient + Scalable + Affordable) ─────────────


def test_api_health_and_metrics():
    from fastapi.testclient import TestClient

    from api.app import app

    client = TestClient(app)

    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["providers"] == 4

    r = client.get("/metrics")
    assert r.status_code == 200
    assert "africa_oracle_info" in r.text
    assert 'version="' in r.text


def test_api_quorum_endpoint():
    from fastapi.testclient import TestClient

    from api.app import app

    client = TestClient(app)
    r = client.post("/feeds/quorum", json={"min_providers": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["quorum_threshold"] == 2
    assert isinstance(body["prices"], list)
    assert isinstance(body["quorum_failed"], list)


def test_api_hunt_rejects_unknown_provider():
    from fastapi.testclient import TestClient

    from api.app import app

    client = TestClient(app)
    r = client.post("/hunt", json={"provider": "zelle", "country": "US"})
    assert r.status_code == 400


# ─── Tukey-fence outlier filter (Resilient pillar — manipulation defense) ────


def test_tukey_bounds_drops_obvious_outlier():
    """Classic textbook case: 7 clustered values + 1 wild outlier → outlier
    falls outside the fence."""
    lo, hi = OracleAggregator._tukey_bounds(
        [100.0, 101.0, 99.0, 100.5, 99.5, 100.2, 100.8, 5000.0]
    )
    assert lo < 100 < hi
    assert hi < 5000  # outlier rejected


def test_tukey_bounds_skips_small_samples():
    """Fewer than 4 samples → IQR is meaningless; return open bounds."""
    lo, hi = OracleAggregator._tukey_bounds([100.0, 200.0, 50.0])
    assert lo == float("-inf")
    assert hi == float("inf")


def test_tukey_bounds_keeps_clustered_feeds():
    """All clustered within IQR → both bounds accept the cluster."""
    vals = [150.0, 150.1, 149.9, 150.2, 149.8, 150.05]
    lo, hi = OracleAggregator._tukey_bounds(vals)
    for v in vals:
        assert lo <= v <= hi


def test_robust_quorum_runs_end_to_end():
    """Smoke-test the full pipeline: feeds in, prices + outliers_dropped out."""
    agg = OracleAggregator()
    agg.add_agent(OracleAgent("safaricom", "KE"))
    agg.add_agent(OracleAgent("airtel", "KE"))
    agg.add_agent(OracleAgent("safaricom", "TZ"))  # TZS, only safaricom
    out = agg.robust_quorum_aggregate(min_providers=2, tukey_k=1.5)
    assert out["quorum_threshold"] == 2
    assert out["tukey_k"] == 1.5
    assert "outliers_dropped" in out
    assert isinstance(out["outliers_dropped"], list)
    assert out["agents_kept"] <= out["agents_reporting"]
    currencies = {p["currency"] for p in out["prices"]}
    assert "KES" in currencies   # 2 providers, passes quorum
    assert "TZS" not in currencies  # only 1 provider, fails quorum
    failed = {p["currency"] for p in out["quorum_failed"]}
    assert "TZS" in failed


def test_robust_quorum_drops_planted_outlier():
    """Inject a synthetic outlier directly into a feed group via a stub agent
    and confirm robust_quorum_aggregate filters it out before consensus."""

    class StubAgent:
        def __init__(self, feed):
            self._feed = feed
            self.agent_id = feed.get("agent_id", "stub")

        def fetch_price(self):
            return self._feed

    base_feed = {
        "provider": "Test", "provider_slug": "t",
        "country": "XX", "currency": "TST",
        "timestamp": 0, "datetime": "2026-01-01T00:00:00+00:00",
        "spread": 0.005, "spread_bps": 50,
        "volume_24h": 1_000_000, "confidence": 0.9,
        "sources": 100, "agent_id": "a", "simulated": True,
    }

    def feed(provider, mid, agent_id):
        return {**base_feed, "provider": provider, "agent_id": agent_id,
                "buy_price": mid * 0.998, "sell_price": mid * 1.002,
                "mid_price": mid}

    agg = OracleAggregator()
    # 7 clustered around 100 + 1 wild outlier at 1000 (realistic multi-agent
    # density — see _tukey_bounds() docstring on N≥6 reliability)
    cluster = [
        ("MTN-A", 100.0), ("MTN-B", 99.9),
        ("Safaricom-A", 100.5), ("Safaricom-B", 100.1),
        ("Airtel", 99.8),
        ("Orange-A", 100.2), ("Orange-B", 100.3),
        ("Compromised", 1000.0),
    ]
    for i, (prov, mid) in enumerate(cluster):
        agg.agents.append(StubAgent(feed(prov, mid, f"a{i}")))

    out = agg.robust_quorum_aggregate(min_providers=2, tukey_k=1.5)
    # The wild outlier must be dropped
    dropped_providers = {o["provider"] for o in out["outliers_dropped"]}
    assert "Compromised" in dropped_providers
    # Consensus mid_price must be near the cluster, not skewed by the outlier
    tst = next(p for p in out["prices"] if p["currency"] == "TST")
    assert 99.0 < tst["mid_price"] < 101.0
    assert tst["agent_count"] == 7  # outlier excluded


def test_api_robust_endpoint():
    from fastapi.testclient import TestClient

    from api.app import app

    client = TestClient(app)
    r = client.post("/feeds/robust", json={"min_providers": 2, "tukey_k": 1.5})
    assert r.status_code == 200
    body = r.json()
    assert body["quorum_threshold"] == 2
    assert body["tukey_k"] == 1.5
    assert isinstance(body["prices"], list)
    assert isinstance(body["outliers_dropped"], list)
    assert "agents_kept" in body


def test_api_robust_rejects_invalid_tukey():
    from fastapi.testclient import TestClient

    from api.app import app

    client = TestClient(app)
    # tukey_k above the upper bound (3.0)
    r = client.post("/feeds/robust", json={"min_providers": 2, "tukey_k": 10})
    assert r.status_code == 422


# ─── /convert endpoint (Alternative pillar — commercial use case) ────────────


def test_convert_amount_mid_side():
    from oracle_agent import convert_amount

    feed = {"prices": [
        {"currency": "KES", "buy_price": 149.0, "sell_price": 151.0,
         "mid_price": 150.0, "spread": 0.013, "avg_confidence": 0.95,
         "providers": ["Safaricom M-Pesa", "Airtel Money"]},
        {"currency": "NGN", "buy_price": 1549.0, "sell_price": 1551.0,
         "mid_price": 1550.0, "spread": 0.001, "avg_confidence": 0.90,
         "providers": ["MTN MoMo"]},
    ]}
    out = convert_amount(feed, "KES", "NGN", 1000.0, side="mid")
    # 1000 KES / 150 = 6.667 USD × 1550 = ~10333 NGN
    assert out["from"]["currency"] == "KES"
    assert out["to"]["currency"] == "NGN"
    assert 10000 < out["to"]["amount"] < 10500
    assert out["rate"] > 0
    assert out["side"] == "mid"


def test_convert_amount_unknown_currency_raises():
    from oracle_agent import convert_amount

    feed = {"prices": [
        {"currency": "KES", "buy_price": 149.0, "sell_price": 151.0,
         "mid_price": 150.0, "spread": 0.013, "avg_confidence": 0.95,
         "providers": ["S"]},
    ]}
    import pytest
    with pytest.raises(ValueError):
        convert_amount(feed, "KES", "ZZZ", 100.0)


def test_api_convert_endpoint():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.post("/convert", json={"from": "KES", "to": "NGN", "amount": 100})
    assert r.status_code == 200
    body = r.json()
    assert body["from"]["currency"] == "KES"
    assert body["to"]["currency"] == "NGN"
    assert body["to"]["amount"] > 0


def test_api_convert_rejects_unknown_currency():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    # ZZZ is not a real ISO 4217 code and not in the feed; USD is now supported
    r = client.post("/convert", json={"from": "ZZZ", "to": "KES", "amount": 100})
    assert r.status_code == 400


def test_api_dashboard_served_at_root():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "Africa Oracle" in r.text
    assert r.headers["content-type"].startswith("text/html")


def test_api_cors_headers_present():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.options(
        "/feeds/all",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "*"


# ─── GET /rate/{from}/{to} (cite-friendly endpoint) ──────────────────────────


def test_api_rate_simple_get():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/rate/KES/NGN")
    assert r.status_code == 200
    body = r.json()
    assert body["from"] == "KES"
    assert body["to"] == "NGN"
    assert body["rate"] > 0
    assert 0 < body["confidence"] <= 1
    assert isinstance(body["providers"], list)


def test_api_rate_404_on_unknown_currency():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    # ZZZ is not a real ISO 4217 code and not in the feed
    r = client.get("/rate/ZZZ/KES")
    assert r.status_code == 404


def test_api_rate_lowercase_currency_still_works():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/rate/kes/ngn")
    assert r.status_code == 200
    assert r.json()["from"] == "KES"


# ─── /widget.js embeddable widget ────────────────────────────────────────────


def test_api_widget_js_served():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/widget.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/javascript")
    # The widget must reference the /convert endpoint and self-mount
    assert "/convert" in r.text
    assert "document.createElement" in r.text
    # Cache-Control present so CDNs can serve it
    assert "max-age" in r.headers.get("cache-control", "")


# ─── AI-discoverability (GEO pass) ───────────────────────────────────────────


def test_api_llms_txt_served():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/llms.txt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "Africa Oracle" in r.text


def test_api_ai_txt_served():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/ai.txt")
    assert r.status_code == 200
    assert "User-agent" in r.text


def test_api_ai_plugin_json_served():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/.well-known/ai-plugin.json")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == "v1"
    assert body["name_for_model"] == "africa_oracle"
    assert body["api"]["type"] == "openapi"


def test_api_security_txt_served():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/.well-known/security.txt")
    assert r.status_code == 200
    assert "Contact:" in r.text


def test_api_dashboard_has_jsonld_and_og():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    # OpenGraph for AI search tools + social embeds
    assert 'property="og:title"' in r.text
    # Schema.org structured data for LLM citers
    assert 'application/ld+json' in r.text
    assert '"@type": "SoftwareApplication"' in r.text
    # AI-friendly robots directive
    assert 'name="robots"' in r.text


def test_api_openapi_schema_published():
    """OpenAPI schema is what the /.well-known/ai-plugin.json points to;
    without it ChatGPT / Claude can't discover the tools."""
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert schema["info"]["title"] == "Africa Oracle Extraction Agent"
    # All public endpoints advertised
    paths = schema["paths"]
    for p in ("/health", "/convert", "/rate/{from_ccy}/{to_ccy}", "/widget.js"):
        assert p in paths, f"missing path in OpenAPI: {p}"


# ─── USD as synthetic base (fixes merchant/remittance examples) ──────────────


def test_convert_usd_to_kes_works():
    """USD must work even though it isn't in REFERENCE_RATES — the aggregator
    feed is USD-quoted by construction, so USD is a synthetic base at 1.0."""
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.post("/convert", json={"from": "USD", "to": "KES", "amount": 100})
    assert r.status_code == 200
    body = r.json()
    assert body["from"]["currency"] == "USD"
    assert body["to"]["currency"] == "KES"
    # KES is around 150/USD, so 100 USD → ~15,000 KES. Allow wide band for simulator noise.
    assert 10_000 < body["to"]["amount"] < 20_000


def test_rate_usd_to_any_works():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/rate/USD/NGN")
    assert r.status_code == 200
    body = r.json()
    assert body["from"] == "USD"
    assert body["to"] == "NGN"
    assert body["rate"] > 0


def test_convert_amount_usd_identity():
    from oracle_agent import convert_amount

    # USD → USD must be exactly identity, even with an empty feed
    out = convert_amount({"prices": []}, "USD", "USD", 42.0)
    assert out["to"]["amount"] == 42.0
    assert out["rate"] == 1.0


# ─── Classic + agentic SEO surfaces ──────────────────────────────────────────


def test_api_robots_txt():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/robots.txt")
    assert r.status_code == 200
    # Explicit AI-bot allows
    for bot in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"):
        assert bot in r.text, f"missing {bot} in robots.txt"
    assert "Sitemap:" in r.text


def test_api_sitemap_xml():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    assert "<urlset" in r.text
    assert "<loc>" in r.text


def test_api_feed_xml():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/feed.xml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/rss+xml")
    assert "<rss" in r.text and "</rss>" in r.text
    assert "<item>" in r.text  # at least one rate item


def test_api_faq_page_has_jsonld_faqpage():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/faq")
    assert r.status_code == 200
    # Schema.org FAQPage is the whole point
    assert '"@type": "FAQPage"' in r.text
    assert '"@type": "Question"' in r.text
    # Canonical URL + robots directive
    assert 'rel="canonical"' in r.text


def test_api_agents_json_discovery():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/.well-known/agents.json")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "africa-oracle"
    assert "capabilities" in body and len(body["capabilities"]) >= 3
    assert body["endpoints"]["mcp"].endswith("/mcp.json")


def test_api_mcp_json_tool_catalog():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/mcp.json")
    assert r.status_code == 200
    body = r.json()
    tool_names = {t["name"] for t in body["tools"]}
    assert {"convert_currency", "get_rate", "list_providers"} <= tool_names
    # convert_currency must declare its JSON schema for the MCP client
    convert = next(t for t in body["tools"] if t["name"] == "convert_currency")
    assert "input_schema" in convert


def test_dashboard_version_is_templated():
    """Catches version drift — the dashboard must show the running VERSION,
    not a stale hardcoded string from a previous release."""
    from fastapi.testclient import TestClient
    from api.app import app, VERSION

    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    # The templated version token must be gone and the real version present
    assert "{{VERSION}}" not in r.text
    assert f'"softwareVersion": "{VERSION}"' in r.text


def test_dashboard_has_persona_chips():
    """Onboarding chips must be present and lead to the right anchors."""
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/")
    for href in ('#convert', '#embed', '/docs', '/mcp.json', '/faq'):
        assert f'href="{href}"' in r.text, f"missing persona chip: {href}"
