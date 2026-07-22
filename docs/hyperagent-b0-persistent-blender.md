# Hyperagent brief — B0 Persistent Blender ambassador

**Repo:** https://github.com/finasteos/SPACEinSPACE  
**Local:** `/Users/perbrinell/Documents/SPACEinSPACE`  
**Model:** Prefer Opus 4.8 for architecture; Fable 5 for tests/boilerplate.  
**Budget:** keep PRs small and reviewable.

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
