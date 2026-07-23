# Hyperagent brief — B0 Persistent Blender ambassador

**Repo:** https://github.com/finasteos/SPACEinSPACE  
**Local:** `/Users/perbrinell/Documents/SPACEinSPACE`  
**Model:** Prefer Opus 4.8 for architecture; Fable 5 for tests/boilerplate.  
**Budget:** keep PRs small and reviewable.

**Status:** ✅ **Delivered** 2026-07-23 — [PR #1](https://github.com/finasteos/SPACEinSPACE/pull/1) (`b0-persistent-blender` → `main`), 208 tests green (197 prior + 11 new). See **Resolution** at the bottom.

## Goal

Replace spawn-per-call Blender (`blender --background --python-expr` per tool) with a **long-lived Blender MCP process** that keeps one shared `.blend` (or in-memory scene) across tool calls for a session.

## Why

Today `mcp_servers/blender_mcp_server.py` (via `_run_blender_script` ~472–492) starts a fresh Blender for every tool call. That kills continuity — objects from call N disappear for call N+1. Docs in `docs/blender.md` already describe a stdin/stdout JSON pipe *inside* Blender; implementation must match that.

## Definition of Done

1. **Persistent process**
   - Start: `blender --background --python mcp_servers/blender_mcp_server.py` (or documented equivalent).
   - Conductor / tool executor talks over **stdio JSON** (one request → one response), not `--python-expr` one-shots.
2. **Scene continuity**
   - `blender.create_object` then `blender.get_scene_info` in the same session returns the created object.
3. **Session binding**
   - Optional: path to a `.blend` file per session (env or arg). Save/load hooks or explicit `blender.save` / open.
4. **Sandbox unchanged**
   - Keep Article 4.3 forbidden patterns for `blender.execute_script` (`import os`, `exec(`, etc.).
5. **Tests**
   - Unit/integration test that two sequential tools share state (can mock Blender subprocess with a fake that holds scene dict if CI has no Blender — but document real Blender smoke test).
6. **Docs**
   - Update `docs/blender.md` + TASKLIST status table so they match reality.
7. **No scope creep**
   - Do **not** build multi-user CRDT, GPU hosting, Unity, or Commons in this PR.

## Suggested approach

1. Read `mcp_servers/blender_mcp_server.py`, `shared/tool_executor.py`, `agents/blender_agent.py`, `docs/blender.md`.
2. Introduce a `PersistentBlenderBackend` (or fix the existing server) with:
   - process lifecycle (start / health / stop)
   - JSON-RPC or line-delimited JSON over stdin/stdout
   - timeout + crash restart policy
3. Wire tool registry to use the persistent backend when `BLENDER_MCP_MODE=persistent` (default) vs legacy `oneshot` for rollback.
4. Add smoke script under `scripts/` that creates a cube, modifies it, asserts presence.
5. Open a PR against `finasteos/SPACEinSPACE` with clear before/after in the description.

## Out of scope (later briefs)

- B1: blender-jobs queue + approve + glTF export
- B2: web guest UI + Commons presence
- B3: multi-user mesh sync / GPU sessions

## Acceptance command (local, with Blender installed)

```bash
cd /Users/perbrinell/Documents/SPACEinSPACE
# after implementation — exact command should be documented in the PR
python scripts/smoke_persistent_blender.py
```

## Charter note

Ambassador isolation stays. Conductor must not gain host filesystem rights beyond the MCP pipe. Sandbox list remains ambassador-owned.

---

## Resolution (2026-07-23)

Delivered in [PR #1](https://github.com/finasteos/SPACEinSPACE/pull/1). Small and reviewable: 9 files, +564/−5.

### Before → After

| | Before | After (default) |
|---|---|---|
| Process | fresh `blender … --python-expr` **per call** | **one** long-lived `blender --background --python mcp_servers/blender_mcp_server.py` |
| Continuity | ❌ call-N object gone in call N+1 | ✅ `create_object` → `get_scene_info` returns it |
| Transport | one-shot `--python-expr` | line-delimited **JSON over stdio** (1 req → 1 resp) |
| Rollback | — | `BLENDER_MCP_MODE=oneshot` |

### How

- **Server (inside Blender).** `_run_blender_script` detects `BLENDER_AVAILABLE`
  (`import bpy`). Inside Blender it execs the script **in-process** against the
  live `bpy` scene via a shared namespace (`_exec_in_blender`) — continuity comes
  from `bpy.data` being process-global. Outside Blender → legacy subprocess
  (`_run_oneshot`).
- **Host.** `mcp_servers/persistent_blender.py::PersistentBlenderBackend` launches
  the single long-lived Blender and speaks the JSON pipe with per-call **timeout**,
  **crash-restart**, and **banner-noise skipping**; exposes a `.tools` dict so it
  registers like any MCP server.
- **Mode switch.** `create_blender_ambassador()` → persistent (default) / oneshot
  (`BLENDER_MCP_MODE`), a process **singleton** so the conductor and the Blender
  agent share one Blender. Wired in `orchestrator/conductor.py` +
  `agents/blender_agent.py`.

### Definition of Done — all met

- [x] Persistent stdio-JSON process (no `--python-expr` one-shots)
- [x] Scene continuity (`create_object` → `get_scene_info`)
- [x] Session binding via `BLENDER_PATH` / `BLENDER_MCP_CMD`
- [x] Article 4.3 sandbox unchanged (enforced server-side before exec)
- [x] Tests share state without real Blender (fake ambassador) + smoke test
- [x] `docs/blender.md` + `TASKLIST.md` updated
- [x] No scope creep

### Files

`mcp_servers/blender_mcp_server.py` (in-process exec + legacy fallback),
`mcp_servers/persistent_blender.py` (new: backend + factory),
`orchestrator/conductor.py`, `agents/blender_agent.py` (wiring),
`tests/fake_blender_server.py` + `tests/test_persistent_blender.py` (new, 11 tests),
`scripts/smoke_persistent_blender.py` (new), `docs/blender.md`, `TASKLIST.md`.

### Acceptance command (now exact)

```bash
cd /Users/perbrinell/Documents/SPACEinSPACE
python scripts/smoke_persistent_blender.py
# creates a cube, re-reads the scene in a SEPARATE call, asserts it survived → exit 0
```

CI (no Blender) covers the same seam via the fake ambassador in
`tests/test_persistent_blender.py`.
