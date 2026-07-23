"""B2 snapshot endpoint — live Commons world helpers.

Tests the pieces behind GET /api/commons and POST /api/commons/join at the
module level (no HTTP/Supabase needed).
"""
import pytest

from mcp_servers.world_backends import InMemoryBackend
from shared.commons_presence import (
    world_snapshot, seed_demo_world, join_as_guest, present_guests,
)


class TestLiveCommons:
    @pytest.mark.asyncio
    async def test_seed_then_snapshot_shape(self):
        b = InMemoryBackend()
        await seed_demo_world(b)
        snap = await world_snapshot(b)
        assert "success" not in snap            # public shape only
        assert snap["entity_count"] >= 2        # seeded avatars
        assert snap["recent_says"]              # welcome line
        assert all("kind" in e for e in snap["entities"])

    @pytest.mark.asyncio
    async def test_guest_join_appears_in_snapshot(self):
        b = InMemoryBackend()
        await seed_demo_world(b)
        res = await join_as_guest(b, "aria")
        assert res["success"] is True
        snap = await world_snapshot(b)
        assert "aria" in [g["id"] for g in present_guests(snap)]

    @pytest.mark.asyncio
    async def test_join_bad_handle_refused(self):
        b = InMemoryBackend()
        res = await join_as_guest(b, "bad handle!")
        assert res["success"] is False and res["field"] == "handle"
