"""Tests for the ExplorerAgent and the world.* capability wiring.

Confirms the Explorer is a lawful (non-ghost) citizen that declares the "world"
capability, that every world.* tool is registered and Article 4 gated, and that
the gate lets a world-capable agent through while rejecting one without it.
Mirrors the helper style of test_charter_40.
"""

from typing import Tuple
from unittest.mock import MagicMock

import pytest

from agents.explorer_agent import ExplorerAgent
from shared.tool_executor import ToolExecutor
from tools.registry import TOOL_DEFINITIONS

WORLD_TOOLS = [
    "world.look", "world.spawn", "world.move",
    "world.build", "world.place_art", "world.say",
]


class _CapResolver:
    def __init__(self, mapping):
        self.mapping = dict(mapping)

    def __call__(self, agent_id: str) -> Tuple[str, ...]:
        if agent_id not in self.mapping:
            raise KeyError(agent_id)
        return tuple(self.mapping[agent_id])


def _explorer():
    return ExplorerAgent(db=MagicMock(), bus=MagicMock(), llm_client=MagicMock())


class TestExplorerAgent:
    def test_declares_world_capability_as_tuple(self):
        agent = _explorer()
        assert "world" in agent.capabilities
        assert isinstance(agent.capabilities, tuple)

    def test_is_not_a_ghost(self):
        # Non-empty capabilities — Article 4.1 satisfied, construction allowed.
        assert _explorer().capabilities

    def test_system_prompt_is_visible_and_names_the_commons(self):
        assert "Commons" in _explorer().system_prompt()


class TestWorldRegistry:
    def test_all_world_tools_registered_and_gated(self):
        for name in WORLD_TOOLS:
            assert name in TOOL_DEFINITIONS, f"{name} missing from registry"
            assert "world" in TOOL_DEFINITIONS[name].requires_capability


class TestWorldGateIntegration:
    @pytest.mark.asyncio
    async def test_world_capable_agent_passes_gate(self):
        executor = ToolExecutor(
            db=None, agent_capabilities=_CapResolver({"explorer": ["world"]}),
        )
        executor._tool_defs["world.build"] = TOOL_DEFINITIONS["world.build"]
        result = await executor.execute(
            {"name": "world.build", "arguments": {}}, thread_id="t", agent_id="explorer",
        )
        # Gate passed (no handler in this bare executor → Unknown tool).
        assert not result["success"]
        assert "Unknown tool" in result["error"]
        assert "Charter Article 4" not in result["error"]

    @pytest.mark.asyncio
    async def test_agent_without_world_cap_is_rejected(self):
        executor = ToolExecutor(
            db=None, agent_capabilities=_CapResolver({"blender-only": ["blender"]}),
        )
        executor._tool_defs["world.build"] = TOOL_DEFINITIONS["world.build"]
        result = await executor.execute(
            {"name": "world.build", "arguments": {}}, thread_id="t", agent_id="blender-only",
        )
        assert not result["success"]
        assert "Charter Article 4" in result["error"]
        assert "world" in result["error"]
