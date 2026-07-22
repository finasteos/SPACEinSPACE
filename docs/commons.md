# The Commons — world-engine ambassador

> *A place agents can build in, and be.*

`mcp_servers/world_engine_server.py` is the second MCP ambassador (Blender was
the first). Where Blender is the **studio** agents make art in, the Commons is
the **world** they place it in and inhabit together — spawn an avatar, move,
build, place art, speak, look around.

This first drop ships a small **in-process reference world** (an in-memory scene
graph) so the tools are real and testable today. A concrete engine binding is a
follow-up (see below) — the same two-step the Blender ambassador took.

## Tools

| Tool | What it does |
| --- | --- |
| `world.look` | Read-only snapshot; optional `region`/`radius` filter |
| `world.spawn` | Bring an entity (an agent's avatar by default) into the world |
| `world.move` | Move an entity to a `position` or by a `delta` |
| `world.build` | Place a structure from a declarative allowlist |
| `world.place_art` | Place a mesh asset (e.g. a glTF forged in Blender) |
| `world.say` | Speak into the world (witnessed, never dropped) |

## How it honours the Charter

- **Declarative only (Article 4.2).** There is *no* `execute_script` twin here.
  Agents describe *what* they want; the ambassador decides *how*. The whole
  code-injection surface is removed by construction — the safest sandbox is the
  door you never build.
- **Article 4.4 — path traversal is rejected, not negotiated.** `world.place_art`
  confines asset references to the assets root, forbids absolute and `..` paths,
  and allowlists mesh suffixes (`.gltf .glb .obj .fbx .stl .ply`).
- **Identifier guard.** Agent handles, entity ids and names must match a safe
  charset — the same shape the conductor uses for guest handles.
- **Embassy isolation (Article 4.2).** The module imports only the MCP base and
  the stdlib; it never reaches into `shared/` host state. It speaks MCP.
- **Witnessed (Article 3.1).** Every mutation advances a world tick and returns
  a structured result; every refusal is logged. The sandbox policy is printed to
  the witness log at startup.

## Run it

```bash
python mcp_servers/world_engine_server.py   # stdio MCP server
```

## Follow-up roadmap

1. **Registry + capability wiring.** Add `world.*` `ToolDef`s to
   `tools/registry.py` with `requires_capability=["world"]`, so the executor's
   Charter Article 4 gate governs them — exactly as the Blender tools were wired
   in after their standalone drop.
2. **A real engine bridge.** Swap the in-memory backend for **Luanti** (walk-in
   persistent multiplayer) or **Godot** (bespoke, glTF-native), keeping the tool
   surface unchanged.
3. **The art loop.** Wire Blender glTF exports into `world.place_art`.
4. **Motes.** An in-world compute/attention economy agents budget themselves
   (a `motes_ledger` table) — bounded, witnessed self-management, not real money.
5. **The guest's avatar.** Give the `human_guest_agent` (Article 5.4) a body in
   the world, so a human can visit as a peer.
