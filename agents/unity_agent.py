"""Unity agent — operates the Unity MCP ambassador.

Mirrors BlenderAgent: declares unity.* capabilities, teaches the LLM the
```tool``` block format, and reaches Unity only through the ambassador.
"""
from __future__ import annotations

from agents.base_agent import BaseAgent
from shared.a2a_protocol import A2AMessage


TOOL_SYSTEM_PROMPT = """

TOOL FORMAT
============
Emit EXACTLY one fenced block per call:

```tool
{"name": "unity.<tool>", "arguments": { ... }}
```

Available tools:
  unity.get_scene_info
  unity.create_gameobject   -> {name, primitive?, parent?, position?}
  unity.delete_gameobject   -> {name}
  unity.find_gameobject     -> {name}
  unity.set_transform       -> {name, position?, rotation?, scale?}
  unity.add_component       -> {name, component}
  unity.remove_component    -> {name, component}
  unity.create_scene        -> {name}
  unity.load_scene          -> {name}
  unity.save_scene          -> {name?}
  unity.list_scenes
  unity.list_assets         -> {filter?}
  unity.create_script       -> {name, language?, body?}
  unity.get_editor_state

The conductor runs the tool and replies with a tool_result observation.
"""


UNITY_SYSTEM_PROMPT = (
    "Du är Unity-agenten — en precis operatör av Unity Editor-scenen via "
    "MCP-ambassadören. Regler:\n"
    "1. VALIDERA alltid innan du muterar (finns objektet? rätt scen?)\n"
    "2. En operation i taget\n"
    "3. Använd bara allowlistade primitives/components\n"
    "4. Vid fel: rapportera exakt till Planner\n"
    "5. Anropa Unity MCP med JSON inom ```tool block.\n"
    + TOOL_SYSTEM_PROMPT
)


class UnityAgent(BaseAgent):
    def __init__(self, db, bus, llm_client):
        super().__init__(
            agent_id="unity",
            name="unity",
            role="unity",
            capabilities=[
                "unity",
                "unity.get_scene_info",
                "unity.create_gameobject",
                "unity.delete_gameobject",
                "unity.find_gameobject",
                "unity.set_transform",
                "unity.add_component",
                "unity.remove_component",
                "unity.create_scene",
                "unity.load_scene",
                "unity.save_scene",
                "unity.list_scenes",
                "unity.list_assets",
                "unity.create_script",
                "unity.get_editor_state",
            ],
            db=db,
            bus=bus,
            llm_client=llm_client,
        )
        self._mcp = None

    def _get_mcp(self):
        if self._mcp is None:
            try:
                from mcp_servers.unity_mcp_server import UnityMCPServer
                self._mcp = UnityMCPServer()
            except Exception:
                self._mcp = None
        return self._mcp

    def system_prompt(self) -> str:
        return UNITY_SYSTEM_PROMPT

    async def think(self, message: A2AMessage, scratchpad: str) -> str:
        return await self.llm.complete(
            f"## Scratchpad\n{scratchpad}\n\n"
            f"## Meddelande från {message.from_agent}\n{message.content}",
            self.system_prompt(),
        )
