(() => {
  "use strict";

  const BASE_URL = localStorage.getItem("afri.baseUrl") || "https://africa-oracle.fly.dev";
  const MIN_PROVIDERS = parseInt(localStorage.getItem("afri.minProviders") || "2", 10);
  const CACHE_TTL_MS = 60_000;

  const $ = (id) => document.getElementById(id);
  const status = $("status");
  const content = $("content");
  const ts = $("ts");
  const refreshBtn = $("refresh");
  const installBtn = $("install");

  const setStatus = (text, cls) => { status.textContent = text; status.className = `status ${cls || ""}`; };

  const fmt = (n, d = 2) =>
    typeof n === "number" ? n.toLocaleString(undefined, { maximumFractionDigits: d }) : "-";

  function render(report) {
    while (content.firstChild) content.removeChild(content.firstChild);
    if (!report?.prices?.length) {
      const div = document.createElement("div");
      div.className = "empty";
      div.textContent = "No quorum feeds available.";
      content.appendChild(div);
      return;
    }
    const table = document.createElement("table");
    const thead = table.createTHead().insertRow();
    for (const h of ["CCY", "Mid", "Spread bps", "Vol 24h", "N"]) {
      const th = document.createElement("th");
      th.textContent = h;
      thead.appendChild(th);
    }
    const tbody = table.createTBody();
    for (const p of report.prices) {
      const r = tbody.insertRow();
      const cells = [
        p.currency,
        fmt(p.mid_price, 4),
        fmt(p.spread_bps, 1),
        fmt(p.total_volume_24h, 0),
        String(p.agent_count ?? "-"),
      ];
      for (const c of cells) {
        const td = r.insertCell();
        td.textContent = String(c);
      }
    }
    content.appendChild(table);
    ts.textContent = new Date(report.timestamp * 1000).toLocaleTimeString();
  }

  async function refresh() {
    refreshBtn.disabled = true;
    setStatus("fetching…");
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 10_000);
      const res = await fetch(`${BASE_URL}/feeds/quorum`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ min_providers: MIN_PROVIDERS }),
        signal: ctrl.signal,
      });
      clearTimeout(t);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const report = await res.json();
      localStorage.setItem("afri.lastReport", JSON.stringify(report));
      localStorage.setItem("afri.lastFetch", String(Date.now()));
      render(report);
      setStatus(`ok · ${report.currencies} ccys`, "ok");
    } catch (e) {
      setStatus(`err: ${e.message}`, "err");
      const cached = localStorage.getItem("afri.lastReport");
      if (cached) render(JSON.parse(cached));
    } finally {
      refreshBtn.disabled = false;
    }
  }

  refreshBtn.addEventListener("click", refresh);

  let deferredPrompt = null;
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredPrompt = e;
    installBtn.hidden = false;
  });
  installBtn.addEventListener("click", async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === "accepted") installBtn.hidden = true;
    deferredPrompt = null;
  });

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("./sw.js").catch(() => { /* offline-only nice-to-have */ });
  }

  const cached = localStorage.getItem("afri.lastReport");
  const lastFetch = parseInt(localStorage.getItem("afri.lastFetch") || "0", 10);
  if (cached && Date.now() - lastFetch < CACHE_TTL_MS) {
    render(JSON.parse(cached));
    setStatus("cached", "ok");
    refresh();
  } else {
    refresh();
  }
})();
