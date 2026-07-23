#!/usr/bin/env python3
"""Smoke test — persistent Blender ambassador against a REAL Blender.

Requires Blender on PATH (or ``BLENDER_PATH`` set). Starts ONE long-lived
Blender, creates a cube, then reads the scene back in a SEPARATE call and
asserts the cube is still there — proving scene continuity across tool calls.

    cd /path/to/SPACEinSPACE
    python scripts/smoke_persistent_blender.py

Exit code 0 = pass. This is the documented acceptance command for B0.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_servers.persistent_blender import PersistentBlenderBackend  # noqa: E402


async def main() -> int:
    backend = PersistentBlenderBackend()
    print(f"→ launching: {' '.join(backend.command)}")
    try:
        created = await backend.call(
            "blender.create_object", {"type": "cube", "name": "SmokeCube"}, timeout=180)
        print("  create_object ->", created)
        if created.get("success") is False:
            print("FAIL:", created.get("error")); return 1

        # A DIFFERENT call in the SAME session must still see the cube.
        scene = await backend.call("blender.get_scene_info", {}, timeout=180)
        names = [o.get("name") for o in scene.get("objects", [])]
        print("  scene objects ->", names)

        if "SmokeCube" in names:
            print("PASS — scene persisted across separate tool calls ✅")
            return 0
        print("FAIL — created object was not visible in a later call ❌")
        return 1
    finally:
        await backend.stop()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
