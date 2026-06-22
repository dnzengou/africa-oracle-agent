// Background SW: refresh feeds every 5 min, keep them warm for the popup.

const ALARM = "afri-refresh";

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(ALARM, { periodInMinutes: 5 });
});

chrome.alarms.onAlarm.addListener(async (a) => {
  if (a.name !== ALARM) return;
  const { baseUrl = "https://africa-oracle.fly.dev", minProviders = 2 } =
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
    if (!res.ok) return;
    const report = await res.json();
    await chrome.storage.local.set({ lastReport: report, lastFetch: Date.now() });
  } catch {
    // swallow: popup shows last cached + the err
  }
});
