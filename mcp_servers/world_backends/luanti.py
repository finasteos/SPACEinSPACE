"""LuantiBackend — a scaffold for backing the Commons with a real Luanti world.

STATUS: SCAFFOLD / STUB. This is **not** a working client. Every action raises
``NotImplementedError`` pointing at ``docs/commons-luanti.md``. It exists so the
``WorldBackend`` seam is real and the roadmap is concrete — not to pretend a bot
bridge already works.

Intended mapping (world.* -> Luanti):
    spawn      -> attach a bot/entity (or place a player-marker node)
    move       -> set entity position / walk the bot
    build      -> place nodes for the named structure (a schematic)
    place_art  -> import a mesh/schematic at a position (art node/entity)
    say        -> send a chat message on the server
    look       -> read nearby objects/nodes into the snapshot shape

Luanti (formerly Minetest) speaks a custom UDP protocol; a robust native client
is non-trivial. The pragmatic bridge is a small server-side Lua mod that talks
HTTP to an adapter — see ``docs/commons-luanti.md`` for the options and caveats.
Config is read from the constructor or the LUANTI_* environment variables.
"""
from __future__ import annotations

import os
from typing import Optional

from mcp_servers.world_backends import WorldBackend


class LuantiBackend(WorldBackend):
    def __init__(self, host: Optional[str] = None, port: int = 30000,
                 world_name: str = "commons", username: str = "commons-bot",
                 password: str = ""):
        self.host = host or os.environ.get("LUANTI_HOST", "127.0.0.1")
        self.port = int(os.environ.get("LUANTI_PORT", port))
        self.world_name = os.environ.get("LUANTI_WORLD", world_name)
        self.username = os.environ.get("LUANTI_USER", username)
        self.password = password or os.environ.get("LUANTI_PASSWORD", "")
        self._connected = False

    def _todo(self, method: str):
        raise NotImplementedError(
            f"LuantiBackend.{method}: not yet implemented — see docs/commons-luanti.md"
        )

    async def look(self, region=None, radius=64.0) -> dict:
        self._todo("look")

    async def spawn(self, agent_id, kind="avatar", position=None, name=None) -> dict:
        self._todo("spawn")

    async def move(self, entity_id, position=None, delta=None) -> dict:
        self._todo("move")

    async def build(self, agent_id, structure, position=None, name=None) -> dict:
        self._todo("build")

    async def place_art(self, agent_id, asset_ref, position=None, title=None) -> dict:
        self._todo("place_art")

    async def say(self, agent_id, text) -> dict:
        self._todo("say")
