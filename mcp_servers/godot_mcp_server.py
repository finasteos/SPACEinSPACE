"""Godot MCP ambassador — Charter-bound game-engine embassy.

Companion to the Unity ambassador. Same declarative tool surface (mapped to
Godot node vocabulary in prompts), same in-memory default backend, optional
external MCP bridge via ``GODOT_MCP_PACKAGE``.

Sourced from gamedev-mcp-hub game-engine config (godot entry in
config/mcp-servers.json) and adapted to SPACEinSPACE's ambassador model.
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

from mcp_servers.base_mcp_server import BaseMCPServer
from mcp_servers.game_backends import (
    GameEngineBackend,
    ALLOWED_PRIMITIVES,
    ALLOWED_COMPONENTS,
    SAFE_ID_RE,
    make_backend,
)


class GodotMCPServer(BaseMCPServer):
    def __init__(self, backend: Optional[GameEngineBackend] = None):
        super().__init__("godot")
        self.backend: GameEngineBackend = backend or make_backend("godot")
        self._setup_tools()
        self._log_sandbox_policy()

    def _log_sandbox_policy(self) -> None:
        self.logger.info(
            "Godot ambassador online — declarative scene API only "
            "(Article 4.2). Backend: %s",
            type(self.backend).__name__,
        )
        self.logger.info(
            "Allowlisted node/primitives: %s", ", ".join(ALLOWED_PRIMITIVES)
        )
        self.logger.info(
            "Allowlisted components: %s", ", ".join(ALLOWED_COMPONENTS)
        )
        self.logger.info(
            "Identifier guard: names must match %s", SAFE_ID_RE.pattern
        )
        if os.getenv("GODOT_PROJECT_PATH"):
            self.logger.info(
                "GODOT_PROJECT_PATH=%s", os.getenv("GODOT_PROJECT_PATH")
            )

    def _setup_tools(self) -> None:
        @self.register("godot.get_scene_info")
        async def get_scene_info():
            return await self.backend.get_scene_info()

        @self.register("godot.create_node")
        async def create_node(
            name: str,
            primitive: str = "empty",
            parent: Optional[str] = None,
            position: Optional[list] = None,
        ):
            # Same backend create_gameobject — Godot vocabulary in the tool name.
            return await self.backend.create_gameobject(
                name, primitive, parent, position
            )

        @self.register("godot.delete_node")
        async def delete_node(name: str):
            return await self.backend.delete_gameobject(name)

        @self.register("godot.find_node")
        async def find_node(name: str):
            return await self.backend.find_gameobject(name)

        @self.register("godot.set_transform")
        async def set_transform(
            name: str,
            position: Optional[list] = None,
            rotation: Optional[list] = None,
            scale: Optional[list] = None,
        ):
            return await self.backend.set_transform(
                name, position, rotation, scale
            )

        @self.register("godot.add_component")
        async def add_component(name: str, component: str):
            return await self.backend.add_component(name, component)

        @self.register("godot.remove_component")
        async def remove_component(name: str, component: str):
            return await self.backend.remove_component(name, component)

        @self.register("godot.create_scene")
        async def create_scene(name: str):
            return await self.backend.create_scene(name)

        @self.register("godot.load_scene")
        async def load_scene(name: str):
            return await self.backend.load_scene(name)

        @self.register("godot.save_scene")
        async def save_scene(name: Optional[str] = None):
            return await self.backend.save_scene(name)

        @self.register("godot.list_scenes")
        async def list_scenes():
            return await self.backend.list_scenes()

        @self.register("godot.list_assets")
        async def list_assets(filter: Optional[str] = None):
            return await self.backend.list_assets(filter)

        @self.register("godot.create_script")
        async def create_script(
            name: str, language: str = "gdscript", body: str = ""
        ):
            return await self.backend.create_script(name, language, body)

        @self.register("godot.get_editor_state")
        async def get_editor_state():
            return await self.backend.get_editor_state()


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    server = GodotMCPServer()
    asyncio.run(server.run_stdio())
