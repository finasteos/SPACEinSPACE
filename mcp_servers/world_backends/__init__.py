"""Swappable world backends for the Commons world-engine ambassador.

The ambassador (`mcp_servers/world_engine_server.py`) exposes a fixed `world.*`
tool surface and delegates the actual world to a `WorldBackend`. This keeps the
tool contract stable while the world itself can be an in-process reference
(`InMemoryBackend`, the default) or, later, a real engine (see `luanti.py`).

Design invariants (Charter):
- Declarative only (Article 4.2): backends receive structured params, never code.
- Article 4.4: `place_art` asset refs are path-traversal guarded, not negotiated.
- Identifiers validated against a safe charset.

Constants live here and are re-exported by `world_engine_server` for backwards
compatibility.
"""
from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Optional


SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,48}$")
ALLOWED_ASSET_SUFFIXES = (".gltf", ".glb", ".obj", ".fbx", ".stl", ".ply")
ASSETS_ROOT = "assets"
ALLOWED_STRUCTURES = (
    "cube", "platform", "pillar", "wall", "stairs",
    "ramp", "arch", "sphere", "torus", "tree", "beacon",
)
WORLD_BOUNDS = 1024.0


class WorldBackend(ABC):
    """Interface every Commons world backend implements.

    Each method returns a JSON-serialisable dict. On success:
    ``{"success": True, "tick": int, ...}``; on refusal:
    ``{"success": False, "error": str, ...}``.
    """

    @abstractmethod
    async def look(self, region: Optional[list] = None, radius: float = 64.0) -> dict: ...

    @abstractmethod
    async def spawn(self, agent_id: str, kind: str = "avatar",
                    position: Optional[list] = None, name: Optional[str] = None) -> dict: ...

    @abstractmethod
    async def move(self, entity_id: str, position: Optional[list] = None,
                   delta: Optional[list] = None) -> dict: ...

    @abstractmethod
    async def build(self, agent_id: str, structure: str,
                    position: Optional[list] = None, name: Optional[str] = None) -> dict: ...

    @abstractmethod
    async def place_art(self, agent_id: str, asset_ref: str,
                        position: Optional[list] = None, title: Optional[str] = None) -> dict: ...

    @abstractmethod
    async def say(self, agent_id: str, text: str) -> dict: ...


