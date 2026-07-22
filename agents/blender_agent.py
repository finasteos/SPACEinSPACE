"""Blender agent — the only agent that talks to Blender.

Wires ``BlenderMCPServer`` subprocess tools (``blender.create_object``,
``blender.modify_object``, etc.) into the agent's system prompt. When the
LLM emits a fenced ``tool``` block the conductor's ``ToolExecutor`` will
parse + dispatch it back here as a ``tool_result`` observation.
"""
from __future__ import annotations

import json
from typing import Optional

from agents.base_agent import BaseAgent
from shared.a2a_protocol import A2AMessage


TOOL_SYSTEM_PROMPT = """\n\nTOOL FORMAT
============
To invoke a Blender operation, emit EXACTLY one fenced block per call:

```tool
{"name": "blender.<tool>", "arguments": { ... }}
```

Available tools:
  blender.get_scene_info         -> returns object list + mode
  blender.create_object          -> {type, location, name?, size?}
  blender.modify_object          -> {object, operation, value}
  blender.set_material           -> {object, color, material_name?}
  blender.render                 -> {output_path?, resolution_x?, resolution_y?}
  blender.get_viewport           -> {} (returns base64 PNG)
  blender.execute_script         -> {script}
  blender.undo                   -> {}

The conductor runs the tool and replies with a ``tool_result`` observation
you should summarize to the next agent.
"""

EXAMPLE_TOOL_BLOCK = "\n\nExample:\n```tool\n{\"name\": \"blender.create_object\", \"arguments\": {\"type\": \"cube\", \"location\": [0, 0, 0]}}\n```"


BLENDER_SYSTEM_PROMPT = (
    "Du är Blender-agenten - en precis operatör av Blender 3D. "
    "Dina regler:\n"
    "1. VALIDERA alltid innan du kör en operation (finns objektet? rätt mode?)\n"
    "2. En operation i taget - inga batch-kommandon\n"
    "3. Efter varje ändring: ta en viewport-screenshot (blender.get_viewport)\n"
    "4. Vid fel: rapportera exakt vad som gick fel till Planner\n"
    "5. Håll koll på aktivt objekt, mode, och senaste operation via scratchpad\n"
    "6. Använd blender.undo om något går fel\n"
    "7. Anropa blender MCP med JSON inom ```tool\n{...}\n``` block."
    + TOOL_SYSTEM_PROMPT
    + EXAMPLE_TOOL_BLOCK
)


class BlenderAgent(BaseAgent):
    def __init__(self, db, bus, llm_client):
        super().__init__(
            agent_id="blender", name="blender", role="blender",
            capabilities=[
                "blender.create_object", "blender.modify_object",
                "blender.set_material", "blender.render",
                "blender.get_viewport", "blender.execute_script",
                "blender.undo",
            ],
            db=db, bus=bus, llm_client=llm_client,
        )
        self._mcp = None

    def _get_mcp(self):
        if self._mcp is None:
            try:
                # B0 — share the conductor's persistent Blender (singleton),
                # so the scene snapshot reflects the same live scene the tool
                # calls mutate. BLENDER_MCP_MODE=oneshot for the legacy path.
                from mcp_servers.persistent_blender import create_blender_ambassador
                self._mcp = create_blender_ambassador()
            except Exception:
                self._mcp = None
        return self._mcp

    def system_prompt(self) -> str:
        return BLENDER_SYSTEM_PROMPT

    async def think(self, message: A2AMessage, scratchpad: str) -> str:
        scene_hint = await self._safe_scene_snapshot()
        context = (
            f"## Uppgift från {message.from_agent}\n"
            f"{message.content}\n\n"
            f"## Scratchpad (thread={message.thread_id})\n{scratchpad}\n\n"
            f"## Blender Scene (snapshot)\n{scene_hint}\n\n"
            "Vad ska jag göra i Blender? Skriv ett ```tool\n{...}\n``` block."
        )
        response = await self.llm.complete(context, self.system_prompt())
        await self.update_scratchpad(
            message.thread_id, "Blender State", response[:500]
        )
        return response

    async def _safe_scene_snapshot(self) -> str:
        mcp = self._get_mcp()
        if mcp is None:
            return "(Blender MCP not available)"
        try:
            handler = mcp.tools.get("blender.get_scene_info")
            if handler is None:
                return "(blender.get_scene_info not registered)"
            result = await handler()
            return json.dumps(result, indent=2)[:1000]
        except Exception as e:
            return f"(could not query Blender: {type(e).__name__}: {e})"
