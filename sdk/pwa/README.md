# AFRI PWA — installable mobile app

KafCa rationale: a TWA-compliant PWA is the lightest mobile distribution on ARM64.
Native APK shell would be a 50 MB WebView wrapper around exactly this; instead
ship the PWA and let users "Add to home screen" or wrap it with Bubblewrap
later if a Play Store listing becomes required.

## Serve

Static files. Any HTTP host works — GitHub Pages, Netlify, Fly.io static, Cloudflare Pages.

```sh
# local test
python3 -m http.server -d sdk/pwa 8080
# → open http://localhost:8080 on phone (same wifi), tap "Add to home screen"
```

## Wrap as APK (optional, later)

```sh
npx @bubblewrap/cli init --manifest=https://<your-host>/manifest.webmanifest
npx @bubblewrap/cli build
# → app-release-signed.apk
```

## Icons

192×192 + 512×512 PNG in `icons/`. Build script writes placeholders if missing.
