"""Tests for the Commons world-engine ambassador.

Covers the declarative world.* tools, the Article 4.4 asset-path guard, the
identifier guard, the no-arbitrary-code guarantee, and the startup policy log.
Mirrors the async-marker convention used across the existing suite.
"""

import logging

import pytest

from mcp_servers.world_engine_server import (
    WorldEngineServer,
    ALLOWED_STRUCTURES,
    ALLOWED_ASSET_SUFFIXES,
    WORLD_BOUNDS,
)


@pytest.fixture
def world():
    return WorldEngineServer()


def call(world, tool):
    return world.tools[tool]


class TestSpawnMoveLook:
    @pytest.mark.asyncio
    async def test_spawn_then_look_sees_it(self, world):
        res = await call(world, "world.spawn")(agent_id="planner", kind="avatar")
        assert res["success"] is True
        eid = res["entity"]["id"]
        snap = await call(world, "world.look")()
        assert snap["success"] is True
        assert snap["entity_count"] == 1
        assert any(e["id"] == eid for e in snap["entities"])

    @pytest.mark.asyncio
    async def test_move_by_position_and_delta(self, world):
        spawned = await call(world, "world.spawn")(agent_id="planner", name="scout", position=[0, 0, 0])
        assert spawned["success"] is True
        moved = await call(world, "world.move")(entity_id="scout", position=[3, 4, 0])
        assert moved["entity"]["position"] == [3.0, 4.0, 0.0]
        nudged = await call(world, "world.move")(entity_id="scout", delta=[1, -2, 0])
        assert nudged["entity"]["position"] == [4.0, 2.0, 0.0]

    @pytest.mark.asyncio
    async def test_move_unknown_entity_refused(self, world):
        res = await call(world, "world.move")(entity_id="ghost", position=[1, 1, 1])
        assert res["success"] is False
        assert res["field"] == "entity_id"

    @pytest.mark.asyncio
    async def test_out_of_bounds_refused(self, world):
        res = await call(world, "world.spawn")(agent_id="planner", position=[WORLD_BOUNDS + 1, 0, 0])
        assert res["success"] is False
        assert res["field"] == "position"

    @pytest.mark.asyncio
    async def test_look_radius_filters(self, world):
        await call(world, "world.spawn")(agent_id="a", name="near", position=[0, 0, 0])
        await call(world, "world.spawn")(agent_id="a", name="far", position=[500, 0, 0])
        snap = await call(world, "world.look")(region=[0, 0, 0], radius=10.0)
        ids = {e["id"] for e in snap["entities"]}
        assert "near" in ids and "far" not in ids


class TestBuildIsDeclarative:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("structure", list(ALLOWED_STRUCTURES))
    async def test_allowed_structures_build(self, world, structure):
        res = await call(world, "world.build")(agent_id="builder", structure=structure)
        assert res["success"] is True
        assert res["entity"]["structure"] == structure

    @pytest.mark.asyncio
    async def test_unknown_structure_refused(self, world):
        res = await call(world, "world.build")(agent_id="builder", structure="deathray")
        assert res["success"] is False
        assert res["field"] == "structure"

    def test_no_arbitrary_code_surface(self, world):
        """There must be no execute_script / eval twin on the world ambassador."""
        names = list(world.tools.keys())
        assert "world.execute_script" not in names
        assert not any(("exec" in n or "eval" in n or "script" in n) for n in names)


class TestPlaceArtPathGuard:
    @pytest.mark.asyncio
    async def test_valid_asset_is_placed(self, world):
        res = await call(world, "world.place_art")(
            agent_id="curator", asset_ref="gallery/monkey.glb", title="Suzanne")
        assert res["success"] is True
        assert res["entity"]["kind"] == "art"
        assert res["entity"]["asset"].endswith("monkey.glb")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [
        "/etc/passwd",
        "../secrets.gltf",
        "../../etc/shadow.glb",
        "~/secrets.obj",
        "assets/../../escape.glb",
        "note.txt",              # disallowed extension
        "model.exe",             # disallowed extension
    ])
    async def test_traversal_and_bad_types_refused(self, world, bad):
        res = await call(world, "world.place_art")(agent_id="curator", asset_ref=bad)
        assert res["success"] is False
        assert res["charter_article"] == "4.4"

    def test_allowed_suffixes_are_mesh_types(self, world):
        assert ".glb" in ALLOWED_ASSET_SUFFIXES and ".gltf" in ALLOWED_ASSET_SUFFIXES


class TestSayAndIdentifiers:
    @pytest.mark.asyncio
    async def test_say_is_recorded(self, world):
        res = await call(world, "world.say")(agent_id="planner", text="hello, commons")
        assert res["success"] is True
        snap = await call(world, "world.look")()
        assert snap["recent_says"][-1]["text"] == "hello, commons"

    @pytest.mark.asyncio
    async def test_empty_say_refused(self, world):
        res = await call(world, "world.say")(agent_id="planner", text="   ")
        assert res["success"] is False
        assert res["field"] == "text"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_id", ["", "has space", "semi;colon", "a" * 49, "rm -rf /"])
    async def test_invalid_agent_id_refused(self, world, bad_id):
        res = await call(world, "world.say")(agent_id=bad_id, text="hi")
        assert res["success"] is False
        assert res["field"] == "agent_id"


class TestStartupPolicyWitnessed:
    def test_policy_logged_at_startup(self, caplog):
        with caplog.at_level(logging.INFO, logger="mcp.world"):
            WorldEngineServer()
        text = " ".join(r.getMessage() for r in caplog.records)
        assert "declarative API only" in text
        assert "Article 4.4 asset guard" in text
