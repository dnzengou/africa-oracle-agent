# AFRI Oracle — Browser Extension (MV3)

Chromium (Chrome, Edge, Brave, Arc, Opera) + Firefox (MV3-capable).

## Install (developer mode)

1. `chrome://extensions` → enable Developer mode → "Load unpacked" → select this folder.
2. Pin the AFRI icon in the toolbar.
3. (Optional) Right-click icon → Options → set your own API URL.

## Package for store

```sh
cd sdk/extension
zip -r ../../dist/afri-extension-0.4.0.zip . -x '*.DS_Store'
```

## Icons

Place 16/32/48/128 px PNG icons in `icons/`. The build script generates placeholders if absent.
