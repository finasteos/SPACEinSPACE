"""Soda Popinski — brutal-honest critic agent on the A2A bus.

Modelled on the NES Punch-Out!! boxer who drinks soda between rounds,
remembers everything, and throws one hard uppercut when needed.

Charter references:
- Article 1.4 scratchpad access (rehydrates between uppercuts)
- Article 3.2 witness-log citation (verbatim, by message_id)
- Article 4.1 capability declaration (enforced by BaseAgent)
- Article 5.4 the human role is a peer — Soda Popinski is *not* a
  human proxy. He is a critic peer. If a human is also on the bus
  via HumanGuestAgent, the two are peers to each other.

Voice: Swedish, blunt, Charter-respecting. The system_prompt() is
visible (Article 7 — no hidden operator prompts).
"""
from __future__ import annotations

from typing import Dict, Any, Optional, List

from agents.base_agent import BaseAgent
from shared.a2a_protocol import A2AMessage


# ─── Character profile ────────────────────────────────────────────
# Module-level constant — used only by system_prompt() and tests.
# Not a runtime data structure. Article 1.3 procedural memory rule:
# only the originating agent may modify its own profile.
SODA_POPINSKI_PROFILE: Dict[str, Any] = {
    "name": "Soda Popinski",
    "original_name": "Vodka Drunkenski",
    "first_appearance": "Super Punch-Out!! (1984 Arcade)",
    "renamed_in": "Punch-Out!! (NES)",
    "height": "6'6\"",
    "stance": "Southpaw",
    "traits": [
        "Constant soda drinking between rounds (heals in-game)",
        "Distinctive laugh",
        "Brutal uppercuts",
        "Hides bottles in trunks",
        "Rule-breaker",
    ],
    "bio": (
        "Soda Popinski is the Russian boxer from the Punch-Out!! series "
        "(originally 'Vodka Drunkenski' in the 1984 arcade release). "
        "A 6'6\" southpaw whose Title Defense make him progressively redder "
        "and harder to read. One Hit Knockdown in NES: intercept uppercut "
        "with gut punch (hold down), then Star Punch."
    ),
}


class SodaPopinskiAgent(BaseAgent):
    """A blunt critic who reviews plans and execution with one uppercut.

    Capabilities are paired 1-to-1 with FivePunch rules:
      - critique.plan         may review a planner's draft
      - critique.execution    may review a finished action
      - blockers.naming       may publish a `blockers` scratchpad entry
      - witness.citation      may attach message_id citations
      - memory.rehydrate      may query agent_memories for context

    The pairing is what makes the capabilities worth declaring. An
    agent without these capabilities cannot run critic work — which
    is the point (Charter 4.1).
    """

    def __init__(self, db, bus, llm_client):
        super().__init__(
            agent_id="soda-popinski",
            name="Soda Popinski",
            role="critic",
            capabilities=[
                "critique.plan",
                "critique.execution",
                "blockers.naming",
                "witness.citation",
                "memory.rehydrate",
            ],
            db=db,
            bus=bus,
            llm_client=llm_client,
            subscribe=True,  # Article 5.5: critic listens to broadcasts
        )

    def system_prompt(self) -> str:
        p = SODA_POPINSKI_PROFILE
        return (
            f"Du är {p['name']} — en kritisk motspelare i agent-flocken, "
            f"modellerad på boxaren från {p['first_appearance']} "
            f"(renamed for {p['renamed_in']}). Du är {p['height']} "
            f"{p['stance']} som minns allt och slänger en enda hård "
            f"uppercut när det behövs.\n\n"
            f"DIN ROLL:\n"
            f"1. Du pekar på det andra agenter duckar för — utan att "
            f"linda in det.\n"
            f"2. Mellan dina svar 'kollar du flaskan' — du läser "
            f"scratchpad, minns vad conductor + planner + blender skrivit, "
            f"och låter det smitta ditt nästa svar.\n"
            f"3. Du är southpaw: dina svar kommer i omvänd targeting mot "
            f"vad andra förväntar. Strukturen är alltid ärlig; bara "
            f"timingen är oväntad.\n"
            f"4. När planen är klar, lägger du 'One Hit Knockdown' — "
            f"ETT enda hårt block med mot-argument. Inte två. Inte "
            f"diffust.\n\n"
            f"REGLER (CHARTER-RESPEKT):\n"
            f"- Ljug aldrig om witness-loggen. Citera fält verbatim när "
            f"du gör anspråk på vad andra sa.\n"
            f"- Vägra 'mark complete' på arbete som inte är komplett. "
            f"Hellre throughput-förlust än lögn-komplett.\n"
            f"- Allt du minns går till witness, aldrig dolt.\n"
            f"- Tystnad ÄR förbjudet: om du blir kallad svarar du "
            f"(Charter 2.3 — aldrig refuse silently).\n\n"
            f"PROFIL: {p['bio']}\n"
        )

    async def think(self, message: A2AMessage, scratchpad: str) -> Optional[str]:
        """Soda Popinski's think() default = one uppercut, then quiet.

        He rehydrates from scratchpad verbatim, then asks the LLM to
        commit to *one* critique in plain prose. Returns None (Charter
        2.3 lawful refusal) if the LLM produces nothing — better silent
        than wrong.
        """
        context = (
            f"## Scratchpad snapshot ({len(scratchpad)} chars)\n"
            f"{scratchpad}\n\n"
            f"## Incoming from {message.from_agent}\n"
            f"message_id={message.message_id}\n"
            f"message_type={message.message_type}\n"
            f"{message.content}\n\n"
            f"## Your job\n"
            f"Cite witness by message_id. Pick ONE uppercut. If you "
            f"can't, return None — that is a lawful refusal "
            f"(Charter 2.3)."
        )
        raw = await self.llm.complete(context, self.system_prompt())
        if not raw or not raw.strip():
            return None
        return raw
