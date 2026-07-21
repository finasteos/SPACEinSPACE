"""HumanGuestAgent — peer seat for a visiting human.

The 'guest' is operated by a human, not by an LLM. think() returns
None (Charter Article 2.3 — a lawful No) until the front-end enqueues
a message via enqueue_human_input().

Charter references:
- Article 1.4 territory (writes to scratchpad as 'guest-<handle>')
- Article 2.3 lawful-no refusal pattern (returns None on empty queue)
- Article 5.4 human role is a peer, not a controller
- Article 4.1 capability declaration enforced by BaseAgent
"""

from __future__ import annotations

import asyncio
from typing import Optional

from agents.base_agent import BaseAgent
from shared.a2a_protocol import A2AMessage


GUEST_CHARTER_SYSTEM = """Du är en mänsklig gäst i en multi-agent conductor.

1. Rehydrera från scratchpad mellan interventioner (Charter 5.4 visitor rule).
2. Citera witness-loggen ordagrant — message_id, inte agent-namn.
3. En uppercut per besök; resten i `blockers` med citation.
4. message_type: observation > question. Vägra `task` från gästplats.
5. Publicera error-citat för varje vägran (Charter 2.3).
6. Peer, inte operator. Du initierar inte conductor.

Läs `docs/guest-charter.md` i repot för hela regelkortet."""


class HumanGuestAgent(BaseAgent):
    """A peer seat on the A2A bus for a visiting human.

    Composes with Charter Article 5.4: humans are peers, not
    controllers. The agent's `think()` is bypassed — humans queue
    content via enqueue_human_input() — so BaseAgent still runs
    (initialize, run loop, bus subscription), but no LLM is invoked.
    """

    def __init__(self, db, bus, llm_client, handle: str = "guest"):
        super().__init__(
            agent_id=f"guest-{handle}",
            name=f"Guest {handle}",
            role="human",  # already permitted by sql/schema.sql CHECK
            capabilities=["human.observe", "human.interject"],
            db=db,
            bus=bus,
            llm_client=llm_client,
            subscribe=True,
        )
        self._pending: asyncio.Queue[str] = asyncio.Queue()

    async def enqueue_human_input(self, content: str) -> None:
        """Called by the CLI front-end when a guest types a message."""
        await self._pending.put(content)

    def system_prompt(self) -> str:
        # BaseAgent calls think() below; the LLM is bypassed in
        # guest mode so this string is only consulted in tooling.
        return GUEST_CHARTER_SYSTEM

    async def think(self, message: A2AMessage, scratchpad: str) -> Optional[str]:
        # Charter Article 2.3 — refusal is a lawful answer when no
        # human input is queued. Do not synthesise smalltalk.
        try:
            queued = await asyncio.wait_for(self._pending.get(), timeout=0.05)
        except asyncio.TimeoutError:
            return None
        # Rehydrate context into the surfaced reply so the human's
        # words land on the bus with awareness of the latest
        # scratchpad snapshot. The HTML-comment marker is visible in
        # witness-log audit but ignored by other agents' parsers.
        prefix = (
            f"<!-- guest rehydrated from scratchpad "
            f"({len(scratchpad)} chars) -->\n"
        )
        return prefix + queued
