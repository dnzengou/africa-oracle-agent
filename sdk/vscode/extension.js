// VS Code extension: thin command-palette wrapper around the oracle API.
// Uses node:https (built-in) — zero deps to keep VSIX small.

const vscode = require("vscode");
const https = require("node:https");
const http = require("node:http");
const { URL } = require("node:url");

function cfg() {
  const c = vscode.workspace.getConfiguration("afri");
  return {
    baseUrl: (c.get("baseUrl") || "https://africa-oracle.fly.dev").replace(/\/$/, ""),
    minProviders: Math.max(1, Math.min(4, c.get("minProviders") || 2)),
  };
}

function request(method, urlStr, body) {
  return new Promise((resolve, reject) => {
    const u = new URL(urlStr);
    const lib = u.protocol === "http:" ? http : https;
    const data = body ? Buffer.from(JSON.stringify(body)) : null;
    const req = lib.request(
      {
        method,
        hostname: u.hostname,
        port: u.port || (u.protocol === "http:" ? 80 : 443),
        path: u.pathname + u.search,
        timeout: 10_000,
        headers: {
          Accept: "application/json",
          ...(data ? { "Content-Type": "application/json", "Content-Length": data.length } : {}),
        },
      },
      (res) => {
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          const text = Buffer.concat(chunks).toString();
          if (res.statusCode < 200 || res.statusCode >= 300) {
            reject(new Error(`${res.statusCode} ${res.statusMessage}: ${text.slice(0, 200)}`));
            return;
          }
          try { resolve(JSON.parse(text)); } catch (e) { reject(e); }
        });
      },
    );
    req.on("error", reject);
    req.on("timeout", () => { req.destroy(new Error("timeout")); });
    if (data) req.write(data);
    req.end();
  });
}

async function show(title, obj) {
  const doc = await vscode.workspace.openTextDocument({
    language: "json",
    content: `// ${title}\n${JSON.stringify(obj, null, 2)}\n`,
  });
  await vscode.window.showTextDocument(doc, { preview: true });
}

async function cmdHealth() {
  const { baseUrl } = cfg();
  try { await show("AFRI · /health", await request("GET", `${baseUrl}/health`)); }
  catch (e) { vscode.window.showErrorMessage(`AFRI: ${e.message}`); }
}

async function cmdHunt() {
  const { baseUrl } = cfg();
  const provider = await vscode.window.showQuickPick(
    ["safaricom", "airtel", "orange", "mtn"], { placeHolder: "Provider" });
  if (!provider) return;
  const country = await vscode.window.showInputBox({
    prompt: "Country code (ISO 3166-1 alpha-2)",
    placeHolder: "KE / GH / NG / CI ...",
    validateInput: (v) => /^[A-Z]{2}$/.test(v.toUpperCase()) ? null : "Two-letter code",
  });
  if (!country) return;
  try {
    const r = await request("POST", `${baseUrl}/hunt`,
      { provider, country: country.toUpperCase(), simulate: true });
    await show(`AFRI · ${provider} ${country.toUpperCase()}`, r);
  } catch (e) { vscode.window.showErrorMessage(`AFRI: ${e.message}`); }
}

async function cmdQuorum() {
  const { baseUrl, minProviders } = cfg();
  try {
    const r = await request("POST", `${baseUrl}/feeds/quorum`, { min_providers: minProviders });
    await show(`AFRI · quorum(${minProviders})`, r);
  } catch (e) { vscode.window.showErrorMessage(`AFRI: ${e.message}`); }
}

async function cmdSetUrl() {
  const cur = vscode.workspace.getConfiguration("afri").get("baseUrl");
  const v = await vscode.window.showInputBox({
    prompt: "AFRI API base URL", value: cur,
    validateInput: (s) => /^https?:\/\//.test(s) ? null : "must start with http(s)://",
  });
  if (!v) return;
  await vscode.workspace.getConfiguration("afri").update(
    "baseUrl", v, vscode.ConfigurationTarget.Global);
  vscode.window.showInformationMessage(`AFRI URL set to ${v}`);
}

function activate(ctx) {
  ctx.subscriptions.push(
    vscode.commands.registerCommand("afri.health", cmdHealth),
    vscode.commands.registerCommand("afri.hunt",   cmdHunt),
    vscode.commands.registerCommand("afri.quorum", cmdQuorum),
    vscode.commands.registerCommand("afri.setUrl", cmdSetUrl),
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
