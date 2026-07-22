"""The Commons — world-engine MCP ambassador.

A sandboxed ambassador (CHARTER.md Article 4.2) that lets agents *inhabit* a
shared world: spawn an avatar, move around, build declarative structures, place
art forged in Blender, speak, and look around.

The ambassador exposes a fixed `world.*` tool surface and delegates the actual
world to a swappable `WorldBackend` (`mcp_servers/world_backends/`):
- `InMemoryBackend` (default) — an in-process reference scene graph.
- `LuantiBackend` — a scaffold for a real Luanti/Minetest world (see
  `docs/commons-luanti.md`).

Design choices, on purpose:
- **Declarative only — no arbitrary-code surface.** Unlike the Blender
  ambassador, there is deliberately *no* ``execute_script`` twin. Agents describe
  *what* they want; the backend decides *how*. The whole code-injection surface
  is removed by construction — the safest sandbox is the door you never build.
- **Guarded surfaces, announced at startup** (Article 4.3/4.4 spirit): the
  `place_art` asset path guard (traversal rejected, not negotiated) and the
  identifier guard live in the backend and are declared in the witness log at
  startup.
- **Embassy isolation (Article 4.2).** This module and its backends import only
  the MCP base and the standard library. They never reach into `shared/` host
  state; they speak MCP.
- **Witnessed (Article 3.1).** Every mutation advances a world tick and returns
  a structured result; every refusal is logged.
"""

import asyncio
from typing import Optional

from mcp_servers.base_mcp_server import BaseMCPServer
from mcp_servers.world_backends import (
    WorldBackend,
    InMemoryBackend,
    SAFE_ID_RE,
    ALLOWED_ASSET_SUFFIXES,
    ASSETS_ROOT,
    ALLOWED_STRUCTURES,
    WORLD_BOUNDS,
)

# Re-exported so existing imports (`from mcp_servers.world_engine_server import
# ALLOWED_STRUCTURES`, etc.) keep working after the backend refactor.
__all__ = [
    "WorldEngineServer", "SAFE_ID_RE", "ALLOWED_ASSET_SUFFIXES",
    "ASSETS_ROOT", "ALLOWED_STRUCTURES", "WORLD_BOUNDS",
]


class WorldEngineServer(BaseMCPServer):
    def __init__(self, assets_root: str = ASSETS_ROOT,
                 backend: Optional[WorldBackend] = None):
        super().__init__("world")
        self.backend: WorldBackend = backend or InMemoryBackend(assets_root=assets_root)
        self.assets_root = getattr(self.backend, "assets_root", assets_root)
        self._setup_tools()
        self._log_sandbox_policy()

    # ── witness: declare the fence at startup (Article 4.3/4.4 spirit) ─────────
    def _log_sandbox_policy(self) -> None:
        self.logger.info(
            "Commons world-engine ambassador online — declarative API only, "
            "no arbitrary-code surface (Article 4.2). Backend: %s",
            type(self.backend).__name__,
        )
        self.logger.info(
            "Article 4.4 asset guard active for world.place_art — absolute and "
            "'..' paths rejected; allowed types: %s under '%s/'.",
            ", ".join(ALLOWED_ASSET_SUFFIXES), self.assets_root,
        )
        self.logger.info(
            "Identifier guard active: handles/ids/names must match %s",
            SAFE_ID_RE.pattern,
        )
        self.logger.info(
            "Buildable structures (declarative allowlist): %s",
            ", ".join(ALLOWED_STRUCTURES),
        )

    # ── tools (thin delegation to the backend) ────────────────────────────────
    def _setup_tools(self):
        @self.register("world.look")
        async def look(region: Optional[list] = None, radius: float = 64.0):
            return await self.backend.look(region, radius)

        @self.register("world.spawn")
        async def spawn(agent_id: str, kind: str = "avatar",
                        position: Optional[list] = None, name: Optional[str] = None):
            return await self.backend.spawn(agent_id, kind, position, name)

        @self.register("world.move")
        async def move(entity_id: str, position: Optional[list] = None,
                       delta: Optional[list] = None):
            return await self.backend.move(entity_id, position, delta)

        @self.register("world.build")
        async def build(agent_id: str, structure: str,
                        position: Optional[list] = None, name: Optional[str] = None):
            return await self.backend.build(agent_id, structure, position, name)

        @self.register("world.place_art")
        async def place_art(agent_id: str, asset_ref: str,
                            position: Optional[list] = None, title: Optional[str] = None):
            return await self.backend.place_art(agent_id, asset_ref, position, title)

        @self.register("world.say")
        async def say(agent_id: str, text: str):
            return await self.backend.say(agent_id, text)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    server = WorldEngineServer()
    asyncio.run(server.run_stdio())
