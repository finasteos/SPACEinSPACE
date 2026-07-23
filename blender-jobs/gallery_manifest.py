#!/usr/bin/env python3
"""Build a JSON manifest of finished blender-jobs for the guest gallery (B2).

Scans ``blender-jobs/exports/*.glb`` (produced by B1), pairs each with its
prompt (from the done job file) and screenshot, and emits a manifest that the
guest UI (``ui/guest.html``) renders as ``<model-viewer>`` cards.

    python blender-jobs/gallery_manifest.py     # writes blender-jobs/gallery.json
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build_manifest(root: Path = ROOT) -> list:
    """Return a list of {name, prompt, glb, screenshot} for each exported glb."""
    jobs = root / "blender-jobs"
    exports = sorted((jobs / "exports").glob("*.glb"))
    done = jobs / "queue" / "done"
    shots = jobs / "screenshots"
    manifest = []
    for glb in exports:
        stem = glb.stem
        prompt = stem
        md = done / f"{stem}.md"
        if md.exists():
            first = md.read_text().strip().split("\n", 1)[0].strip()
            if first:
                prompt = first
        shot = shots / f"{stem}.png"
        manifest.append({
            "name": stem,
            "prompt": prompt,
            "glb": f"/blender-jobs/exports/{glb.name}",
            "screenshot": f"/blender-jobs/screenshots/{shot.name}" if shot.exists() else None,
        })
    return manifest


def write_manifest(root: Path = ROOT) -> Path:
    out = root / "blender-jobs" / "gallery.json"
    out.write_text(json.dumps(build_manifest(root), indent=2))
    return out


if __name__ == "__main__":
    path = write_manifest()
    print(f"wrote {path} ({len(json.loads(path.read_text()))} entries)")
