"""Commons presence for a visiting human guest (B2).

A human "visits" The Commons by taking a peer seat *in the world*: we spawn a
``guest`` entity through the world backend's ``world.spawn``. This is Charter
Article 5.4 (the human is a peer, not a controller) made spatial.

We speak only the declarative world.* surface (Article 4.2 embassy isolation) —
no host reach-in. The backend is any ``WorldBackend`` (mcp_servers.world_backends):
the InMemoryBackend in tests, the world-engine ambassador in production.
"""
from __future__ import annotations

from typing import Optional

from mcp_servers.world_backends import SAFE_ID_RE


async def join_as_guest(backend, handle: str, position: Optional[list] = None) -> dict:
    """Spawn a ``guest`` entity for ``handle``. Returns the spawn result dict.

    The handle is validated against the world's safe-id charset before it can
    mint a peer seat (mirrors the conductor's guest-handle guard). A repeated
    handle is refused by ``world.spawn`` (id already exists) — no double-join.
    """
    if not (isinstance(handle, str) and SAFE_ID_RE.match(handle)):
        return {"success": False, "error": f"invalid guest handle: {handle!r}", "field": "handle"}
    return await backend.spawn(agent_id=handle, kind="guest", position=position, name=handle)


def present_guests(snapshot: dict) -> list:
    """Filter a world snapshot (from ``world.look``) to its guest entities."""
    return [e for e in (snapshot or {}).get("entities", []) if e.get("kind") == "guest"]


async def world_snapshot(backend) -> dict:
    """Return the public Commons snapshot for GET /api/commons.

    The shape (tick, entity_count, entities, recent_says) is exactly what
    ui/guest.html consumes; the internal ``success`` flag is dropped.
    """
    snap = await backend.look()
    snap.pop("success", None)
    return snap


async def seed_demo_world(backend) -> None:
    """Give the guest view a small, non-empty starting Commons."""
    await backend.spawn(agent_id="explorer", kind="avatar", position=[0, 0, 0])
    await backend.spawn(agent_id="curator", kind="avatar", position=[220, -140, 0])
    await backend.say(agent_id="curator", text="welcome to The Commons.")
