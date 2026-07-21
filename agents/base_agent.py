from abc import ABC
from typing import Optional, List, Dict, Any, Tuple
import asyncio
from datetime import datetime

from shared.a2a_protocol import A2AMessage, A2ATask, A2ABus
from shared.supabase_client import AgentDatabase
from shared.agent_timeline import Tickable, AgentTimeline, TimelineEvent, HumanInputPolicy


class CharterViolationError(ValueError):
    """Raised when a system operation violates the project Charter.

    Charter Article 4.1 is the most common cause: an agent declared
    without capabilities is a ghost who must not be allowed to run.
    Future Charter articles may introduce their own subclasses or
    more specific messages.
    """


class BaseAgent(ABC, Tickable):
    tick_interval: int = 1

    def __init__(self, agent_id: str, name: str, role: str,
                 capabilities: List[str], db: AgentDatabase,
                 bus: A2ABus, llm_client, subscribe: bool = False):
        # Charter Article 4.1: a capabilities=[] agent is a ghost and
        # shall not be allowed to run. We coerce the list to a tuple so
        # subclasses cannot structurally clear capabilities after
        # super().__init__ returns.
        if not capabilities:
            raise CharterViolationError(
                f"Charter Article 4.1 Violation: Agent '{agent_id}' "
                "declared empty capabilities. A ghost shall not be "
                "allowed to run."
            )
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.capabilities: Tuple[str, ...] = tuple(capabilities)
        self.db = db
        self.bus = bus
        self.llm = llm_client
        self.current_thread: Optional[str] = None
        self._stop_event = asyncio.Event()
        self._world: Optional[AgentWorld] = None
        self._pending_intents: List[Dict] = []
        if subscribe:
            self.bus.subscribe(agent_id, self._on_bus_message)

    async def initialize(self):
        # capabilities stored internally as tuple; pass as list to DB.
        await self.db.register_agent(
            self.agent_id, self.name, self.role, list(self.capabilities)
        )

    async def think(self, message: A2AMessage, scratchpad: str) -> str:
        context = (
            f"## Scratchpad\n{scratchpad}\n\n"
            f"## Meddelande från {message.from_agent}\n{message.content}"
        )
        return await self.llm.complete(context, self.system_prompt())

    def system_prompt(self) -> str:
        return f"Du är {self.name} — en agent som hanterar {', '.join(self.capabilities)}."

    def _on_bus_message(self, message: A2AMessage):
        asyncio.create_task(self.handle_message(message))

    async def handle_message(self, message: A2AMessage) -> Optional[A2AMessage]:
        if self._stop_event.is_set():
            return None
        if message.from_agent == self.agent_id:
            return None
        await self.db.update_agent_status(self.agent_id, "thinking", message.thread_id)
        self.current_thread = message.thread_id
        start_time = datetime.now()
        try:
            scratchpad = await self.db.get_scratchpad(message.thread_id)
            response_content = await self.think(message, scratchpad)
            if not response_content:
                return None
            embedding = await self._embed(response_content)
            latency = int((datetime.now() - start_time).total_seconds() * 1000)
            response = A2AMessage(
                thread_id=message.thread_id,
                from_agent=self.agent_id,
                to_agent=message.from_agent,
                message_type="answer",
                content=response_content,
                parent_id=message.message_id,
                context={"latency_ms": latency},
            )
            await self.bus.publish(response)
            await self.db.log_message(
                thread_id=message.thread_id,
                from_agent=self.agent_id,
                content=response_content,
                embedding=embedding,
                message_type="answer",
                to_agent=message.from_agent,
                latency_ms=latency,
                parent_id=message.message_id,
            )
            return response
        except Exception as e:
            error_msg = A2AMessage(
                thread_id=message.thread_id,
                from_agent=self.agent_id,
                to_agent=message.from_agent,
                message_type="error",
                content=f"## Error in {self.name}\n\n```\n{str(e)}\n```",
                parent_id=message.message_id,
            )
            await self.bus.publish(error_msg)
            return error_msg
        finally:
            await self.db.update_agent_status(self.agent_id, "idle")

    async def _embed(self, text: str) -> List[float]:
        return await self.llm.embed(text)

    async def send_task(self, task: A2ATask, to_agent: str, thread_id: str) -> Optional[A2AMessage]:
        message = task.to_message(self.agent_id, thread_id, to_agent)
        return await self.bus.request(message, timeout=task.timeout_seconds)

    async def update_scratchpad(self, thread_id: str, section: str, content: str):
        await self.db.upsert_scratchpad(thread_id, section, content, self.agent_id)

    async def get_scratchpad(self, thread_id: str) -> str:
        return await self.db.get_scratchpad(thread_id)

    async def retrieve_memory(self, query: str, thread_id: Optional[str] = None, limit: int = 5) -> List[Dict]:
        embedding = await self._embed(query)
        return await self.db.retrieve_memories(embedding, agent_id=self.agent_id, thread_id=thread_id, limit=limit)

    async def store_memory(self, content: str, memory_type: str = "episodic", **kwargs) -> str:
        embedding = await self._embed(content)
        return await self.db.store_memory(self.agent_id, content, embedding, memory_type, **kwargs)

    def connect_world(self, world):
        self._world = world

    async def tick(self, timeline: AgentTimeline) -> None:
        pass

    def log_event(self, timeline: AgentTimeline, event_type: str,
                  data: Optional[Dict] = None) -> TimelineEvent:
        return timeline.log(self.agent_id, event_type, data)

    async def run(self):
        await self.initialize()
        await self.db.update_agent_status(self.agent_id, "idle")
        while not self._stop_event.is_set():
            await asyncio.sleep(30)

    def stop(self):
        self._stop_event.set()
