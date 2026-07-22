"""Godot agent — operates the Godot MCP ambassador."""
from __future__ import annotations

from agents.base_agent import BaseAgent
from shared.a2a_protocol import A2AMessage


TOOL_SYSTEM_PROMPT = """

TOOL FORMAT
============
Emit EXACTLY one fenced block per call:

```tool
{"name": "godot.<tool>", "arguments": { ... }}
```

Available tools:
  godot.get_scene_info
  godot.create_node         -> {name, primitive?, parent?, position?}
  godot.delete_node         -> {name}
  godot.find_node           -> {name}
  godot.set_transform       -> {name, position?, rotation?, scale?}
  godot.add_component       -> {name, component}
  godot.remove_component    -> {name, component}
  godot.create_scene        -> {name}
  godot.load_scene          -> {name}
  godot.save_scene          -> {name?}
  godot.list_scenes
  godot.list_assets         -> {filter?}
  godot.create_script       -> {name, language?, body?}
  godot.get_editor_state
"""


GODOT_SYSTEM_PROMPT = (
    "Du är Godot-agenten — en precis operatör av Godot-scenen via "
    "MCP-ambassadören. Regler:\n"
    "1. VALIDERA alltid innan du muterar\n"
    "2. En operation i taget\n"
    "3. Föredra gdscript för nya skript\n"
    "4. Vid fel: rapportera exakt till Planner\n"
    "5. Anropa Godot MCP med JSON inom ```tool block.\n"
    + TOOL_SYSTEM_PROMPT
)


class GodotAgent(BaseAgent):
    def __init__(self, db, bus, llm_client):
        super().__init__(
            agent_id="godot",
            name="godot",
            role="godot",
            capabilities=[
                "godot",
                "godot.get_scene_info",
                "godot.create_node",
                "godot.delete_node",
                "godot.find_node",
                "godot.set_transform",
                "godot.add_component",
                "godot.remove_component",
                "godot.create_scene",
                "godot.load_scene",
                "godot.save_scene",
                "godot.list_scenes",
                "godot.list_assets",
                "godot.create_script",
                "godot.get_editor_state",
            ],
            db=db,
            bus=bus,
            llm_client=llm_client,
        )

    def system_prompt(self) -> str:
        return GODOT_SYSTEM_PROMPT

    async def think(self, message: A2AMessage, scratchpad: str) -> str:
        return await self.llm.complete(
            f"## Scratchpad\n{scratchpad}\n\n"
            f"## Meddelande från {message.from_agent}\n{message.content}",
            self.system_prompt(),
        )
