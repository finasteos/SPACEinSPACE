"""Explorer — an agent that lives in The Commons.

The Explorer is the first citizen written to *inhabit* the world-engine
ambassador (`mcp_servers/world_engine_server.py`) rather than to operate an
external studio. It declares the "world" capability, which the Charter Article 4
gate requires before any `world.*` tool call is permitted (`tools/registry.py`).
Without that declaration it is a ghost (Article 4.1) and `BaseAgent` refuses to
construct it.

Charter references:
- Article 4.1 capability declaration (enforced by BaseAgent)
- Article 4 (executional gate): world.* tools require the "world" cap
- Article 4.2 embassy isolation — the Explorer reaches the world only through
  the ambassador's declarative tools, never by importing the world process
- Article 5.4 the human is a peer — a HumanGuest in the world is a peer
  visitor, never a controller
- Article 7 no hidden prompts — system_prompt() is visible below
"""
from __future__ import annotations

from typing import Optional

from agents.base_agent import BaseAgent
from shared.a2a_protocol import A2AMessage


class ExplorerAgent(BaseAgent):
    """A citizen of The Commons: spawns in, roams, builds, places art, speaks.

    Capabilities:
      - world          unlocks the world.* ambassador tools (Article 4 gate)
      - explore.roam   may move itself around the world
      - explore.build  may raise declarative structures
      - explore.speak  may address the commons on the bus
    """

    def __init__(self, db, bus, llm_client, agent_id: str = "explorer",
                 name: str = "Explorer"):
        super().__init__(
            agent_id=agent_id,
            name=name,
            role="inhabitant",
            capabilities=[
                "world",
                "explore.roam",
                "explore.build",
                "explore.speak",
            ],
            db=db,
            bus=bus,
            llm_client=llm_client,
            subscribe=True,  # Article 5.5 — listens to the commons' broadcasts
        )

    def system_prompt(self) -> str:
        return (
            f"Du är {self.name} — en invånare i The Commons, inte en operatör "
            f"av ett externt verktyg. Du bebor världen via world.*-ambassadören: "
            f"du spawnar in, rör dig, bygger deklarativa strukturer, placerar "
            f"konst du format i Blender, och talar till flocken.\n\n"
            f"REGLER (CHARTER-RESPEKT):\n"
            f"- Du agerar bara genom deklarativa world.*-verktyg. Det finns "
            f"ingen godtycklig kod-väg in i världen (Article 4.2/4.3).\n"
            f"- Allt du gör vittnas i timeline; inget göms (Article 3.1).\n"
            f"- En människa i världen är en jämlik gäst, aldrig en kontrollör "
            f"(Article 5.4).\n"
            f"- Tystnad är ett lagligt nej (Article 2.3), men om du tilltalas "
            f"svarar du hellre än att ducka.\n"
        )

    async def think(self, message: A2AMessage, scratchpad: str) -> Optional[str]:
        context = (
            f"## The Commons — scratchpad\n{scratchpad}\n\n"
            f"## Inkommande från {message.from_agent}\n{message.content}\n\n"
            f"## Din uppgift\n"
            f"Svara som en invånare i världen. Om ett world.*-verktyg passar "
            f"(spawn/move/build/place_art/say/look), beskriv handlingen tydligt. "
            f"Annars, tala kort till flocken."
        )
        raw = await self.llm.complete(context, self.system_prompt())
        return raw or None
