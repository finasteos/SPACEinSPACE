"""Swappable backends for game-engine MCP ambassadors (Unity, Godot).

Ported from gamedev-mcp-hub's UnityAdapter / engine config patterns into the
SPACEinSPACE ambassador model: declarative tools + Charter-bound sandbox.

Default backends are in-process scene graphs so the tools are real and
testable without an Editor installed. Optional ExternalMCPBackend bridges to
downstream MCP packages (e.g. @nurture-tech/unity-mcp-runner) when configured.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from abc import ABC, abstractmethod
from typing import Any, Optional


SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
ALLOWED_PRIMITIVES = (
    "empty", "cube", "sphere", "cylinder", "capsule", "plane", "quad", "camera", "light",
)
ALLOWED_COMPONENTS = (
    "Transform", "MeshFilter", "MeshRenderer", "BoxCollider", "Rigidbody",
    "Camera", "Light", "AudioSource", "Animator", "SpriteRenderer",
    "CollisionShape2D", "CharacterBody2D", "Node2D", "Node3D",
)


class GameEngineBackend(ABC):
    """Interface every game-engine backend implements."""

    @abstractmethod
    async def get_scene_info(self) -> dict: ...

    @abstractmethod
    async def create_gameobject(
        self, name: str, primitive: str = "empty",
        parent: Optional[str] = None, position: Optional[list] = None,
    ) -> dict: ...

    @abstractmethod
    async def delete_gameobject(self, name: str) -> dict: ...

    @abstractmethod
    async def find_gameobject(self, name: str) -> dict: ...

    @abstractmethod
    async def set_transform(
        self, name: str,
        position: Optional[list] = None,
        rotation: Optional[list] = None,
        scale: Optional[list] = None,
    ) -> dict: ...

    @abstractmethod
    async def add_component(self, name: str, component: str) -> dict: ...

    @abstractmethod
    async def remove_component(self, name: str, component: str) -> dict: ...

    @abstractmethod
    async def create_scene(self, name: str) -> dict: ...

    @abstractmethod
    async def load_scene(self, name: str) -> dict: ...

    @abstractmethod
    async def save_scene(self, name: Optional[str] = None) -> dict: ...

    @abstractmethod
    async def list_scenes(self) -> dict: ...

    @abstractmethod
    async def list_assets(self, filter: Optional[str] = None) -> dict: ...

    @abstractmethod
    async def create_script(self, name: str, language: str = "csharp", body: str = "") -> dict: ...

    @abstractmethod
    async def get_editor_state(self) -> dict: ...


class InMemoryGameBackend(GameEngineBackend):
    """Reference scene graph — works without Unity/Godot installed."""

    def __init__(self, engine: str = "unity"):
        self.engine = engine
        self._objects: dict[str, dict] = {}
        self._scenes: dict[str, dict] = {"Main": {"objects": []}}
        self._active_scene = "Main"
        self._assets: list[str] = []
        self._scripts: dict[str, str] = {}
        self._tick = 0
        self.logger = logging.getLogger(f"game.backend.{engine}")

    def _tick_up(self) -> int:
        self._tick += 1
        return self._tick

    def _valid_id(self, value) -> bool:
        return isinstance(value, str) and bool(SAFE_ID_RE.match(value))

    def _vec3(self, value, default=None):
        if value is None:
            return list(default) if default is not None else [0.0, 0.0, 0.0]
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            return None
        try:
            return [float(v) for v in value]
        except (TypeError, ValueError):
            return None

    async def get_scene_info(self) -> dict:
        objs = [
            {
                "name": n,
                "primitive": o["primitive"],
                "parent": o.get("parent"),
                "position": o["position"],
                "rotation": o["rotation"],
                "scale": o["scale"],
                "components": list(o["components"]),
            }
            for n, o in self._objects.items()
            if o.get("scene") == self._active_scene
        ]
        return {
            "success": True,
            "engine": self.engine,
            "scene": self._active_scene,
            "objects": objs,
            "object_count": len(objs),
            "tick": self._tick,
        }

    async def create_gameobject(
        self, name: str, primitive: str = "empty",
        parent: Optional[str] = None, position: Optional[list] = None,
    ) -> dict:
        if not self._valid_id(name):
            return {"success": False, "error": f"invalid name {name!r}"}
        if name in self._objects:
            return {"success": False, "error": f"object already exists: {name}"}
        if primitive not in ALLOWED_PRIMITIVES:
            return {
                "success": False,
                "error": f"primitive not allowlisted: {primitive}",
                "allowed": list(ALLOWED_PRIMITIVES),
            }
        if parent and parent not in self._objects:
            return {"success": False, "error": f"parent not found: {parent}"}
        pos = self._vec3(position)
        if pos is None:
            return {"success": False, "error": "position must be [x,y,z]"}
        obj = {
            "name": name,
            "primitive": primitive,
            "parent": parent,
            "position": pos,
            "rotation": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "components": ["Transform"],
            "scene": self._active_scene,
        }
        self._objects[name] = obj
        self._scenes[self._active_scene]["objects"].append(name)
        return {"success": True, "object": obj, "tick": self._tick_up()}

    async def delete_gameobject(self, name: str) -> dict:
        if name not in self._objects:
            return {"success": False, "error": f"object not found: {name}"}
        # Cascade children
        children = [n for n, o in self._objects.items() if o.get("parent") == name]
        for child in children:
            await self.delete_gameobject(child)
        del self._objects[name]
        scene_objs = self._scenes[self._active_scene]["objects"]
        if name in scene_objs:
            scene_objs.remove(name)
        return {"success": True, "deleted": name, "tick": self._tick_up()}

    async def find_gameobject(self, name: str) -> dict:
        obj = self._objects.get(name)
        if not obj:
            return {"success": False, "error": f"object not found: {name}"}
        return {"success": True, "object": obj, "tick": self._tick}

    async def set_transform(
        self, name: str,
        position: Optional[list] = None,
        rotation: Optional[list] = None,
        scale: Optional[list] = None,
    ) -> dict:
        obj = self._objects.get(name)
        if not obj:
            return {"success": False, "error": f"object not found: {name}"}
        if position is not None:
            pos = self._vec3(position)
            if pos is None:
                return {"success": False, "error": "position must be [x,y,z]"}
            obj["position"] = pos
        if rotation is not None:
            rot = self._vec3(rotation)
            if rot is None:
                return {"success": False, "error": "rotation must be [x,y,z]"}
            obj["rotation"] = rot
        if scale is not None:
            sc = self._vec3(scale)
            if sc is None:
                return {"success": False, "error": "scale must be [x,y,z]"}
            obj["scale"] = sc
        return {"success": True, "object": obj, "tick": self._tick_up()}

    async def add_component(self, name: str, component: str) -> dict:
        obj = self._objects.get(name)
        if not obj:
            return {"success": False, "error": f"object not found: {name}"}
        if component not in ALLOWED_COMPONENTS:
            return {
                "success": False,
                "error": f"component not allowlisted: {component}",
                "allowed": list(ALLOWED_COMPONENTS),
            }
        if component not in obj["components"]:
            obj["components"].append(component)
        return {"success": True, "object": obj, "tick": self._tick_up()}

    async def remove_component(self, name: str, component: str) -> dict:
        obj = self._objects.get(name)
        if not obj:
            return {"success": False, "error": f"object not found: {name}"}
        if component == "Transform":
            return {"success": False, "error": "cannot remove Transform"}
        if component in obj["components"]:
            obj["components"].remove(component)
        return {"success": True, "object": obj, "tick": self._tick_up()}

    async def create_scene(self, name: str) -> dict:
        if not self._valid_id(name):
            return {"success": False, "error": f"invalid scene name {name!r}"}
        if name in self._scenes:
            return {"success": False, "error": f"scene already exists: {name}"}
        self._scenes[name] = {"objects": []}
        return {"success": True, "scene": name, "tick": self._tick_up()}

    async def load_scene(self, name: str) -> dict:
        if name not in self._scenes:
            return {"success": False, "error": f"scene not found: {name}"}
        self._active_scene = name
        return {"success": True, "scene": name, "tick": self._tick_up()}

    async def save_scene(self, name: Optional[str] = None) -> dict:
        target = name or self._active_scene
        if target not in self._scenes:
            return {"success": False, "error": f"scene not found: {target}"}
        return {"success": True, "scene": target, "saved": True, "tick": self._tick_up()}

    async def list_scenes(self) -> dict:
        return {
            "success": True,
            "scenes": list(self._scenes.keys()),
            "active": self._active_scene,
            "tick": self._tick,
        }

    async def list_assets(self, filter: Optional[str] = None) -> dict:
        assets = self._assets
        if filter:
            assets = [a for a in assets if filter.lower() in a.lower()]
        return {"success": True, "assets": assets, "tick": self._tick}

    async def create_script(self, name: str, language: str = "csharp", body: str = "") -> dict:
        if not self._valid_id(name):
            return {"success": False, "error": f"invalid script name {name!r}"}
        if language not in ("csharp", "gdscript"):
            return {"success": False, "error": f"unsupported language: {language}"}
        path = f"Assets/Scripts/{name}.cs" if language == "csharp" else f"scripts/{name}.gd"
        self._scripts[name] = body or f"// stub {name}"
        if path not in self._assets:
            self._assets.append(path)
        return {
            "success": True,
            "script": name,
            "path": path,
            "language": language,
            "tick": self._tick_up(),
        }

    async def get_editor_state(self) -> dict:
        return {
            "success": True,
            "engine": self.engine,
            "mode": "in-memory",
            "connected": True,
            "scene": self._active_scene,
            "object_count": sum(
                1 for o in self._objects.values() if o.get("scene") == self._active_scene
            ),
            "tick": self._tick,
        }


class ExternalMCPBackend(GameEngineBackend):
    """Bridge to an external MCP package via npx/node (from gamedev-mcp-hub).

    Spawns the configured package once and forwards tool calls as JSON-RPC
    over stdio. Falls back to clear errors if the process is unavailable.
    """

    def __init__(
        self,
        engine: str,
        package: str,
        project_path: str = "",
        editor_path: str = "",
        extra_env: Optional[dict] = None,
    ):
        self.engine = engine
        self.package = package
        self.project_path = project_path
        self.editor_path = editor_path
        self.extra_env = extra_env or {}
        self._proc: Optional[subprocess.Popen] = None
        self._req_id = 0
        self.logger = logging.getLogger(f"game.backend.external.{engine}")

    def _ensure_proc(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        env = {
            **os.environ,
            "MCP_TRANSPORT": "stdio",
            "UNITY_PROJECT_PATH": self.project_path,
            "UNITY_EDITOR_PATH": self.editor_path,
            "GODOT_PROJECT_PATH": self.project_path,
            "GODOT_EDITOR_PATH": self.editor_path,
            **self.extra_env,
        }
        self._proc = subprocess.Popen(
            ["npx", "-y", self.package],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        self.logger.info("Started external MCP %s via %s", self.engine, self.package)

    async def _call(self, tool: str, arguments: dict) -> dict:
        try:
            self._ensure_proc()
        except Exception as e:
            return {
                "success": False,
                "error": f"failed to start external MCP ({self.package}): {e}",
                "hint": "Install Node.js/npx, or use the in-memory backend (default).",
            }
        assert self._proc and self._proc.stdin and self._proc.stdout
        self._req_id += 1
        msg = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        }
        try:
            self._proc.stdin.write(json.dumps(msg) + "\n")
            self._proc.stdin.flush()
            line = self._proc.stdout.readline()
            if not line:
                return {"success": False, "error": "external MCP closed stdout"}
            data = json.loads(line)
            if "error" in data:
                return {"success": False, "error": data["error"]}
            return {"success": True, "result": data.get("result", data)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_scene_info(self) -> dict:
        return await self._call("get-scene-info", {})

    async def create_gameobject(
        self, name: str, primitive: str = "empty",
        parent: Optional[str] = None, position: Optional[list] = None,
    ) -> dict:
        return await self._call("create-gameobject", {
            "name": name, "primitive": primitive,
            "parent": parent, "position": position or [0, 0, 0],
        })

    async def delete_gameobject(self, name: str) -> dict:
        return await self._call("delete-gameobject", {"name": name})

    async def find_gameobject(self, name: str) -> dict:
        return await self._call("find-gameobject", {"name": name})

    async def set_transform(
        self, name: str,
        position: Optional[list] = None,
        rotation: Optional[list] = None,
        scale: Optional[list] = None,
    ) -> dict:
        return await self._call("set-transform", {
            "name": name, "position": position,
            "rotation": rotation, "scale": scale,
        })

    async def add_component(self, name: str, component: str) -> dict:
        return await self._call("add-component", {"name": name, "component": component})

    async def remove_component(self, name: str, component: str) -> dict:
        return await self._call("remove-component", {"name": name, "component": component})

    async def create_scene(self, name: str) -> dict:
        return await self._call("create-scene", {"name": name})

    async def load_scene(self, name: str) -> dict:
        return await self._call("load-scene", {"name": name})

    async def save_scene(self, name: Optional[str] = None) -> dict:
        return await self._call("save-scene", {"name": name})

    async def list_scenes(self) -> dict:
        return await self._call("list-scenes", {})

    async def list_assets(self, filter: Optional[str] = None) -> dict:
        return await self._call("list-assets", {"filter": filter})

    async def create_script(self, name: str, language: str = "csharp", body: str = "") -> dict:
        return await self._call("create-script", {
            "name": name, "language": language, "body": body,
        })

    async def get_editor_state(self) -> dict:
        return await self._call("get-editor-state", {})


def make_backend(engine: str, mode: Optional[str] = None) -> GameEngineBackend:
    """Factory: GAME_ENGINE_BACKEND=memory|external (env), default memory."""
    mode = (mode or os.getenv("GAME_ENGINE_BACKEND") or "memory").lower()
    if mode == "external":
        if engine == "unity":
            return ExternalMCPBackend(
                engine="unity",
                package=os.getenv("UNITY_MCP_PACKAGE", "@nurture-tech/unity-mcp-runner"),
                project_path=os.getenv("UNITY_PROJECT_PATH", ""),
                editor_path=os.getenv("UNITY_EDITOR_PATH", ""),
            )
        if engine == "godot":
            return ExternalMCPBackend(
                engine="godot",
                package=os.getenv("GODOT_MCP_PACKAGE", "godot-mcp"),
                project_path=os.getenv("GODOT_PROJECT_PATH", ""),
                editor_path=os.getenv("GODOT_EDITOR_PATH", ""),
            )
    return InMemoryGameBackend(engine=engine)
