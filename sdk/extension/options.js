const $ = (id) => document.getElementById(id);

(async () => {
  const { baseUrl, minProviders } = await chrome.storage.sync.get([
    "baseUrl",
    "minProviders",
  ]);
  if (baseUrl) $("baseUrl").value = baseUrl;
  if (minProviders) $("minProviders").value = String(minProviders);
})();

$("save").addEventListener("click", async () => {
  const baseUrl = $("baseUrl").value.trim() || "https://africa-oracle.fly.dev";
  const minProviders = Math.max(1, Math.min(4, parseInt($("minProviders").value, 10) || 2));
  await chrome.storage.sync.set({ baseUrl, minProviders });
  const msg = $("msg");
  msg.hidden = false;
  setTimeout(() => { msg.hidden = true; }, 1500);
});
