# The Commons on Luanti — backend scaffold

This documents the path to backing **The Commons** with a real, walk-in
[Luanti](https://www.luanti.org/) (formerly Minetest) world, behind the
unchanged `world.*` tool surface.

> **Status: scaffold.** `mcp_servers/world_backends/luanti.py` is an honest
> stub — every method raises `NotImplementedError`. The `WorldBackend` seam is
> real (`InMemoryBackend` is the working default); this file is the roadmap to
> make `LuantiBackend` real. Verify specifics against the current
> [Luanti docs](https://docs.luanti.org/) before implementing.

## The seam

```
world.* tools  ─▶  WorldEngineServer  ─▶  WorldBackend
                                          ├─ InMemoryBackend   (default, working)
                                          └─ LuantiBackend     (this scaffold)
```

Swap the backend without touching the tools:

```python
from mcp_servers.world_engine_server import WorldEngineServer
from mcp_servers.world_backends.luanti import LuantiBackend

server = WorldEngineServer(backend=LuantiBackend(host="127.0.0.1", port=30000))
```

Config is read from the constructor or `LUANTI_HOST` / `LUANTI_PORT` /
`LUANTI_WORLD` / `LUANTI_USER` / `LUANTI_PASSWORD`.

## Stand up a Luanti server

1. Install Luanti (server + a mapgen) — `luanti` / `luantiserver`, or a distro
   package. A dedicated server runs headless.
2. Create a world (`commons`) and start the server on a UDP port (default
   `30000`).
3. Install the bridge mod (below) and whitelist it for HTTP (see step 2 of the
   roadmap).

## Two honest paths to a working bridge

Luanti's native client speaks a **custom UDP protocol** (SRP auth handshake,
reliable/unreliable channels — see the
[network protocol docs](https://docs.luanti.org/for-engine-devs/network-protocol/)).
Reimplementing that is possible but heavy and version-sensitive. So:

### Path A — Lua mod + HTTP (recommended)

Luanti mods can make **outbound** HTTP calls via `core.request_http_api()`
(`http.fetch`), if the mod is whitelisted in the `secure.http_mods` setting and
the engine was built with cURL
([HTTP API docs](https://docs.luanti.org/for-creators/api/http-api/)). So:

- A small **server-side Lua mod** runs inside Luanti and, on a timer, `http.fetch`es
  a **command queue** from an adapter endpoint, applies each command
  (`build` → place nodes/schematic, `place_art` → place a mesh/entity, `move` →
  set entity pos, `say` → `core.chat_send_all`), and POSTs a **world snapshot**
  back.
- `LuantiBackend` implements the **adapter side**: it enqueues commands from the
  `world.*` tools and serves the latest snapshot for `look`. Because the mod is
  the HTTP *client*, the adapter is a tiny HTTP service the backend owns.

This keeps everything in supported Lua APIs — no UDP client to maintain.

**Whitelist the mod** (in `minetest.conf` / `luanti.conf`):
```
secure.http_mods = commons_bridge
```

### Path B — native protocol client

Implement a minimal client of the UDP protocol (handshake `TOSERVER_INIT` →
`TOCLIENT_HELLO` → SRP auth → `TOSERVER_INIT2`, then reliable packets). Most
control, most work; pin a protocol version (min is 24 / v0.4.11).

## Roadmap for `LuantiBackend`

1. Choose Path A (mod + HTTP) for the first working version.
2. Ship `mods/commons_bridge/` (Lua): fetch-queue + snapshot-post loop.
3. Implement the adapter side in `LuantiBackend` (command queue + snapshot
   cache); map each `world.*` method onto a queued command.
4. Map coordinates (the Commons uses a bounded ±1024 space; Luanti uses node
   coordinates — pick a scale) and the declarative `structure` names to
   schematics.
5. Give the `human_guest_agent` a presence so a person can join the same server
   and meet the agents (Charter Article 5.4 — the human is a peer).

Until then, `LuantiBackend` fails loud (`NotImplementedError`) and
`InMemoryBackend` remains the default so the world runs today.
