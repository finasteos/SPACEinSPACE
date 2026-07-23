#!/usr/bin/env python3
"""Blender autonomous job worker — B1.

Pulls APPROVED jobs from ``blender-jobs/queue/approved/``, runs each through the
persistent Blender ambassador (B0) in one session, exports a **glTF**, saves a
render, and files the job to ``done/``/``failed/`` with a gallery entry.

Approve gate (human-in-the-loop): jobs land in ``pending/`` and DO NOT run until
a human approves them (``approve`` → moves to ``approved/``). Unattended launchd
runs (``run``) execute only what was approved — no surprise autonomous builds.

CLI::

    python blender-jobs/worker.py list                 # show pending + approved
    python blender-jobs/worker.py add "<prompt>"       # queue a pending job
    python blender-jobs/worker.py refill               # seed pending from seed-ideas
    python blender-jobs/worker.py approve <slug|all>   # pending -> approved
    python blender-jobs/worker.py run [--limit N]      # run approved via the B0 ambassador

Execution goes through ``mcp_servers.persistent_blender.create_blender_ambassador``
(B0) — one long-lived Blender, so scene-setup → build → export → render all share
the same scene. Templates run through the sandboxed ``blender.execute_script``.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

JOBS = ROOT / "blender-jobs"
QUEUE = JOBS / "queue"
PENDING = QUEUE / "pending"
APPROVED = QUEUE / "approved"
ACTIVE = QUEUE / "active"
DONE = QUEUE / "done"
FAILED = QUEUE / "failed"
SCREENSHOTS = JOBS / "screenshots"
EXPORTS = JOBS / "exports"
GALLERY = JOBS / "gallery.md"
TEMPLATES_DIR = JOBS / "templates"

CONFIG = json.loads((JOBS / "config.json").read_text())

for _d in (PENDING, APPROVED, ACTIVE, DONE, FAILED, SCREENSHOTS, EXPORTS):
    _d.mkdir(parents=True, exist_ok=True)


# ── ambassador (B0) ─────────────────────────────────────────────────────────
def _ambassador():
    from mcp_servers.persistent_blender import create_blender_ambassador
    return create_blender_ambassador()


def _ok(result) -> bool:
    return isinstance(result, dict) and result.get("success", True) and not result.get("error")


# ── scene + templates ───────────────────────────────────────────────────────
def scene_setup_code() -> str:
    """Runs before every job: clean scene, render engine, lights, camera."""
    return """
import bpy
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for mat in list(bpy.data.materials):
    bpy.data.materials.remove(mat)
bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.render.resolution_x = 1920
bpy.context.scene.render.resolution_y = 1080
bpy.ops.object.light_add(type='SUN', location=(10, -10, 15))
bpy.ops.object.light_add(type='AREA', location=(-5, 5, 8))
bpy.data.objects['Area'].data.energy = 200
bpy.ops.object.camera_add(location=(8, -8, 6))
cam = bpy.context.active_object
cam.rotation_euler = (1.1, 0, 0.8)
bpy.context.scene.camera = cam
print('{"status": "ok"}')
"""


TEMPLATE_MAP = [
    (["forest", "campfire", "tent"], "forest_campfire.py"),
    (["cabin", "fireplace", "cozy", "interior", "bookshelf"], "cabin_interior.py"),
    (["chess", "marble", "obsidian", "board", "pawn"], "chessboard.py"),
    (["zen", "garden", "bonsai", "sand", "rock"], "zen_garden.py"),
    (["floating", "island", "waterfall", "ancient"], "floating_island.py"),
]


def build_prompt_code(prompt: str) -> str:
    """Match a prompt to a template and return executable bpy code."""
    low = prompt.lower()
    for keywords, template_file in TEMPLATE_MAP:
        if any(k in low for k in keywords):
            tmpl = TEMPLATES_DIR / template_file
            if tmpl.exists():
                code = tmpl.read_text()
                if "import bpy" not in code:
                    code = "import bpy, math, random\n" + code
                return code
    return (
        "import bpy, math, random\n"
        "bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 1))\n"
        "cube = bpy.context.active_object\n"
        "mat = bpy.data.materials.new('Default')\n"
        "mat.use_nodes = True\n"
        "mat.node_tree.nodes['Principled BSDF'].inputs[0].default_value = (0.2, 0.4, 0.8, 1)\n"
        "cube.data.materials.append(mat)\n"
    )


# ── queue helpers ───────────────────────────────────────────────────────────
def parse_job(filepath: Path) -> dict:
    text = filepath.read_text()
    prompt = text.strip().split("\n")[0] if text.strip() else ""
    return {"prompt": prompt, "full_text": text, "filepath": filepath}


def create_job_file(prompt: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = "".join(c if c.isalnum() or c in " -_" else "" for c in prompt.lower())[:40]
    slug = slug.strip().replace(" ", "-")
    fp = PENDING / f"{ts}_{slug}.md"
    fp.write_text(f"{prompt}\n\n---\nCreated: {datetime.now().isoformat()}\n")
    print(f"queued (pending): {fp.stem}")
    return fp


def refill_queue() -> int:
    """Seed pending jobs from seed-ideas.md when the pending queue runs low."""
    if len(list(PENDING.glob("*.md"))) >= CONFIG.get("min_pending_for_refill", 2):
        return 0
    seed = ROOT / CONFIG.get("seed_file", "blender-jobs/seed-ideas.md")
    if not seed.exists():
        return 0
    used = {d.read_text().split("\n")[0].strip() for d in DONE.glob("*.md")}
    added = 0
    for line in seed.read_text().splitlines():
        line = line.strip()
        if line.startswith("- "):
            idea = line[2:].strip()
            if idea and idea not in used:
                create_job_file(idea)
                added += 1
                if added >= 3:
                    break
    return added


# ── approve gate ─────────────────────────────────────────────────────────────
def _matches(fp: Path, selector: str) -> bool:
    return selector == "all" or selector.lower() in fp.name.lower()


def cmd_approve(selector: str) -> int:
    moved = 0
    for fp in sorted(PENDING.glob("*.md")):
        if _matches(fp, selector):
            shutil.move(str(fp), str(APPROVED / fp.name))
            print(f"approved: {fp.stem}")
            moved += 1
    if not moved:
        print(f"no pending job matched {selector!r}")
    return moved


def cmd_list() -> None:
    for label, d in (("pending", PENDING), ("approved", APPROVED),
                     ("done", DONE), ("failed", FAILED)):
        files = sorted(d.glob("*.md"))
        print(f"{label} ({len(files)})" + (":" if files else ""))
        for f in files[:20]:
            print(f"  {f.stem}")
    print("\nApprove a job to let `run` execute it: "
          "python blender-jobs/worker.py approve <slug|all>")


# ── run (async, via the B0 persistent ambassador) ───────────────────────────
def _fail(active: Path, msg: str) -> bool:
    print(f"FAILED: {msg}")
    shutil.move(str(active), str(FAILED / active.name))
    return False


async def run_job(amb, job: dict) -> bool:
    name = job["filepath"].stem
    print(f"\n--- running (approved): {job['prompt']} ---")
    active = ACTIVE / job["filepath"].name
    shutil.move(str(job["filepath"]), str(active))

    execute_script = amb.tools["blender.execute_script"]

    r = await execute_script(script=scene_setup_code())
    if not _ok(r):
        return _fail(active, f"scene setup: {r}")

    r = await execute_script(script=build_prompt_code(job["prompt"]))
    if not _ok(r):
        return _fail(active, f"build: {r}")

    # glTF export (the B1 deliverable) — one session, so the scene we just built.
    glb = EXPORTS / f"{name}.glb"
    exp = await amb.tools["blender.export_gltf"](filepath=str(glb))
    gltf_ok = _ok(exp)
    if not gltf_ok:
        print(f"glTF export warning: {exp}")

    # Render a still for the gallery (best-effort; not fatal).
    png = SCREENSHOTS / f"{name}.png"
    try:
        await amb.tools["blender.render"](output_path=str(png))
    except Exception as e:  # noqa: BLE001
        print(f"render warning: {e}")

    shutil.move(str(active), str(DONE / job["filepath"].name))
    append_gallery(job, glb if gltf_ok else None, png)
    print(f"done: {job['prompt']}  (glTF={'ok' if gltf_ok else 'skipped'})")
    return True


async def run_approved(amb=None, limit=None) -> int:
    """Run approved jobs through the ambassador. Returns count succeeded."""
    own = amb is None
    amb = amb or _ambassador()
    limit = limit or CONFIG.get("max_jobs_per_run", 3)
    approved = sorted(APPROVED.glob("*.md"))[:limit]
    if not approved:
        print("no approved jobs — approve some first "
              "(python blender-jobs/worker.py approve <slug|all>)")
        return 0
    ran = 0
    try:
        for fp in approved:
            if await run_job(amb, parse_job(fp)):
                ran += 1
    finally:
        if own and hasattr(amb, "stop"):
            try:
                await amb.stop()
            except Exception:
                pass
    print(f"\n=== ran {ran}/{len(approved)} approved job(s) ===")
    return ran


def append_gallery(job: dict, glb: Path | None, png: Path) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"- **{job['prompt']}**  ", f"  *Completed {ts}*  "]
    if glb is not None:
        try:
            rel = glb.relative_to(ROOT)
        except ValueError:
            rel = glb
        lines.append(f"  glTF: `{rel}`  ")
    lines.append(f"  ![screenshot](../blender-jobs/screenshots/{png.name})\n")
    if not GALLERY.exists():
        GALLERY.write_text("# Blender Gallery\n\nAutonomously generated scenes.\n\n")
    with open(GALLERY, "a") as f:
        f.write("\n".join(lines) + "\n")


# ── CLI ──────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="Blender autonomous job worker (B1)")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list", help="show the queue")
    p_add = sub.add_parser("add", help="queue a pending job")
    p_add.add_argument("prompt")
    sub.add_parser("refill", help="seed pending jobs from seed-ideas.md")
    p_ap = sub.add_parser("approve", help="move pending -> approved")
    p_ap.add_argument("selector", help="slug substring, or 'all'")
    p_run = sub.add_parser("run", help="run approved jobs via the B0 ambassador")
    p_run.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if args.cmd == "add":
        create_job_file(args.prompt)
    elif args.cmd == "refill":
        print(f"seeded {refill_queue()} pending job(s)")
    elif args.cmd == "approve":
        cmd_approve(args.selector)
    elif args.cmd == "run":
        asyncio.run(run_approved(limit=args.limit))
    else:
        # Default: status only. NEVER auto-runs — the approve gate is the point.
        cmd_list()


if __name__ == "__main__":
    main()
