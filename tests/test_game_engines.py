"""Tests for Unity / Godot ambassadors (in-memory backend)."""
import pytest

from mcp_servers.unity_mcp_server import UnityMCPServer
from mcp_servers.godot_mcp_server import GodotMCPServer
from mcp_servers.game_backends import InMemoryGameBackend, ALLOWED_PRIMITIVES


@pytest.fixture
def unity():
    return UnityMCPServer(backend=InMemoryGameBackend(engine="unity"))


@pytest.fixture
def godot():
    return GodotMCPServer(backend=InMemoryGameBackend(engine="godot"))


@pytest.mark.asyncio
async def test_unity_create_and_list(unity):
    created = await unity.handle_request({
        "id": "1",
        "name": "unity.create_gameobject",
        "arguments": {"name": "Hero", "primitive": "capsule", "position": [0, 1, 0]},
    })
    assert created["success"] is True
    assert created["result"]["success"] is True

    info = await unity.handle_request({
        "id": "2", "name": "unity.get_scene_info", "arguments": {},
    })
    assert info["success"] is True
    names = [o["name"] for o in info["result"]["objects"]]
    assert "Hero" in names


@pytest.mark.asyncio
async def test_unity_rejects_bad_primitive(unity):
    bad = await unity.handle_request({
        "id": "3",
        "name": "unity.create_gameobject",
        "arguments": {"name": "X", "primitive": "dragon"},
    })
    assert bad["success"] is True  # MCP call ok
    assert bad["result"]["success"] is False
    assert "allowlisted" in bad["result"]["error"]


@pytest.mark.asyncio
async def test_unity_transform_and_component(unity):
    await unity.handle_request({
        "id": "a", "name": "unity.create_gameobject",
        "arguments": {"name": "Cube", "primitive": "cube"},
    })
    moved = await unity.handle_request({
        "id": "b", "name": "unity.set_transform",
        "arguments": {"name": "Cube", "position": [1, 2, 3]},
    })
    assert moved["result"]["object"]["position"] == [1.0, 2.0, 3.0]

    comp = await unity.handle_request({
        "id": "c", "name": "unity.add_component",
        "arguments": {"name": "Cube", "component": "Rigidbody"},
    })
    assert "Rigidbody" in comp["result"]["object"]["components"]


@pytest.mark.asyncio
async def test_godot_create_node(godot):
    r = await godot.handle_request({
        "id": "1",
        "name": "godot.create_node",
        "arguments": {"name": "Player", "primitive": "capsule"},
    })
    assert r["result"]["success"] is True
    state = await godot.handle_request({
        "id": "2", "name": "godot.get_editor_state", "arguments": {},
    })
    assert state["result"]["engine"] == "godot"
    assert state["result"]["object_count"] == 1


@pytest.mark.asyncio
async def test_tools_registered():
    u = UnityMCPServer()
    g = GodotMCPServer()
    assert "unity.create_gameobject" in u.tools
    assert "godot.create_node" in g.tools
    # every unity tool has a registry entry
    from tools.registry import TOOL_DEFINITIONS
    for name in u.tools:
        assert name in TOOL_DEFINITIONS, f"missing ToolDef for {name}"
    for name in g.tools:
        assert name in TOOL_DEFINITIONS, f"missing ToolDef for {name}"


def test_allowed_primitives_nonempty():
    assert "cube" in ALLOWED_PRIMITIVES
    assert "capsule" in ALLOWED_PRIMITIVES
