// Popup: read cached quorum report from storage, render table.
// CSP-strict: no innerHTML, no eval, no inline handlers.

const DEFAULTS = { baseUrl: "https://africa-oracle.fly.dev", minProviders: 2 };

const $ = (id) => document.getElementById(id);
const setText = (el, t) => { el.textContent = t; };
const setClass = (el, c) => { el.className = c; };

function fmtNum(n, digits = 2) {
  return typeof n === "number" ? n.toLocaleString(undefined, { maximumFractionDigits: digits }) : "-";
}

function render(report) {
  const content = $("content");
  while (content.firstChild) content.removeChild(content.firstChild);
  if (!report || !report.prices || report.prices.length === 0) {
    const div = document.createElement("div");
    div.className = "empty";
    setText(div, "No quorum feeds available.");
    content.appendChild(div);
    return;
  }
  const table = document.createElement("table");
  const thead = table.createTHead().insertRow();
  for (const h of ["CCY", "Mid", "Spread (bps)", "Providers"]) {
    const th = document.createElement("th");
    setText(th, h);
    thead.appendChild(th);
  }
  const tbody = table.createTBody();
  for (const p of report.prices) {
    const row = tbody.insertRow();
    const cells = [
      p.currency,
      fmtNum(p.mid_price, 4),
      fmtNum(p.spread_bps, 1),
      String(p.agent_count ?? p.providers?.length ?? "-"),
    ];
    for (const c of cells) {
      const td = row.insertCell();
      setText(td, String(c));
    }
  }
  content.appendChild(table);
}

async function refresh() {
  const status = $("status");
  setText(status, "fetching…"); setClass(status, "status");
  const { baseUrl = DEFAULTS.baseUrl, minProviders = DEFAULTS.minProviders } =
    await chrome.storage.sync.get(["baseUrl", "minProviders"]);
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 10_000);
    const res = await fetch(`${baseUrl}/feeds/quorum`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ min_providers: minProviders }),
      signal: ctrl.signal,
    });
    clearTimeout(t);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const report = await res.json();
    await chrome.storage.local.set({ lastReport: report, lastFetch: Date.now() });
    render(report);
    setText(status, `ok · ${report.currencies} ccys`); setClass(status, "status ok");
    setText($("ts"), new Date(report.timestamp * 1000).toLocaleTimeString());
  } catch (e) {
    setText(status, `err: ${e.message}`); setClass(status, "status err");
    const { lastReport } = await chrome.storage.local.get("lastReport");
    if (lastReport) render(lastReport);
  }
}

$("refresh").addEventListener("click", (ev) => { ev.preventDefault(); refresh(); });

(async () => {
  const { lastReport, lastFetch } = await chrome.storage.local.get(["lastReport", "lastFetch"]);
  if (lastReport && lastFetch && Date.now() - lastFetch < 60_000) {
    render(lastReport);
    setText($("status"), `cached · ${lastReport.currencies} ccys`);
    setClass($("status"), "status ok");
    setText($("ts"), new Date(lastReport.timestamp * 1000).toLocaleTimeString());
  } else {
    await refresh();
  }
})();
