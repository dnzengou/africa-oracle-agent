# AFRI Oracle — VS Code extension

Query the AFRI oracle from the command palette.

## Install (local)

```sh
npm i -g @vscode/vsce
cd sdk/vscode
vsce package                 # → afri-oracle-0.4.0.vsix
code --install-extension afri-oracle-0.4.0.vsix
```

## Commands

- `AFRI: Oracle health`
- `AFRI: Hunt single feed`
- `AFRI: Quorum report`
- `AFRI: Set API URL`

Settings: `afri.baseUrl`, `afri.minProviders`.
