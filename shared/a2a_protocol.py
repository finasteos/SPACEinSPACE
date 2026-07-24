"""Agent-to-Agent (A2A) protocol — message dataclasses + in-process event bus.

A ``A2AMessage`` is a unit of communication between agents. The ``A2ABus``
delivers messages to subscribed agent callbacks IN-PROCESS (single Python
process). For multi-process fan-out, persist ``log_message`` to Supabase and
have other processes listen via Supabase Realtime.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Callable, Awaitable
from uuid import uuid4

from pydantic import BaseModel, Field


# ─── Message & Task dataclasses (backwards compatible) ──────────

class A2AMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    thread_id: str
    from_agent: str
    to_agent: Optional[str] = None  # None = broadcast (all subscribers)
    message_type: str = "answer"
    content: str = ""
    context: Dict = Field(default_factory=dict)
    parent_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ttl: Optional[int] = None

    def is_broadcast(self) -> bool:
        return self.to_agent is None

    def is_expired(self) -> bool:
        if self.ttl is None:
            return False
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return age > self.ttl

    def is_human_visible(self) -> bool:
        """Used by the CLI / dashboard to decide what to render to humans."""
        return self.message_type in (
            "observation",
            "error",
            "plan_update",
            "human_input",
        )

    def short(self) -> str:
        """One-line summary for logs."""
        target = self.to_agent or "(broadcast)"
        return (
            f"[{self.timestamp.strftime('%H:%M:%S')}] "
            f"{self.from_agent} → {target} :: {self.message_type}"
        )

    def attach_artifact(self, token: str, role: str = "attachment") -> None:
        """Record an artifact:// token on the message without expanding payload."""
        arts = self.context.setdefault("artifacts", [])
        if isinstance(arts, list):
            arts.append({"token": token, "role": role})

    def artifact_tokens(self) -> List[str]:
        """Tokens from context.artifacts plus any embedded in content."""
        from shared.artifacts import extract_tokens
        found: List[str] = []
        for item in self.context.get("artifacts") or []:
            if isinstance(item, dict) and item.get("token"):
                found.append(item["token"])
            elif isinstance(item, str):
                found.append(item)
        found.extend(extract_tokens(self.content or ""))
        # de-dupe preserve order
        seen = set()
        out: List[str] = []
        for t in found:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out

    def with_handoff(self, token: str, hint: str = "", role: str = "handoff") -> "A2AMessage":
        """Return a copy whose content is a short artifact handoff line."""
        from shared.artifacts import handoff_line
        data = self.model_dump()
        data["content"] = handoff_line(token, hint)
        msg = A2AMessage(**data)
        msg.attach_artifact(token, role=role)
        return msg


class A2ATask(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    task_type: str
    priority: int = 3
    payload: Dict = Field(default_factory=dict)
    required_tools: List[str] = Field(default_factory=list)
    estimated_complexity: str = "medium"

    def to_message(self, thread_id: str, from_agent: str,
                   to_agent: Optional[str] = None) -> A2AMessage:
        return A2AMessage(
            thread_id=thread_id,
            from_agent=from_agent,
            to_agent=to_agent,
            message_type="task",
            content=(
                f"Task: {self.task_type}\n"
                f"Complexity: {self.estimated_complexity}\n"
                f"Payload: {self.payload}"
            ),
            context={
                "task_id": self.task_id,
                "task_type": self.task_type,
                "priority": self.priority,
                "payload": self.payload,
                "required_tools": self.required_tools,
            },
        )


VALID_MESSAGE_TYPES = {
    "task",
    "question",
    "answer",
    "tool_call",
    "tool_result",
    "observation",
    "error",
    "heartbeat",
    "plan_update",
    "human_input",
}

Handler = Callable[[A2AMessage], Awaitable[None]]


# ─── In-process event bus ───────────────────────────────────────

class A2ABus:
    """Single-process pub/sub for agent messages.

    Semantic:
      * ``publish(msg)`` — persist to DB (optional), deliver to subscribers
        of ``msg.to_agent`` (or everyone except sender if broadcast).
      * ``request(msg, timeout)`` — publish and wait for a single reply whose
        ``parent_id == msg.message_id``. Returns ``None`` on timeout.
    """

    def __init__(self, db=None) -> None:
        self.db = db  # optional AgentDatabase; persistence is opt-in
        self._subs: Dict[str, List[Handler]] = defaultdict(list)
        # Multiple concurrent in-flight request/response closures. Each
        # ``request()`` appends its own coroutine; ``publish()`` invokes
        # every active one (each only resolves its own future via parent_id).
        self._wildcard_replies: List[Handler] = []

    # ─── Subscription ───────────────────────────────────────
    def subscribe(self, agent_name: str, handler: Handler) -> None:
        self._subs[agent_name].append(handler)

    def unsubscribe(self, agent_name: str, handler: Handler) -> None:
        try:
            self._subs[agent_name].remove(handler)
        except ValueError:
            pass

    # ─── Publish ────────────────────────────────────────────
    async def publish(self, msg: A2AMessage) -> None:
        # 1. Persist (best-effort)
        if self.db is not None:
            try:
                await self.db.log_message(
                    thread_id=msg.thread_id,
                    from_agent=msg.from_agent,
                    content=msg.content,
                    message_type=msg.message_type,
                    to_agent=msg.to_agent,
                    parent_id=msg.parent_id,
                    metadata={k: v for k, v in msg.context.items()
                              if isinstance(v, (str, int, float, bool, list, dict))},
                )
            except Exception:
                # Don't fail the bus if Supabase is unhappy.
                pass

        # 2. Wildcard reply catchers (for request/response pattern).
        #    Fires BEFORE targeted delivery so a future set inside the closure
        #    is not racing against pubsub callbacks. Each closure decides
        #    independently whether ``msg`` resolves its own future via parent_id.
        for wb in list(self._wildcard_replies):  # snapshot: handlers may remove themselves
            try:
                await wb(msg)
            except Exception as e:
                print(f"[A2ABus] wildcard reply error: {e!r}")

        # 3. Targeted delivery
        if msg.to_agent:
            targets = [msg.to_agent]
        else:
            targets = [n for n in self._subs.keys() if n != msg.from_agent]
        for t in targets:
            for cb in list(self._subs.get(t, [])):
                try:
                    await cb(msg)
                except Exception as e:
                    # Swallow handler errors so the bus keeps moving.
                    print(f"[A2ABus] handler {t} error: {e!r}")

    # ─── Request / response ─────────────────────────────────
    async def request(
        self, msg: A2AMessage, timeout: float = 30.0
    ) -> Optional[A2AMessage]:
        """Send ``msg`` and wait for the first reply with matching parent_id.

        Registers a closure-based wildcard handler that fires for every
        published reply and resolves the local future as soon as a reply
        arrives with ``parent_id == msg.message_id``. Multiple concurrent
        ``request()`` calls are supported — each appends its own closure to
        ``_wildcard_replies`` and removes it in ``finally``. Conductor's
        default flow uses its own ``asyncio.Queue`` and bypasses the bus, so
        this helper is intended for direct bus-to-bus callers (test rigs,
        future parallel agent teams).
        """
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()

        async def _on_reply(reply: A2AMessage) -> None:
            if not future.done() and reply.parent_id == msg.message_id:
                future.set_result(reply)

        self._wildcard_replies.append(_on_reply)
        try:
            await self.publish(msg)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            # Safe single-threaded asyncio mutation; remove() is no-op if
            # somehow already removed.
            try:
                self._wildcard_replies.remove(_on_reply)
            except ValueError:
                pass
