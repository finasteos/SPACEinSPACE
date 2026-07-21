"""AgentWorld — den värld agenterna lever i.

Innehåller:
  - AgentTimeline (tick-baserad tid)
  - GoalQueue (vad agenterna vill uppnå)
  - BlenderStateMirror (agenternas bild av Blender)
  - AgentMemory (deras gemensamma minne)

Världen tickar oavsett om människan tittar.
"""

from __future__ import annotations

import asyncio
from typing import Optional, List, Dict, Any, Set
from datetime import datetime, timezone
from uuid import uuid4

from shared.agent_timeline import AgentTimeline, Tickable, TimelineEvent, HumanInputPolicy


# ─── Goal Queue ────────────────────────────────────────────────────

class Goal:
    """Ett mål som agenterna jobbar mot.

    Mål kan komma från människan, från Planner, eller från agenternas
    egen initiativförmåga.
    """

    def __init__(
        self,
        description: str,
        goal_type: str = "human_request",
        priority: int = 3,
        human_policy: HumanInputPolicy = HumanInputPolicy.ADVISORY,
        human_deadline_seconds: int = 300,
        parent_goal_id: Optional[str] = None,
    ):
        self.id = str(uuid4())[:12]
        self.description = description
        self.goal_type = goal_type
        self.priority = priority
        self.human_policy = human_policy
        self.human_deadline_seconds = human_deadline_seconds
        self.parent_goal_id = parent_goal_id
        self.created_at = datetime.now(timezone.utc)
        self.completed_at: Optional[datetime] = None
        self.sub_goals: List[Goal] = []
        self.status: str = "pending"  # pending, active, completed, failed, rolled_back

    def short(self) -> str:
        return f"[{self.status}] {self.description[:60]}"


class GoalQueue:
    """Prioriterad kö med mål.

    Planner lägger in mål. Agenter plockar mål och jobbar.
    Människan kan omprioritera, lägga till, eller ta bort.
    """

    def __init__(self):
        self._goals: List[Goal] = []
        self._active: Optional[Goal] = None

    def add(self, goal: Goal):
        self._goals.append(goal)
        self._goals.sort(key=lambda g: g.priority)  # lägre tal = högre prio

    def next(self) -> Optional[Goal]:
        """Hämta nästa mål att jobba på."""
        if self._active and self._active.status == "active":
            return self._active
        pending = [g for g in self._goals if g.status == "pending"]
        if not pending:
            return None
        self._active = pending[0]
        self._active.status = "active"
        return self._active

    def complete(self, goal_id: str):
        for g in self._goals:
            if g.id == goal_id:
                g.status = "completed"
                g.completed_at = datetime.now(timezone.utc)
                if self._active and self._active.id == goal_id:
                    self._active = None
                break

    def fail(self, goal_id: str, reason: str = ""):
        for g in self._goals:
            if g.id == goal_id:
                g.status = "failed"
                if self._active and self._active.id == goal_id:
                    self._active = None
                break

    def rollback(self, goal_id: str):
        for g in self._goals:
            if g.id == goal_id:
                g.status = "rolled_back"
                if self._active and self._active.id == goal_id:
                    self._active = None
                break

    def list_active(self) -> List[Goal]:
        return [g for g in self._goals if g.status in ("pending", "active")]

    def list_completed(self) -> List[Goal]:
        return [g for g in self._goals if g.status == "completed"]


# ─── Blender State Mirror ──────────────────────────────────────────

