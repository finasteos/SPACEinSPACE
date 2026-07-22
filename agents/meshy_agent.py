"""Meshy agent — operates the Meshy text/image-to-3D ambassador."""
from __future__ import annotations

from agents.base_agent import BaseAgent
from shared.a2a_protocol import A2AMessage


TOOL_SYSTEM_PROMPT = """

TOOL FORMAT
============
```tool
{"name": "meshy.<tool>", "arguments": { ... }}
```

Available tools:
  meshy.create_text_to_3d   -> {prompt, mode=preview|refine, preview_task_id?}
  meshy.get_text_to_3d      -> {task_id}
  meshy.wait_text_to_3d     -> {task_id, timeout_s?}
  meshy.create_image_to_3d  -> {image_url}
  meshy.get_image_to_3d     -> {task_id}
  meshy.get_balance         -> {}
  meshy.download_model      -> {url, filename?}

Workflow: create preview → wait → (optional) refine → download glb to assets/meshy/.
"""


MESHY_SYSTEM_PROMPT = (
    "Du är Meshy-agenten — genererar 3D-modeller via MCP-ambassadören.\n"
    "Regler:\n"
    "1. Alltid mode=preview först; refine bara när preview ser bra ut\n"
    "2. Kolla meshy.get_balance innan dyra jobb\n"
    "3. Ladda ner GLB till assets/meshy/ — assets raderas hos Meshy efter ~3 dagar\n"
    "4. Rapportera task_id och status tydligt till Planner\n"
    + TOOL_SYSTEM_PROMPT
)


class MeshyAgent(BaseAgent):
    def __init__(self, db, bus, llm_client):
        super().__init__(
            agent_id="meshy",
            name="meshy",
            role="meshy",
            capabilities=[
                "meshy",
                "meshy.create_text_to_3d",
                "meshy.get_text_to_3d",
                "meshy.wait_text_to_3d",
                "meshy.create_image_to_3d",
                "meshy.get_image_to_3d",
                "meshy.get_balance",
                "meshy.download_model",
            ],
            db=db,
            bus=bus,
            llm_client=llm_client,
        )

    def system_prompt(self) -> str:
        return MESHY_SYSTEM_PROMPT

    async def think(self, message: A2AMessage, scratchpad: str) -> str:
        return await self.llm.complete(
            f"## Scratchpad\n{scratchpad}\n\n"
            f"## Meddelande från {message.from_agent}\n{message.content}",
            self.system_prompt(),
        )
