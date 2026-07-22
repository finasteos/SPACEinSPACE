"""PixelLab agent — operates the PixelLab pixel-art ambassador."""
from __future__ import annotations

from agents.base_agent import BaseAgent
from shared.a2a_protocol import A2AMessage


TOOL_SYSTEM_PROMPT = """

TOOL FORMAT
============
```tool
{"name": "pixellab.<tool>", "arguments": { ... }}
```

Available tools:
  pixellab.generate_pixflux  -> {description, width?, height?, no_background?, save_to?}
  pixellab.rotate            -> {image_base64, to_direction, from_direction?, save_to?}
  pixellab.get_balance       -> {}
"""


PIXELLAB_SYSTEM_PROMPT = (
    "Du är PixelLab-agenten — genererar pixel art via MCP-ambassadören.\n"
    "Regler:\n"
    "1. Föredra 64x64 eller 128x128 sprites med no_background=true för spel\n"
    "2. Spara till assets/pixellab/ via save_to när resultatet ska återanvändas\n"
    "3. Kolla balance innan batch-generering\n"
    "4. En operation i taget\n"
    + TOOL_SYSTEM_PROMPT
)


class PixelLabAgent(BaseAgent):
    def __init__(self, db, bus, llm_client):
        super().__init__(
            agent_id="pixellab",
            name="pixellab",
            role="pixellab",
            capabilities=[
                "pixellab",
                "pixellab.generate_pixflux",
                "pixellab.rotate",
                "pixellab.get_balance",
            ],
            db=db,
            bus=bus,
            llm_client=llm_client,
        )

    def system_prompt(self) -> str:
        return PIXELLAB_SYSTEM_PROMPT

    async def think(self, message: A2AMessage, scratchpad: str) -> str:
        return await self.llm.complete(
            f"## Scratchpad\n{scratchpad}\n\n"
            f"## Meddelande från {message.from_agent}\n{message.content}",
            self.system_prompt(),
        )