class BlenderStateMirror:
    """Agenternas bild av Blender — cached, inte nödvändigtvis perfekt.

    Agenter uppdaterar denna spegel när de gör operationer.
    Vid osäkerhet kan de hämta färsk data från Blender MCP.
    """

    def __init__(self):
        self.objects: Dict[str, Dict[str, Any]] = {}
        self.mode: str = "OBJECT"
        self.active_object: Optional[str] = None
        self.last_operation: Optional[str] = None
        self._dirty: bool = False

    def add_object(self, name: str, obj_type: str = "cube", location=None):
        self.objects[name] = {
            "type": obj_type,
            "location": location or [0, 0, 0],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._dirty = True

    def remove_object(self, name: str):
        self.objects.pop(name, None)
        self._dirty = True

    def modify_object(self, name: str, **changes):
        if name in self.objects:
            self.objects[name].update(changes)
            self._dirty = True

    def set_mode(self, mode: str):
        self.mode = mode

    def set_active(self, name: str):
        self.active_object = name
        self.mode = "EDIT" if name and name in self.objects else "OBJECT"

    def is_dirty(self) -> bool:
        return self._dirty

    def clean(self):
        self._dirty = False

    def snapshot(self) -> Dict[str, Any]:
        return {
            "objects": {n: o["type"] for n, o in self.objects.items()},
            "mode": self.mode,
            "active": self.active_object,
            "count": len(self.objects),
        }

    def summary(self) -> str:
        if not self.objects:
            return "Tom scen"
        by_type: Dict[str, int] = {}
        for o in self.objects.values():
            t = o["type"]
            by_type[t] = by_type.get(t, 0) + 1
        parts = [f"{count} {t}" for t, count in sorted(by_type.items())]
        return f"{', '.join(parts)} · mode: {self.mode}"


# ─── Agent Memory ─────────────────────────────────────────────────

class AgentMemory:
    """Agenternas gemensamma minne.

    Lagrar minnen som agenter kan hämta. Minnen har typer:
    - episodic: händelser (TTL 24h)
    - semantic: fakta (permanenta)
    - procedural: hur man gör
    """

    def __init__(self):
        self._memories: List[Dict[str, Any]] = []

    async def store(self, content: str, memory_type: str = "episodic",
                    agent_id: str = "unknown", ttl_hours: Optional[int] = None,
                    **kwargs) -> str:
        memory_id = str(uuid4())[:12]
        entry = {
            "id": memory_id,
            "content": content,
            "memory_type": memory_type,
            "agent_id": agent_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ttl_hours": ttl_hours,
            **kwargs,
        }
        self._memories.append(entry)
        # Rensa gamla om för många
        if len(self._memories) > 10000:
            self._memories = self._memories[-5000:]
        return memory_id

    async def query(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Enkel text-matchning (ersätts med vektorsökning när DB finns)."""
        query_lower = query.lower()
        matches = []
        for m in self._memories:
            if query_lower in m["content"].lower():
                matches.append(m)
                if len(matches) >= limit:
                    break
        return matches

    def summary(self) -> str:
        by_type: Dict[str, int] = {}
        for m in self._memories:
            t = m["memory_type"]
            by_type[t] = by_type.get(t, 0) + 1
        parts = [f"{count} {t}" for t, count in sorted(by_type.items())]
        return f"{len(self._memories)} minnen ({', '.join(parts)})" if parts else "Tomt minne"


# ─── Agent World ───────────────────────────────────────────────────

class AgentWorld:
    """Den värld agenterna lever i.

    Allt agenterna behöver finns här:
    - timeline (deras tid)
    - goals (vad de ska göra)
    - blender_state (deras bild av Blender)
    - memory (deras gemensamma minne)

    Människan är en gäst i denna värld.
    """

    def __init__(self, tick_interval_ms: float = 1.0):
        self.timeline = AgentTimeline(tick_interval_ms=tick_interval_ms)
        self.goals = GoalQueue()
        self.blender_state = BlenderStateMirror()
        self.memory = AgentMemory()
        # Charter Article 5.4 — the human role is a peer, not a
        # controller, and not a default character. Substrate is
        # avatar-agnostic: set human_avatar from conductor config or
        # leave None. No shipped default that names anyone.
        self.human_avatar: Optional[Dict[str, Any]] = None
        self._tasks: Set[asyncio.Task] = set()

    # ─── Goal management ─────────────────────────────────────

    def add_goal(self, description: str, goal_type: str = "human_request",
                 priority: int = 3,
                 human_policy: HumanInputPolicy = HumanInputPolicy.ADVISORY) -> Goal:
        goal = Goal(description, goal_type, priority, human_policy)
        self.goals.add(goal)
        self.timeline.log("world", "goal_added", {
            "goal_id": goal.id, "description": description[:80], "priority": priority
        })
        return goal

    def add_sub_goal(self, parent_id: str, description: str, **kwargs) -> Optional[Goal]:
        for g in self.goals._goals:
            if g.id == parent_id:
                sub = Goal(description, parent_goal_id=parent_id, **kwargs)
                g.sub_goals.append(sub)
                self.goals.add(sub)
                return sub
        return None

    def complete_goal(self, goal_id: str):
        self.goals.complete(goal_id)
        self.timeline.log("world", "goal_completed", {"goal_id": goal_id})

    def fail_goal(self, goal_id: str, reason: str = ""):
        self.goals.fail(goal_id, reason)
        self.timeline.log("world", "goal_failed", {"goal_id": goal_id, "reason": reason})

    # ─── World loop ─────────────────────────────────────────

    async def run(self):
        """Världen tickar för evigt."""
        timeline_task = asyncio.create_task(self.timeline.run())
        self._tasks.add(timeline_task)
        try:
            await asyncio.gather(timeline_task, return_exceptions=True)
        except asyncio.CancelledError:
            pass

    def stop(self):
        self.timeline.stop()
        for t in self._tasks:
            t.cancel()

    # ─── Human interface ────────────────────────────────────

    def human_view(self) -> str:
        """Vad människan ser när hon tittar in."""
        timeline_view = self.timeline.get_human_view()

        current_goal = self.goals.next()
        goal_line = (
            f"\n\n### 🎯 Nuvarande mål\n{current_goal.short()}"
            if current_goal else ""
        )

        # Substrate is avatar-agnostic. If the operator has set a
        # named guest avatar (via HumanGuestAgent instantiation or
        # conductor config), surface it; otherwise leave the slot quiet
        # so the project does not ship a default that names anyone.
        avatar_section = ""
        if self.human_avatar is not None:
            avatar_section = (
                f"\n\n### 🥊 Guest Avatar\n"
                f"  Namn: {self.human_avatar.get('name', 'unknown')} "
                f"({self.human_avatar.get('role', 'guest')})\n"
                f"  Beskrivning: {self.human_avatar.get('description', '').strip() or '—'}\n"
            )

        return (
            f"{avatar_section}"
            f"{timeline_view}"
            f"{goal_line}"
            f"\n\n### 🌍 Världen\n"
            f"  Blender: {self.blender_state.summary()}\n"
            f"  Minne: {self.memory.summary()}\n"
            f"  Mål i kö: {len(self.goals.list_active())}"
        )

    def human_detail(self, limit: int = 20) -> str:
        return self.timeline.get_human_detail(limit=limit)

    def pause(self):
        self.timeline.pause()

    def resume(self):
        self.timeline.resume()
