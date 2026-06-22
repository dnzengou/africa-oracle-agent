"""Bundled devflow skill artifact — exposed so downstream agents can self-evolve.

The skill is loaded lazily from the on-disk artifact installed alongside the
package (project-root `skills/africa-oracle-devflow.md` at build time).
"""

from __future__ import annotations

from importlib.resources import files
from functools import lru_cache


@lru_cache(maxsize=1)
def devflow_skill() -> str:
    """Return the latest distilled DevFlow skill text (Markdown)."""
    return (files("africa_oracle") / "_skill.md").read_text(encoding="utf-8")
