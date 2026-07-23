"""Path guard for serving blender-jobs assets over the web (B2).

The guest gallery fetches exported models + screenshots. This confines any
web-served asset path to ``blender-jobs/{exports,screenshots}`` and rejects
traversal — the same "rejected, not negotiated" stance as Charter Article 4.4.
Kept separate from ``serve.py`` so it's importable/testable without Supabase.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

BLENDER_JOBS = (Path(__file__).resolve().parent.parent / "blender-jobs").resolve()
ALLOWED_ASSET_DIRS = ("exports", "screenshots")


def safe_blender_asset(subpath: str) -> Optional[Path]:
    """Resolve ``subpath`` under blender-jobs/, allowing only ``exports/`` and
    ``screenshots/`` and only real files. Returns the Path, or None if rejected.
    """
    if not isinstance(subpath, str) or not subpath or "\x00" in subpath:
        return None
    resolved = (BLENDER_JOBS / subpath).resolve()
    try:
        rel = resolved.relative_to(BLENDER_JOBS)
    except ValueError:
        return None  # escaped blender-jobs/
    if not rel.parts or rel.parts[0] not in ALLOWED_ASSET_DIRS:
        return None
    return resolved if resolved.is_file() else None