class InMemoryBackend(WorldBackend):
    """The default reference world — a small in-process scene graph.

    This is the exact behaviour the ambassador shipped with; it is the ground
    truth the world.* tools are tested against.
    """

    def __init__(self, assets_root: str = ASSETS_ROOT):
        self.assets_root = assets_root
        self._entities: dict = {}
        self._say_log: list = []
        self._tick = 0
        self._seq = 0
        self.logger = logging.getLogger("world.backend.memory")

    # ── guards ──────────────────────────────────────────────────────────────
    def _valid_id(self, value) -> bool:
        return isinstance(value, str) and bool(SAFE_ID_RE.match(value))

    def _safe_asset(self, ref) -> Optional[str]:
        if not isinstance(ref, str) or not ref.strip():
            return None
        ref = ref.strip()
        if ref.startswith(("/", "~")) or os.path.isabs(ref) or "\\" in ref:
            return None
        root = os.path.normpath(self.assets_root)
        candidate = os.path.normpath(os.path.join(root, ref))
        if candidate != root and not candidate.startswith(root + os.sep):
            return None
        if os.path.splitext(candidate)[1].lower() not in ALLOWED_ASSET_SUFFIXES:
            return None
        return candidate

    def _clamp_pos(self, pos) -> Optional[list]:
        if not isinstance(pos, (list, tuple)) or len(pos) != 3:
            return None
        try:
            p = [float(pos[0]), float(pos[1]), float(pos[2])]
        except (TypeError, ValueError):
            return None
        if any(abs(c) > WORLD_BOUNDS for c in p):
            return None
        return p

    def _refuse(self, reason: str, field: Optional[str] = None) -> dict:
        self.logger.warning("world refusal: %s (field=%s)", reason, field)
        return {"success": False, "error": reason, "field": field}

    def _refuse_charter(self, article: str, reason: str, field: Optional[str] = None) -> dict:
        self.logger.warning("Charter %s refusal: %s (field=%s)", article, reason, field)
        return {"success": False, "charter_article": article, "error": reason, "field": field}

    # ── actions (identical semantics to the original tools) ──────────────────
    async def look(self, region=None, radius=64.0) -> dict:
        ents = list(self._entities.values())
        center = self._clamp_pos(region) if region is not None else None
        if center is not None:
            cx, cy, cz = center

            def near(e):
                x, y, z = e["position"]
                return ((x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2) ** 0.5 <= radius

            ents = [e for e in ents if near(e)]
        return {"success": True, "tick": self._tick, "entity_count": len(ents),
                "entities": ents, "recent_says": self._say_log[-10:]}

    async def spawn(self, agent_id, kind="avatar", position=None, name=None) -> dict:
        if not self._valid_id(agent_id):
            return self._refuse("invalid agent_id", field="agent_id")
        if name is not None and not self._valid_id(name):
            return self._refuse("invalid name", field="name")
        if name is not None and name in self._entities:
            return self._refuse(f"id already exists: {name}", field="name")
        pos = self._clamp_pos(position if position is not None else [0, 0, 0])
        if pos is None:
            return self._refuse("position missing/out of bounds", field="position")
        self._seq += 1
        self._tick += 1
        eid = name or f"{kind}-{agent_id}-{self._seq}"
        if not self._valid_id(eid):
            eid = f"e{self._seq}"
        ent = {"id": eid, "kind": kind, "position": pos,
               "owner": agent_id, "created_tick": self._tick}
        self._entities[eid] = ent
        return {"success": True, "tick": self._tick, "entity": ent}

    async def move(self, entity_id, position=None, delta=None) -> dict:
        ent = self._entities.get(entity_id)
        if not ent:
            return self._refuse(f"unknown entity: {entity_id}", field="entity_id")
        if position is not None:
            target = position
        elif delta is not None and isinstance(delta, (list, tuple)) and len(delta) == 3:
            target = [ent["position"][i] + d for i, d in enumerate(delta)]
        else:
            return self._refuse("provide position or a 3-vector delta", field="position")
        clamped = self._clamp_pos(target)
        if clamped is None:
            return self._refuse("target out of bounds", field="position")
        self._tick += 1
        ent["position"] = clamped
        return {"success": True, "tick": self._tick, "entity": ent}

    async def build(self, agent_id, structure, position=None, name=None) -> dict:
        if not self._valid_id(agent_id):
            return self._refuse("invalid agent_id", field="agent_id")
        if structure not in ALLOWED_STRUCTURES:
            return self._refuse(
                f"unknown structure '{structure}'. Declarative only — allowed: "
                f"{', '.join(ALLOWED_STRUCTURES)}", field="structure")
        if name is not None and not self._valid_id(name):
            return self._refuse("invalid name", field="name")
        if name is not None and name in self._entities:
            return self._refuse(f"id already exists: {name}", field="name")
        pos = self._clamp_pos(position if position is not None else [0, 0, 0])
        if pos is None:
            return self._refuse("position missing/out of bounds", field="position")
        self._seq += 1
        self._tick += 1
        eid = name or f"{structure}-{self._seq}"
        ent = {"id": eid, "kind": "structure", "structure": structure,
               "position": pos, "owner": agent_id, "created_tick": self._tick}
        self._entities[eid] = ent
        return {"success": True, "tick": self._tick, "entity": ent}

    async def place_art(self, agent_id, asset_ref, position=None, title=None) -> dict:
        if not self._valid_id(agent_id):
            return self._refuse("invalid agent_id", field="agent_id")
        safe = self._safe_asset(asset_ref)
        if safe is None:
            return self._refuse_charter(
                "4.4",
                f"asset_ref rejected: {asset_ref!r}. Path traversal is rejected, "
                f"not negotiated — no absolute or '..' paths; allowed types "
                f"{', '.join(ALLOWED_ASSET_SUFFIXES)} under '{self.assets_root}/'.",
                field="asset_ref")
        pos = self._clamp_pos(position if position is not None else [0, 0, 0])
        if pos is None:
            return self._refuse("position missing/out of bounds", field="position")
        self._seq += 1
        self._tick += 1
        eid = f"art-{self._seq}"
        ent = {"id": eid, "kind": "art", "asset": safe, "title": title or eid,
               "position": pos, "author": agent_id, "created_tick": self._tick}
        self._entities[eid] = ent
        return {"success": True, "tick": self._tick, "entity": ent}

    async def say(self, agent_id, text) -> dict:
        if not self._valid_id(agent_id):
            return self._refuse("invalid agent_id", field="agent_id")
        if not isinstance(text, str) or not text.strip():
            return self._refuse("empty message", field="text")
        self._tick += 1
        entry = {"agent_id": agent_id, "text": text.strip()[:2000], "tick": self._tick}
        self._say_log.append(entry)
        return {"success": True, "tick": self._tick, "said": entry}
