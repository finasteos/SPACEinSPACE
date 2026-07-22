"""Unity MCP ambassador — Charter-bound game-engine embassy.

Ported from gamedev-mcp-hub's UnityAdapter tool surface into SPACEinSPACE's
ambassador pattern (see blender_mcp_server / world_engine_server).

Default backend is an in-process scene graph so agents can rehearse Unity
workflows without the Editor. Set ``GAME_ENGINE_BACKEND=external`` and
``UNITY_PROJECT_PATH`` to bridge to ``@nurture-tech/unity-mcp-runner``.

Design (Charter):
- Declarative only for scene ops (Article 4.2) — no arbitrary C# eval surface.
- Sandbox policy announced at startup (Article 4.3 spirit).
- Embassy isolation — imports only MCP base + game_backends, never shared/.
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


class UnityMCPServer(BaseMCPServer):
    def __init__(self, backend: Optional[GameEngineBackend] = None):
        super().__init__("unity")
        self.backend: GameEngineBackend = backend or make_backend("unity")
        self._setup_tools()
        self._log_sandbox_policy()

    def _log_sandbox_policy(self) -> None:
        self.logger.info(
            "Unity ambassador online — declarative scene API only "
            "(Article 4.2). Backend: %s",
            type(self.backend).__name__,
        )
        self.logger.info(
            "Allowlisted primitives: %s", ", ".join(ALLOWED_PRIMITIVES)
        )
        self.logger.info(
            "Allowlisted components: %s", ", ".join(ALLOWED_COMPONENTS)
        )
        self.logger.info(
            "Identifier guard: names must match %s", SAFE_ID_RE.pattern
        )
        if os.getenv("UNITY_PROJECT_PATH"):
            self.logger.info(
                "UNITY_PROJECT_PATH=%s", os.getenv("UNITY_PROJECT_PATH")
            )

    def _setup_tools(self) -> None:
        @self.register("unity.get_scene_info")
        async def get_scene_info():
            return await self.backend.get_scene_info()

        @self.register("unity.create_gameobject")
        async def create_gameobject(
            name: str,
            primitive: str = "empty",
            parent: Optional[str] = None,
            position: Optional[list] = None,
        ):
            return await self.backend.create_gameobject(
                name, primitive, parent, position
            )

        @self.register("unity.delete_gameobject")
        async def delete_gameobject(name: str):
            return await self.backend.delete_gameobject(name)

        @self.register("unity.find_gameobject")
        async def find_gameobject(name: str):
            return await self.backend.find_gameobject(name)

        @self.register("unity.set_transform")
        async def set_transform(
            name: str,
            position: Optional[list] = None,
            rotation: Optional[list] = None,
            scale: Optional[list] = None,
        ):
            return await self.backend.set_transform(
                name, position, rotation, scale
            )

        @self.register("unity.add_component")
        async def add_component(name: str, component: str):
            return await self.backend.add_component(name, component)

        @self.register("unity.remove_component")
        async def remove_component(name: str, component: str):
            return await self.backend.remove_component(name, component)

        @self.register("unity.create_scene")
        async def create_scene(name: str):
            return await self.backend.create_scene(name)

        @self.register("unity.load_scene")
        async def load_scene(name: str):
            return await self.backend.load_scene(name)

        @self.register("unity.save_scene")
        async def save_scene(name: Optional[str] = None):
            return await self.backend.save_scene(name)

        @self.register("unity.list_scenes")
        async def list_scenes():
            return await self.backend.list_scenes()

        @self.register("unity.list_assets")
        async def list_assets(filter: Optional[str] = None):
            return await self.backend.list_assets(filter)

        @self.register("unity.create_script")
        async def create_script(
            name: str, language: str = "csharp", body: str = ""
        ):
            return await self.backend.create_script(name, language, body)

        @self.register("unity.get_editor_state")
        async def get_editor_state():
            return await self.backend.get_editor_state()


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    server = UnityMCPServer()
    asyncio.run(server.run_stdio())
