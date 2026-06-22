# AFRI Africa Oracle — Distribution Surfaces

Phase-0 oracle is now shipped through **5 channels** so any African dev, agent
operator, edge node, or wallet can consume the feed natively.

| Channel | Path | Audience | Install |
|---|---|---|---|
| Python SDK | `sdk/python/` | data scientists, backend devs | `pip install africa-oracle` |
| TS/JS SDK | `sdk/typescript/` | web/Node/Deno/Bun/CF Workers | `npm i @afri/oracle` |
| Browser extension (MV3) | `sdk/extension/` | end users (Chromium + FF) | unpacked or webstore |
| PWA (installable mobile) | `sdk/pwa/` | phones (Android/iOS), KaiOS-ish | "Add to home screen" |
| VSCode plugin | `sdk/vscode/` | developers | `.vsix` install |
| POSIX one-liner | `sdk/installer/install.sh` | edge nodes, Raspberry Pi, Termux | `curl ... \| sh` |

## Build everything

```sh
bash sdk/build.sh
# → dist/
#     africa_oracle-0.4.0-py3-none-any.whl   (pip)
#     afri-oracle-0.4.0.tgz                  (npm)
#     afri-extension-0.4.0.zip               (Chrome/FF webstore)
#     afri-pwa-0.4.0.tgz                     (static host)
#     afri-oracle-0.4.0.vsix                 (VS Code)
```

## Why no native APK?

KafCa rationale: a TWA APK is a 30-50 MB WebView wrapper around `sdk/pwa/`.
We ship the PWA — users can install it directly, or wrap it with Bubblewrap
later for Play Store. ARM64 falls out for free via the device WebView.

## ARM64 native everywhere

| Surface | ARM64 story |
|---|---|
| Python SDK | stdlib only — no compiled wheels |
| TS SDK | pure ECMAScript — runs on `arm64` Node, Deno, Bun |
| Extension | DOM only — works in `arm64` Chromium/Firefox builds |
| PWA | static — runs on every ARM phone WebView |
| VSCode | pure JS using `node:https` — `arm64` VSCode supported |
| CLI installer | POSIX sh + ghcr.io multi-arch image |

## Evolve mechanism (skill artifact)

Every SDK bundles `skills/africa-oracle-devflow.md` so consumers can self-improve:

```python
from africa_oracle import devflow_skill
print(devflow_skill())   # latest distilled DevFlow skill
```

The skill version lives in `metadata.version` inside the file and is bumped by
the `evo-metaclaw` step at the end of each release pipeline.
