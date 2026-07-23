"""B0 — persistent Blender ambassador: continuity + seam tests.

Uses a fake Blender-side server (``tests/fake_blender_server.py``) that holds an
in-memory scene, so CI needs no real Blender. The real-Blender check lives in
``scripts/smoke_persistent_blender.py`` (documented, run locally).
"""
import sys
from pathlib import Path

import pytest

from mcp_servers.persistent_blender import (
    PersistentBlenderBackend,
    create_blender_ambassador,
)
from mcp_servers.blender_mcp_server import BlenderMCPServer

FAKE = str(Path(__file__).resolve().parent / "fake_blender_server.py")


def _backend() -> PersistentBlenderBackend:
    return PersistentBlenderBackend(command=[sys.executable, FAKE])


class TestSceneContinuity:
    @pytest.mark.asyncio
    async def test_create_then_get_scene_shares_state(self):
        """The whole point of B0: object from call N survives to call N+1."""
        backend = _backend()
        try:
            created = await backend.call(
                "blender.create_object", {"type": "cube", "name": "Cube"})
            assert created.get("name") == "Cube"
            scene = await backend.call("blender.get_scene_info", {})
            names = [o["name"] for o in scene["objects"]]
            assert "Cube" in names
        finally:
            await backend.stop()

    @pytest.mark.asyncio
    async def test_calls_accumulate_in_one_session(self):
        backend = _backend()
        try:
            await backend.call("blender.create_object", {"type": "cube", "name": "A"})
            await backend.call("blender.create_object", {"type": "sphere", "name": "B"})
            scene = await backend.call("blender.get_scene_info", {})
            assert scene["count"] == 2
        finally:
            await backend.stop()

    @pytest.mark.asyncio
    async def test_tools_dict_is_registerable_and_callable(self):
        """`.tools` mirrors an MCP server so register_mcp_server() works."""
        backend = _backend()
        try:
            assert "blender.create_object" in backend.tools
            res = await backend.tools["blender.create_object"](type="cube", name="Z")
            assert res["name"] == "Z"
        finally:
            await backend.stop()


class TestProtocolRobustness:
    @pytest.mark.asyncio
    async def test_skips_nonjson_banner(self):
        """The fake prints a banner line first; the first call still works."""
        backend = _backend()
        try:
            res = await backend.call("blender.get_scene_info", {})
            assert res["count"] == 0
        finally:
            await backend.stop()

    @pytest.mark.asyncio
    async def test_restart_after_process_dies(self):
        backend = _backend()
        try:
            await backend.call("blender.create_object", {"type": "cube", "name": "A"})
            assert backend.health()
            await backend.stop()
            assert not backend.health()
            # Next call transparently restarts the process (fresh scene).
            scene = await backend.call("blender.get_scene_info", {})
            assert backend.health()
            assert scene["count"] == 0
        finally:
            await backend.stop()


class TestFactoryModeSwitch:
    def test_default_mode_is_persistent(self, monkeypatch):
        monkeypatch.delenv("BLENDER_MCP_MODE", raising=False)
        assert isinstance(create_blender_ambassador(force=True), PersistentBlenderBackend)

    def test_oneshot_mode_returns_legacy_server(self, monkeypatch):
        monkeypatch.setenv("BLENDER_MCP_MODE", "oneshot")
        assert isinstance(create_blender_ambassador(force=True), BlenderMCPServer)

    def test_singleton_is_shared(self, monkeypatch):
        monkeypatch.delenv("BLENDER_MCP_MODE", raising=False)
        first = create_blender_ambassador(force=True)
        assert create_blender_ambassador() is first


class TestInProcessExecutor:
    """Server-side in-process path (_exec_in_blender) — the mechanism that gives
    continuity inside real Blender, exercised here without bpy."""

    def test_captures_printed_json(self):
        server = BlenderMCPServer()
        out = server._exec_in_blender(
            'import json\nprint(json.dumps({"objects": [], "mode": "OBJECT"}))')
        assert out["success"] is True
        assert out["mode"] == "OBJECT"

    def test_error_is_structured_not_fatal(self):
        server = BlenderMCPServer()
        out = server._exec_in_blender('raise RuntimeError("boom")')
        assert out["success"] is False
        assert "boom" in out["error"]

    def test_namespace_persists_across_calls(self):
        """Shared _script_globals persists state across execs — the CI-testable
        analog of bpy.data surviving between tool calls in one process."""
        server = BlenderMCPServer()
        server._exec_in_blender("counter = 41")
        out = server._exec_in_blender('import json\nprint(json.dumps({"n": counter + 1}))')
        assert out["n"] == 42
