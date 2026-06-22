"""SDK smoke tests — verify the Python distribution layer imports and signatures match."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SDK_PY = ROOT / "sdk" / "python"
sys.path.insert(0, str(SDK_PY))


def test_python_sdk_imports():
    import africa_oracle

    assert africa_oracle.__version__ == "0.4.0"
    assert hasattr(africa_oracle, "Client")
    assert hasattr(africa_oracle, "OracleError")
    assert hasattr(africa_oracle, "PriceFeed")
    assert hasattr(africa_oracle, "QuorumReport")


def test_client_default_url_overridable(monkeypatch):
    monkeypatch.setenv("AFRICA_ORACLE_URL", "https://example.test")
    # re-import to pick up env
    import importlib

    import africa_oracle.client as cm

    importlib.reload(cm)
    c = cm.Client()
    assert c.base_url == "https://example.test"


def test_oracle_error_has_correct_base():
    from africa_oracle import OracleError

    assert issubclass(OracleError, RuntimeError)


@pytest.mark.parametrize(
    "manifest",
    [
        "sdk/extension/manifest.json",
        "sdk/pwa/manifest.webmanifest",
        "sdk/typescript/package.json",
        "sdk/vscode/package.json",
    ],
)
def test_manifest_is_valid_json(manifest):
    with open(ROOT / manifest, encoding="utf-8") as f:
        data = json.load(f)
    assert data
    if manifest.endswith(("manifest.json", "manifest.webmanifest")):
        assert data["name"]
    if "package.json" in manifest:
        assert data["version"] == "0.4.0"


def test_extension_csp_blocks_remote_scripts():
    """MV3 extension must declare CSP that forbids remote script-src."""
    with open(ROOT / "sdk/extension/manifest.json", encoding="utf-8") as f:
        m = json.load(f)
    csp = m["content_security_policy"]["extension_pages"]
    assert "script-src 'self'" in csp
    assert "'unsafe-eval'" not in csp
    assert "'unsafe-inline'" not in csp


def _strip_comments(src: str) -> str:
    """Remove // line comments + /* block */ comments — naive but enough for these files."""
    import re

    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    src = re.sub(r"//.*", "", src)
    return src


def test_pwa_serves_no_eval():
    src = _strip_comments((ROOT / "sdk/pwa/app.js").read_text(encoding="utf-8"))
    assert "eval(" not in src
    assert ".innerHTML" not in src
    assert "document.write" not in src


def test_extension_popup_uses_no_innerhtml():
    src = _strip_comments((ROOT / "sdk/extension/popup.js").read_text(encoding="utf-8"))
    assert ".innerHTML" not in src
    assert "eval(" not in src
