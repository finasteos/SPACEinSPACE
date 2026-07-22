"""Tests for the swappable world-backend seam.

Confirms the ambassador defaults to InMemoryBackend and still works through
delegation, that a custom backend is honoured, and that the LuantiBackend stub
raises NotImplementedError (an honest scaffold, not a fake client). The existing
test_world_engine.py continues to exercise the full in-memory behaviour through
the ambassador, so this file focuses on the seam itself.
"""

import pytest

from mcp_servers.world_engine_server import WorldEngineServer
from mcp_servers.world_backends import WorldBackend, InMemoryBackend
from mcp_servers.world_backends.luanti import LuantiBackend


class TestDefaultBackend:
    def test_defaults_to_in_memory(self):
        assert isinstance(WorldEngineServer().backend, InMemoryBackend)

    @pytest.mark.asyncio
    async def test_spawn_delegates_to_backend(self):
        server = WorldEngineServer()
        result = await server.tools["world.spawn"](agent_id="explorer")
        assert result["success"] is True
        snapshot = await server.tools["world.look"]()
        assert snapshot["entity_count"] == 1

    def test_custom_backend_is_honoured(self):
        backend = InMemoryBackend(assets_root="assets")
        assert WorldEngineServer(backend=backend).backend is backend


class TestLuantiStub:
    def test_is_a_world_backend(self):
        assert issubclass(LuantiBackend, WorldBackend)

    def test_reads_config_from_env(self, monkeypatch):
        monkeypatch.setenv("LUANTI_HOST", "10.0.0.5")
        monkeypatch.setenv("LUANTI_PORT", "31337")
        backend = LuantiBackend()
        assert backend.host == "10.0.0.5"
        assert backend.port == 31337

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,args", [
        ("look", {}),
        ("spawn", {"agent_id": "x"}),
        ("move", {"entity_id": "x"}),
        ("build", {"agent_id": "x", "structure": "cube"}),
        ("place_art", {"agent_id": "x", "asset_ref": "assets/a.glb"}),
        ("say", {"agent_id": "x", "text": "hi"}),
    ])
    async def test_methods_raise_not_implemented(self, method, args):
        backend = LuantiBackend()
        with pytest.raises(NotImplementedError):
            await getattr(backend, method)(**args)
