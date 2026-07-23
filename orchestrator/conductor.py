"""Conductor — orchestrates the agent world.

The conductor no longer runs a message queue. Instead it:
  1. Creates an AgentWorld with timeline, goals, blender state, memory
  2. Registers agents as Tickable participants in the timeline
  3. Lets the world tick — agents act on their own schedule
  4. Human input becomes a Goal in the world, not a blocking gate

The world ticks regardless of human attention.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Dict, Optional, Tuple

from dotenv import load_dotenv

from shared.supabase_client import get_supabase, AgentDatabase
from shared.llm import QwenClient
from shared.world_state import AgentWorld, Goal
from shared.agent_timeline import AgentTimeline, HumanInputPolicy
from shared.a2a_protocol import A2ABus, A2AMessage
from shared.tool_executor import ToolExecutor
from shared.telemetry import telemetry

from agents.base_agent import BaseAgent
from agents.planner_agent import PlannerAgent
from agents.blender_agent import BlenderAgent
from agents.unity_agent import UnityAgent
from agents.godot_agent import GodotAgent
from agents.pixellab_agent import PixelLabAgent
from agents.meshy_agent import MeshyAgent
from agents.memory_agent import MemoryAgent
from agents.tool_agent import ToolAgent
from agents.review_agent import ReviewAgent
from agents.fallback_agent import FallbackAgent


# Charter Article 5.4 — guest-handle input contract.
# Reject any non-trivial input that could be used to mint a peer id
# with attacker-influenced routing. The reservation isn't perfect
# (a malicious peer can still spoof by emitting messages with
# crafted `from_agent` fields) but the regex blocks the simple
# abuse class of `/guest evil; rm -rf /`. The handle is also
# passed into `agent_id = f"guest-{handle}"` and a peer-id-shaped
# string with control characters would otherwise leak onto the
# bus and into the witness log (Charter 3.2).
GUEST_HANDLE_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


class Conductor:
    def __init__(self, tick_interval_ms: float = 10.0, use_tool_tuning: bool = True) -> None:
        load_dotenv(override=False)

        self.logger = logging.getLogger("conductor")
        self.db: AgentDatabase = get_supabase()
        self.llm = QwenClient()
        self.bus = A2ABus(db=self.db)

        # ─── The Agent World ────────────────────────────────
        self.world = AgentWorld(tick_interval_ms=tick_interval_ms)

        # ─── Tool executor ────────────────────────────────
        # Charter Article 4 (empirical at production runtime): the
        # executor's capability gate must be wired with a callable that
        # resolves `agent_id → declared capabilities`. We use a late-
        # bound lambda so we can populate `_agents_by_id` in
        # _setup_agents() before the callable is actually called.
        self._agents_by_id: Dict[str, BaseAgent] = {}
        self.tool_executor = ToolExecutor(
            db=self.db,
            agent_capabilities=lambda aid: self._resolve_capabilities(aid),
        )
        try:
            # B0 — persistent Blender by default (one long-lived process with
            # scene continuity). BLENDER_MCP_MODE=oneshot restores the legacy
            # spawn-per-call behaviour for rollback.
            from mcp_servers.persistent_blender import create_blender_ambassador
            bm = create_blender_ambassador()
            self.tool_executor.register_blender(bm)
        except Exception:
            self.logger.info("Blender MCP not loaded — blender.* tools unavailable")

        try:
            from mcp_servers.unity_mcp_server import UnityMCPServer
            self.tool_executor.register_mcp_server(UnityMCPServer())
        except Exception:
            self.logger.info("Unity MCP not loaded — unity.* tools unavailable")

        try:
            from mcp_servers.godot_mcp_server import GodotMCPServer
            self.tool_executor.register_mcp_server(GodotMCPServer())
        except Exception:
            self.logger.info("Godot MCP not loaded — godot.* tools unavailable")

        try:
            from mcp_servers.world_engine_server import WorldEngineServer
            self.tool_executor.register_mcp_server(WorldEngineServer())
        except Exception:
            self.logger.info("World MCP not loaded — world.* tools unavailable")

        try:
            from mcp_servers.pixellab_mcp_server import PixelLabMCPServer
            self.tool_executor.register_mcp_server(PixelLabMCPServer())
        except Exception:
            self.logger.info("PixelLab MCP not loaded — pixellab.* tools unavailable")

        try:
            from mcp_servers.meshy_mcp_server import MeshyMCPServer
            self.tool_executor.register_mcp_server(MeshyMCPServer())
        except Exception:
            self.logger.info("Meshy MCP not loaded — meshy.* tools unavailable")

        # ─── Tool Tuning ──────────────────────────────────
        self.tool_tuning = None
        if use_tool_tuning:
            try:
                from tools.stats import ToolTuning
                self.tool_tuning = ToolTuning(self.db)
            except Exception:
                self.logger.debug("ToolTuning not available")

        # ─── Agents ────────────────────────────────────────
        self.agents: Dict[str, BaseAgent] = {}
        self._setup_agents()

        self._stop = asyncio.Event()

    def _setup_agents(self) -> None:
        agent_classes = {
            "planner": PlannerAgent,
            "blender": BlenderAgent,
            "unity": UnityAgent,
            "godot": GodotAgent,
            "pixellab": PixelLabAgent,
            "meshy": MeshyAgent,
            "memory": MemoryAgent,
            "tool": ToolAgent,
            "review": ReviewAgent,
            "fallback": FallbackAgent,
        }
        for name, cls in agent_classes.items():
            instance = cls(db=self.db, bus=self.bus, llm_client=self.llm)
            instance.connect_world(self.world)
            self.world.timeline.register_agent(instance)
            self.agents[name] = instance
            # Charter Article 4: index by `agent_id` so the runtime
            # gate (`_resolve_capabilities`) resolves caller ids
            # correctly. Display name and agent_id may differ.
            self._agents_by_id[instance.agent_id] = instance

    def _resolve_capabilities(self, agent_id: str) -> Tuple[str, ...]:
        """Charter Article 4: callable wired into ToolExecutor.

        Fail-closed semantics: if `agent_id` is not in the conductor's
        registry, raise KeyError. The executor's gate translates that
        into a Charter Article 4 Violation string for the witness log.
        """
        agent = self._agents_by_id.get(agent_id)
        if agent is None:
            # Charter 3.2 — witness log is public-by-default within
            # the conductor; do NOT enumerate the registered agent
            # ids in the rejection string. That would leak the
            # registry to any caller who attempted a forbidden tool
            # call. A count is enough for ops to know whether the
            # conductor started up empty.
            raise KeyError(
                f"agent_id {agent_id!r} not in conductor registry "
                f"(registry size: {len(self._agents_by_id)})"
            )
        return tuple(agent.capabilities)

    # ─── Charter Article 5.4: human peer seat ────────────────────────
    def get_or_create_guest(self, handle: str) -> "HumanGuestAgent":
        """Visitor seat on the A2A bus (Charter Article 5.4).

        Returns an existing HumanGuestAgent if one already exists for
        this handle, else creates one and registers it. The handle is
        validated against `GUEST_HANDLE_RE` to ensure bus-minted peer
        ids are constrained to a safe charset. ValueError on malformed
        input is the caller's job to surface (e.g. CLI red error).
        """
        if not isinstance(handle, str) or not GUEST_HANDLE_RE.match(handle):
            raise ValueError(
                f"Invalid guest handle {handle!r}. "
                f"Must match ^[a-z0-9_-]{{1,32}}$ (lowercase letters, "
                f"digits, underscore, hyphen; 1-32 chars)."
            )
        agent_id = f"guest-{handle}"
        existing = self._agents_by_id.get(agent_id)
        if existing is not None:
            return existing
        from agents.human_guest_agent import HumanGuestAgent
        instance = HumanGuestAgent(
            db=self.db, bus=self.bus, llm_client=self.llm, handle=handle,
        )
        instance.connect_world(self.world)
        self._agents_by_id[agent_id] = instance
        self.agents[f"guest:{handle}"] = instance
        # Surface the named guest in the world's observable state so
        # the operator can see who is currently on the bus.
        self.world.human_avatar = {
            "name": f"Guest {handle}",
            "role": "Guest Human Avatar",
            "description": f"Visiting human peer (handle={handle})",
            "profile_doc": "docs/guest-charter.md",
        }
        self.world.timeline.log("world", "guest_arrived", {
            "agent_id": agent_id, "handle": handle,
        })
        return instance

    async def publish_as_guest(self, handle: str, text: str) -> int:
        """Route a human message into the visitor peer seat (Article 5.4).

        Returns the message_id so the front-end can cite it back.
        """
        agent = self.get_or_create_guest(handle)
        await agent.enqueue_human_input(text)
        # Synthesize an addressed A2AMessage so BaseAgent.handle_message
        # walks the normal publish-on-bus path. The human's words land
        # on the witness log; the LLM is bypassed by HumanGuestAgent.think().
        msg = A2AMessage(
            thread_id=f"guest-{handle}",
            from_agent=agent.agent_id,
            to_agent=None,
            message_type="observation",
            content=text,
        )
        return await agent.handle_message(msg)

    async def remove_guest(self, handle: str) -> bool:
        if not isinstance(handle, str) or not GUEST_HANDLE_RE.match(handle):
            raise ValueError(
                f"Invalid guest handle {handle!r}. "
                f"Must match ^[a-z0-9_-]{{1,32}}$"
            )
        agent_id = f"guest-{handle}"
        instance = self._agents_by_id.pop(agent_id, None)
        self.agents.pop(f"guest:{handle}", None)
        if self.world.human_avatar and self.world.human_avatar.get("name") == f"Guest {handle}":
            self.world.human_avatar = None
        if instance is not None:
            self.world.timeline.log("world", "guest_departed", {
                "agent_id": agent_id, "handle": handle,
            })
            return True
        return False

    async def register_all(self) -> None:
        for agent in self.agents.values():
            try:
                await agent.initialize()
            except Exception as e:
                self.logger.debug(f"register_agent({agent.name}) failed: {e}")

    # ─── Human interaction ────────────────────────────────

    def add_goal(self, description: str, priority: int = 3,
                 human_policy: HumanInputPolicy = HumanInputPolicy.ADVISORY) -> Goal:
        goal = self.world.add_goal(description, goal_type="human_request",
                                    priority=priority, human_policy=human_policy)
        self.world.timeline.log("human", "goal_added", {
            "goal_id": goal.id, "description": description[:80],
        })
        return goal

    def human_view(self) -> str:
        return self.world.human_view()

    def human_detail(self, limit: int = 20) -> str:
        return self.world.human_detail(limit=limit)

    def pause(self):
        self.world.pause()

    def resume(self):
        self.world.resume()

    # ─── Lifecycle ─────────────────────────────────────────

    async def run(self) -> None:
        await self.register_all()
        self.logger.info("Agent world spinning up, agents: %s",
                         list(self.agents.keys()))

        if self.tool_tuning:
            try:
                await asyncio.wait_for(self.tool_tuning.sync_from_db(), timeout=5)
            except Exception:
                self.logger.debug("ToolTuning sync_from_db failed")

        self.world.timeline.log("world", "world_started", {
            "agents": list(self.agents.keys()),
        })

        await self.world.run()

    def stop(self) -> None:
        self.world.stop()
        self._stop.set()

    def get_thread_log(self, thread_id: str):
        return []
