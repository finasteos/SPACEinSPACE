# TASKLIST — Agent Ecosystem

> Samordnad byggplan för agent-ecosystemet.
> Varje task är en atomisk enhet — en byggagent kan plocka upp den, utföra, och markera klar.
> Lägg till `- [x]` när klar. Lägg till nya tasks under `🔮 Backlog` när ni upptäcker dem.

---

## Snabbstart

```bash
cd /Users/joachimsundgren/agent-ecosystem
cp .env.example .env        # Fyll i SUPABASE_URL, SUPABASE_KEY, OLLAMA_BASE_URL
pip install -r requirements.txt
ollama pull qwen3-embedding:8b
ollama pull qwen3:4b
python sql/apply_schema.py  # Skapa tabeller i Supabase
python main.py              # Starta CLI
```

---

## Status — nuläget 2026-07-21

| Detta är BYGGT | Detta SAKNAS |
|---|---|
| ✅ Projektstruktur, requirements, .env.example | ❌ Tool Execution Engine (P0) |
| ✅ A2A-protokoll (A2AMessage, A2ATask) | ❌ Supabase async-klient (P0) |
| ✅ Scratchpad-manager (CRUD, section updates) | ❌ Planner infinite loop fix (P0) |
| ✅ Memory-system (embed + retrieve + store) | ❌ Web search implementation (P1) |
| ✅ LLM-wrapper (Ollama generate) | ❌ File read/write implementation (P1) |
| ✅ Telemetry (span-tracking, latency) | ✅ Blender MCP inkoppling (persistent, B0) |
| ✅ Tool-registry (12 tools med scheman) | ❌ Tool registry integration (P1) |
| ✅ Base agent-klass | ❌ Agent-register i Supabase (P2) |
| ✅ Planner-agent (med loop-bugg) | ❌ Graceful shutdown (P2) |
| ✅ Blender-agent (med hårdkodad stub) | ❌ Session persistence (P3) |
| ✅ Memory-agent | ❌ Tester (P3) |
| ✅ Tool-agent (stub) | ❌ HTML/JS Dashboard (P3) |
| ✅ Review-agent | |
| ✅ Fallback-agent | |
| ✅ Blender MCP-server (fristående) | |
| ✅ SQL-schema (pgvector, RPC, RLS) | |
| ✅ CLI-UI (Rich, /status, /log, /help) | |

---

## Fas 1 — Fundamentet (P0, måste fungera för att köra)

### Task 1.1: Skapa Supabase async-klient

All DB-anrop använder `await` men den nuvarande klienten är synkron — kommer crasha direkt.

**Kod att implementera i `shared/supabase_client.py`:**

```python
import os
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from supabase import create_client, Client

class AgentDatabase:
    def __init__(self):
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_KEY")
        )

    # ─── Memory ─────────────────────────────────────────────
    async def store_memory(
        self,
        agent_id: str,
        content: str,
        embedding: List[float],
        memory_type: str = "episodic",
        metadata: Optional[Dict] = None,
        parent_id: Optional[str] = None,
        confidence: float = 1.0,
        source: Optional[str] = None,
        ttl_hours: Optional[int] = None
    ) -> str:
        data = {
            "agent_id": agent_id,
            "memory_type": memory_type,
            "content": content,
            "embedding": embedding,
            "metadata": metadata or {},
            "parent_id": parent_id,
            "confidence": confidence,
            "source": source,
            "expires_at": (datetime.now() + timedelta(hours=ttl_hours)).isoformat() if ttl_hours else None
        }
        result = self.supabase.table("agent_memories").insert(data).execute()
        return result.data[0]["id"]

    async def retrieve_memories(
        self,
        query_embedding: List[float],
        agent_id: Optional[str] = None,
        memory_type: Optional[str] = None,
        thread_id: Optional[str] = None,
        threshold: float = 0.7,
        limit: int = 10
    ) -> List[Dict]:
        result = self.supabase.rpc("match_memories", {
            "query_embedding": query_embedding,
            "match_threshold": threshold,
            "match_count": limit,
            "agent_filter": agent_id,
            "type_filter": memory_type,
            "thread_filter": thread_id
        }).execute()
        return result.data

    # ─── Scratchpad ─────────────────────────────────────────
    async def get_scratchpad(self, thread_id: str) -> Dict[str, Any]:
        result = self.supabase.rpc("get_scratchpad", {
            "p_thread_id": thread_id
        }).execute()
        scratchpad = {}
        for row in result.data:
            scratchpad[row["section"]] = {
                "content": row["content"],
                "version": row["version"],
                "agent_id": row["agent_id"],
                "updated_at": row["updated_at"]
            }
        return scratchpad

    async def update_scratchpad(
        self, thread_id: str, section: str, content: str,
        agent_id: str, metadata: Optional[Dict] = None
    ) -> int:
        existing = self.supabase.table("scratchpad")\
            .select("version")\
            .eq("thread_id", thread_id)\
            .eq("section", section)\
            .execute()
        version = 1
        if existing.data:
            version = existing.data[0]["version"] + 1
        data = {
            "thread_id": thread_id, "section": section,
            "content": content, "agent_id": agent_id,
            "version": version, "metadata": metadata or {}
        }
        self.supabase.table("scratchpad").upsert(data).execute()
        return version

    # ─── A2A Messages ───────────────────────────────────────
    async def send_message(
        self, thread_id: str, from_agent: str, content: str,
        embedding: List[float], message_type: str = "observation",
        to_agent: Optional[str] = None, tool_calls: Optional[List] = None,
        latency_ms: Optional[int] = None, metadata: Optional[Dict] = None,
        parent_id: Optional[str] = None
    ) -> str:
        message_id = f"{from_agent}_{datetime.now().timestamp()}"
        data = {
            "thread_id": thread_id, "message_id": message_id,
            "from_agent": from_agent, "to_agent": to_agent,
            "message_type": message_type, "content": content,
            "embedding": embedding, "tool_calls": tool_calls or [],
            "latency_ms": latency_ms, "metadata": metadata or {},
            "parent_id": parent_id
        }
        self.supabase.table("agent_conversations").insert(data).execute()
        return message_id

    async def get_thread_messages(
        self, thread_id: str, since: Optional[datetime] = None, limit: int = 50
    ) -> List[Dict]:
        query = self.supabase.table("agent_conversations")\
            .select("*").eq("thread_id", thread_id)\
            .order("created_at", desc=True).limit(limit)
        if since:
            query = query.gte("created_at", since.isoformat())
        result = query.execute()
        return result.data

    # ─── Agent Registry ─────────────────────────────────────
    async def register_agent(self, agent_id: str, name: str, role: str, capabilities: List[str]):
        data = {"id": agent_id, "name": name, "role": role, "capabilities": capabilities, "status": "idle"}
        self.supabase.table("agents").upsert(data).execute()

    async def update_agent_status(self, agent_id: str, status: str, thread_id: Optional[str] = None):
        data = {"status": status, "last_heartbeat": datetime.now().isoformat()}
        if thread_id:
            data["current_thread_id"] = thread_id
        self.supabase.table("agents").update(data).eq("id", agent_id).execute()

    async def get_active_agents(self) -> List[Dict]:
        result = self.supabase.table("agents").select("*").order("last_heartbeat", desc=True).execute()
        return result.data

    # ─── Tool Calls ─────────────────────────────────────────
    async def log_tool_call(
        self, thread_id: str, agent_id: str, tool_name: str,
        input_params: Dict, output_result: Optional[Dict] = None,
        success: Optional[bool] = None, error_message: Optional[str] = None,
        latency_ms: Optional[int] = None, scratchpad_version: Optional[int] = None
    ):
        data = {
            "thread_id": thread_id, "agent_id": agent_id, "tool_name": tool_name,
            "input_params": input_params, "output_result": output_result,
            "success": success, "error_message": error_message,
            "latency_ms": latency_ms, "scratchpad_version": scratchpad_version
        }
        self.supabase.table("tool_calls").insert(data).execute()
```

**Sub-tasks:**
- [ ] Skriv koden ovan till `shared/supabase_client.py`
- [ ] Uppdatera `requirements.txt`: `supabase>=2.0.0` → `supabase[async]>=2.0.0`
- [ ] Skapa `sql/apply_schema.py` som läser `sql/schema.sql` och kör mot Supabase:
  ```python
  import os
  from supabase import create_client
  from dotenv import load_dotenv
  load_dotenv()
  supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
  with open("sql/schema.sql") as f:
      supabase.query(f.read()).execute()
  print("Schema applied!")
  ```
- [ ] Kör `python sql/apply_schema.py` mot en riktig Supabase-instans
- [ ] Verifiera att in-memory.py, scratchpad.py och conductor.py importerar från `AgentDatabase` istället för direkt `get_supabase()`

---

### Task 1.2: Bygg A2A-protokoll med Broadcast

Ersätt nuvarande `a2a_protocol.py` med en full event-bus.

**Kod för `shared/a2a_protocol.py`:**

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
import json, asyncio

class A2AMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: f"msg_{datetime.now().timestamp()}")
    thread_id: str
    from_agent: str
    to_agent: Optional[str] = None
    message_type: Literal[
        "task", "question", "answer", "tool_call", "tool_result",
        "observation", "error", "plan_update", "heartbeat", "human_input"
    ]
    content: str
    context: Dict[str, Any] = Field(default_factory=dict)
    parent_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    ttl: Optional[int] = None

    def is_broadcast(self) -> bool:
        return self.to_agent is None

    def is_human_visible(self) -> bool:
        return self.message_type in ["observation", "error", "plan_update", "human_input"]

    def to_markdown_chat(self) -> str:
        icon = {
            "task": "📋", "question": "❓", "answer": "✅",
            "tool_call": "🔧", "tool_result": "📤",
            "observation": "👁️", "error": "❌",
            "plan_update": "📝", "heartbeat": "💓", "human_input": "👤"
        }.get(self.message_type, "💬")
        target = f" → **{self.to_agent}**" if self.to_agent else " (broadcast)"
        return f"{icon} **{self.from_agent}**{target}\n\n{self.content}\n\n---"

class A2ATask(BaseModel):
    task_id: str = Field(default_factory=lambda: f"task_{datetime.now().timestamp()}")
    task_type: Literal[
        "blender_operation", "memory_query", "plan_review",
        "tool_execution", "scene_analysis", "render_job"
    ]
    priority: int = Field(default=3, ge=1, le=5)
    payload: Dict[str, Any]
    required_tools: List[str] = Field(default_factory=list)
    estimated_complexity: Literal["simple", "medium", "complex"] = "medium"
    max_retries: int = 2
    timeout_seconds: int = 60

    def to_message(self, from_agent: str, thread_id: str, to_agent: Optional[str] = None) -> A2AMessage:
        return A2AMessage(
            thread_id=thread_id, from_agent=from_agent, to_agent=to_agent,
            message_type="task",
            content=f"## Task: {self.task_type}\n\nPriority: {self.priority}/5\nComplexity: {self.estimated_complexity}\n\n```json\n{json.dumps(self.payload, indent=2)}\n```",
            context={"task_id": self.task_id, "task_type": self.task_type, "priority": self.priority,
                     "required_tools": self.required_tools, "complexity": self.estimated_complexity}
        )

class A2ABus:
    def __init__(self, db: "AgentDatabase"):
        self.db = db
        self.subscribers: Dict[str, List[callable]] = {}

    def subscribe(self, agent_id: str, callback: callable):
        if agent_id not in self.subscribers:
            self.subscribers[agent_id] = []
        self.subscribers[agent_id].append(callback)

    def unsubscribe(self, agent_id: str, callback: callable):
        if agent_id in self.subscribers:
            self.subscribers[agent_id].remove(callback)

    async def publish(self, message: A2AMessage):
        targets = []
        if message.to_agent:
            targets = [message.to_agent]
        else:
            # Broadcast: alla utom avsändaren
            targets = [a for a in self.subscribers.keys() if a != message.from_agent]
        for target in targets:
            if target in self.subscribers:
                for callback in self.subscribers[target]:
                    try:
                        await callback(message)
                    except Exception as e:
                        print(f"[A2ABus] Error delivering to {target}: {e}")

    async def request(self, message: A2AMessage, timeout: float = 30.0) -> Optional[A2AMessage]:
        future = asyncio.Future()
        async def handler(msg: A2AMessage):
            if msg.parent_id == message.message_id and not future.done():
                future.set_result(msg)
        temp_id = f"temp_{message.message_id}"
        self.subscribe(temp_id, handler)
        try:
            await self.publish(message)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self.unsubscribe(temp_id, handler)
```

**Sub-tasks:**
- [ ] Skriv koden ovan till `shared/a2a_protocol.py`
- [ ] Verifiera att den importeras korrekt av alla agenter
- [ ] Lägg till `A2ABus`-integration i Conductor

---

### Task 1.3: Bygg Tool Execution Engine

Systemets största gap. LLM:en genererar tool-calls i kodblock men inget exekverar dem.

**Kod för `shared/tool_executor.py`:**

```python
import json
import re
from typing import List, Dict, Any, Optional, Callable, Awaitable
import asyncio
import httpx
from datetime import datetime

from shared.a2a_protocol import A2AMessage
from shared.telemetry import telemetry

ToolHandler = Callable[..., Awaitable[Dict[str, Any]]]

class ToolExecutor:
    def __init__(self):
        self._handlers: Dict[str, ToolHandler] = {}
        self._register_builtins()

    def register(self, name: str):
        def decorator(func: ToolHandler):
            self._handlers[name] = func
            return func
        return decorator

    def _register_builtins(self):
        @self.register("web.search")
        async def web_search(query: str):
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.duckduckgo.com",
                    params={"q": query, "format": "json"},
                    timeout=10
                )
                return resp.json()

        @self.register("file.read")
        async def file_read(path: str):
            # Path traversal protection
            import os
            safe = os.path.normpath(path)
            if safe.startswith("..") or safe.startswith("/"):
                raise PermissionError("Path traversal denied")
            with open(safe) as f:
                return {"content": f.read(), "path": safe}

        @self.register("file.write")
        async def file_write(path: str, content: str):
            import os
            safe = os.path.normpath(path)
            if safe.startswith("..") or safe.startswith("/"):
                raise PermissionError("Path traversal denied")
            with open(safe, "w") as f:
                f.write(content)
            return {"path": safe, "bytes": len(content)}

    async def register_blender(self, blender_handler: ToolHandler):
        """Koppla in Blender MCP när den är igång."""
        self._handlers["blender.get_scene_info"] = blender_handler
        self._handlers["blender.create_object"] = blender_handler
        self._handlers["blender.modify_object"] = blender_handler
        self._handlers["blender.set_material"] = blender_handler
        self._handlers["blender.render"] = blender_handler
        self._handlers["blender.execute_script"] = blender_handler
        self._handlers["blender.select_object"] = blender_handler
        self._handlers["blender.delete_selected"] = blender_handler
        self._handlers["blender.undo"] = blender_handler
        self._handlers["blender.get_viewport"] = blender_handler

    def parse_tool_calls(self, text: str) -> List[Dict]:
        """Extraherar ```tool ... ``` block från LLM-svar."""
        pattern = r'```(?:tool)?\s*\n?({.*?})\n?```'
        matches = re.findall(pattern, text, re.DOTALL)
        calls = []
        for match in matches:
            try:
                parsed = json.loads(match.strip())
                if "name" in parsed:
                    calls.append(parsed)
            except json.JSONDecodeError:
                # Försök hitta name/arguments pattern
                try:
                    parsed = json.loads(match.strip().replace("'", '"'))
                    if "name" in parsed:
                        calls.append(parsed)
                except json.JSONDecodeError:
                    continue
        return calls

    async def execute(
        self, tool_call: Dict, thread_id: str, agent_id: str
    ) -> Dict:
        name = tool_call.get("name", "")
        arguments = tool_call.get("arguments", {})
        tool_id = tool_call.get("id", "unknown")

        span = telemetry.start_span(agent_id, f"tool:{name}")
        handler = self._handlers.get(name)

        if not handler:
            span.finish(success=False)
            telemetry.record_span(span)
            return {"id": tool_id, "name": name, "success": False,
                    "error": f"No handler for tool: {name}"}

        try:
            result = await asyncio.wait_for(handler(**arguments), timeout=30)
            span.finish(success=True)
            telemetry.record_span(span)
            return {"id": tool_id, "name": name, "success": True, "result": result}
        except Exception as e:
            span.finish(success=False, error=str(e))
            telemetry.record_span(span)
            return {"id": tool_id, "name": name, "success": False, "error": str(e)}

    async def execute_all(
        self, text: str, thread_id: str, agent_id: str
    ) -> List[A2AMessage]:
        """Extraherar alla tool-calls från text och exekverar dem."""
        calls = self.parse_tool_calls(text)
        if not calls:
            return []

        results = []
        for call in calls:
            result = await self.execute(call, thread_id, agent_id)
            results.append(A2AMessage(
                thread_id=thread_id,
                from_agent="tool_executor",
                to_agent=agent_id,
                message_type="tool_result",
                content=f"## Tool Result: {call.get('name')}\n\n```json\n{json.dumps(result, indent=2)}\n```",
                context={"tool_name": call.get("name"), "tool_result": result,
                         "success": result.get("success", False)}
            ))
        return results
```

**Sub-tasks:**
- [ ] Skapa `shared/tool_executor.py` med koden ovan
- [ ] Integrera i `orchestrator/conductor.py` — efter agent-svar, kör tool executor före vidare routing:
  ```python
  async def _process_message(self, msg: A2AMessage):
      ...
      response = await agent.handle_message(msg)
      if response:
          tool_results = await self.tool_executor.execute_all(
              response.content, msg.thread_id, response.from_agent
          )
          for r in tool_results:
              await self.message_queue.put(r)
          if not tool_results:
              await self.message_queue.put(response)
  ```
- [ ] Lägg till tool-executor som parameter i Conductor.__init__

---

### Task 1.4: Fixa Planner infinite loop

**Problem:** `_handle_completion()` returnerar meddelande utan `to_agent` → Conductor routar till planner igen → loop.

**Fix i `agents/planner_agent.py`:**

```python
async def _handle_completion(self, msg: A2AMessage):
    await self.scratchpad.update_section(
        msg.thread_id, "Aktuell Plan",
        f"- [X] {msg.from_agent} klar: {msg.content[:200]}",
        self.name,
    )
    # Returnera None så Conductor inte routar vidare
    return None
```

**Sub-tasks:**
- [ ] Ändra `_handle_completion()` att returnera `None`
- [ ] Lägg till guard i `handle_generic`: `if msg.from_agent == self.name: return None`
- [ ] Verifiera med ett test-flöde

---

### Task 1.5: Uppdatera SQL-schema

Lägg till tabeller för agent-register, tool_calls, RLS-policies och en `get_scratchpad`-RPC.

**Kod att lägga till i `sql/schema.sql`:**

```sql
-- Agent-register
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('planner', 'blender', 'memory', 'tool', 'review', 'fallback', 'human')),
    status TEXT NOT NULL DEFAULT 'idle' CHECK (status IN ('idle', 'active', 'thinking', 'waiting', 'error', 'paused')),
    capabilities TEXT[] DEFAULT '{}',
    current_thread_id TEXT,
    last_heartbeat TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tool-anrop logg
CREATE TABLE IF NOT EXISTS tool_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_version TEXT,
    input_params JSONB NOT NULL,
    output_result JSONB,
    success BOOLEAN,
    error_message TEXT,
    latency_ms INT,
    scratchpad_version INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Text-sökning med trigram
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_memories_content_trgm ON agent_memories USING gin (content gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_conversations_content_trgm ON agent_conversations USING gin (content gin_trgm_ops);

-- Automatisk updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_memories_updated_at ON agent_memories;
CREATE TRIGGER update_memories_updated_at BEFORE UPDATE ON agent_memories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_scratchpad_updated_at ON scratchpad;
CREATE TRIGGER update_scratchpad_updated_at BEFORE UPDATE ON scratchpad
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- RPC: hämta scratchpad för en thread
CREATE OR REPLACE FUNCTION get_scratchpad(p_thread_id TEXT)
RETURNS TABLE(section TEXT, content TEXT, version INT, agent_id TEXT, updated_at TIMESTAMPTZ)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT s.section, s.content, s.version, s.agent_id, s.updated_at
    FROM scratchpad s
    WHERE s.thread_id = p_thread_id
    ORDER BY CASE s.section
        WHEN 'plan' THEN 1
        WHEN 'blender_state' THEN 2
        WHEN 'memory_refs' THEN 3
        WHEN 'blockers' THEN 4
        WHEN 'human_input_needed' THEN 5
        WHEN 'raw_notes' THEN 6
    END;
END;
$$;

-- Row Level Security
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE tool_calls ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS service_all ON agents;
DROP POLICY IF EXISTS service_all ON tool_calls;
DROP POLICY IF EXISTS anon_read_agents ON agents;

CREATE POLICY service_all ON agents FOR ALL TO service_role USING (true);
CREATE POLICY service_all ON tool_calls FOR ALL TO service_role USING (true);
CREATE POLICY anon_read_agents ON agents FOR SELECT TO anon USING (true);
```

**Sub-tasks:**
- [ ] Lägg till SQL ovan i `sql/schema.sql`
- [ ] Applicera på Supabase

---

## Fas 2 — Agenterna vaknar (P1)

### Task 2.1: Bygg Base Agent-klass (ABC)

Ersätt nuvarande `base_agent.py` med en abstrakt basklass som använder `AgentDatabase` och `A2ABus`.

**Kod för `agents/base_agent.py`:**

```python
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
import asyncio
from datetime import datetime

from shared.a2a_protocol import A2AMessage, A2ATask, A2ABus
from shared.supabase_client import AgentDatabase

class BaseAgent(ABC):
    def __init__(self, agent_id: str, name: str, role: str,
                 capabilities: List[str], db: AgentDatabase,
                 bus: A2ABus, llm_client: Any):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.capabilities = capabilities
        self.db = db
        self.bus = bus
        self.llm = llm_client
        self.current_thread: Optional[str] = None
        self._stop_event = asyncio.Event()
        self.bus.subscribe(agent_id, self._handle_message)

    async def initialize(self):
        await self.db.register_agent(self.agent_id, self.name, self.role, self.capabilities)

    @abstractmethod
    async def think(self, message: A2AMessage, scratchpad: Dict) -> str:
        pass

    @abstractmethod
    def system_prompt(self) -> str:
        pass

    async def _handle_message(self, message: A2AMessage):
        if self._stop_event.is_set():
            return
        await self.db.update_agent_status(self.agent_id, "thinking", message.thread_id)
        self.current_thread = message.thread_id
        start_time = datetime.now()
        try:
            scratchpad = await self.db.get_scratchpad(message.thread_id)
            response_content = await self.think(message, scratchpad)
            embedding = await self._embed(response_content)
            latency = int((datetime.now() - start_time).total_seconds() * 1000)
            response = A2AMessage(
                thread_id=message.thread_id, from_agent=self.agent_id,
                to_agent=message.from_agent, message_type="answer",
                content=response_content, parent_id=message.message_id,
                context={"latency_ms": latency}
            )
            await self.bus.publish(response)
            await self.db.send_message(
                thread_id=message.thread_id, from_agent=self.agent_id,
                content=response_content, embedding=embedding,
                message_type="answer", to_agent=message.from_agent,
                latency_ms=latency, parent_id=message.message_id
            )
        except Exception as e:
            error_msg = A2AMessage(
                thread_id=message.thread_id, from_agent=self.agent_id,
                to_agent=message.from_agent, message_type="error",
                content=f"## Error in {self.name}\n\n```\n{str(e)}\n```",
                parent_id=message.message_id
            )
            await self.bus.publish(error_msg)
        finally:
            await self.db.update_agent_status(self.agent_id, "idle")

    async def _embed(self, text: str) -> List[float]:
        response = await self.llm.embed(text)
        return response

    async def send_task(self, task: A2ATask, to_agent: str, thread_id: str) -> Optional[A2AMessage]:
        message = task.to_message(self.agent_id, thread_id, to_agent)
        return await self.bus.request(message, timeout=task.timeout_seconds)

    async def update_scratchpad(self, thread_id: str, section: str, content: str):
        await self.db.update_scratchpad(thread_id, section, content, self.agent_id)

    async def get_scratchpad(self, thread_id: str) -> Dict:
        return await self.db.get_scratchpad(thread_id)

    async def retrieve_memory(self, query: str, thread_id: Optional[str] = None, limit: int = 5) -> List[Dict]:
        embedding = await self._embed(query)
        return await self.db.retrieve_memories(embedding, agent_id=self.agent_id, thread_id=thread_id, limit=limit)

    async def store_memory(self, content: str, memory_type: str = "episodic", **kwargs) -> str:
        embedding = await self._embed(content)
        return await self.db.store_memory(self.agent_id, content, embedding, memory_type, **kwargs)

    async def run(self):
        await self.initialize()
        await self.db.update_agent_status(self.agent_id, "idle")
        while not self._stop_event.is_set():
            await asyncio.sleep(30)

    def stop(self):
        self._stop_event.set()
```

**Sub-tasks:**
- [ ] Skriv koden ovan till `agents/base_agent.py`
- [ ] Uppdatera alla befintliga agenter att ärva från `BaseAgent` med rätt ABC-signatur

---

### Task 2.2: Bygg Planner-agent (Seg fläskhjärna #1)

Full Planner med task-dekomposition, komplexitetsbedömning, steg-för-steg-exekvering.

**Kod för `agents/planner_agent.py`:**

```python
from typing import Dict, Any, List
import json
from datetime import datetime

from agents.base_agent import BaseAgent
from shared.a2a_protocol import A2AMessage, A2ATask

class PlannerAgent(BaseAgent):
    def __init__(self, db, bus, llm_client):
        super().__init__(
            agent_id="planner", name="Planner", role="planner",
            capabilities=["planning", "coordination", "task_decomposition", "human_escalation"],
            db=db, bus=bus, llm_client=llm_client
        )

    def system_prompt(self) -> str:
        return """Du är PlannerAgent, teamets koordinator.

DIN ROLL:
1. Bryt ner komplexa uppgifter i steg
2. Delegera till rätt agent
3. GRANSKA resultat innan du godkänner
4. Vid osäkerhet → FRÅGA människan (human_input)
5. DU är LÅNGSAM och METODISK

REGLER:
- Ingen agent får köra mer än 3 tools utan scratchpad-uppdatering
- "Complex" uppgifter måste godkännas av Review-agent eller människa
- Alltid spara plan i scratchpad innan exekvering
- Använd Markdown, var tydlig och strukturerad"""

    async def think(self, message: A2AMessage, scratchpad: Dict) -> str:
        if message.message_type == "human_input":
            return await self._handle_human_input(message, scratchpad)
        elif message.message_type == "task":
            return await self._handle_incoming_task(message, scratchpad)
        elif message.message_type == "observation":
            return await self._handle_observation(message, scratchpad)
        elif message.message_type == "error":
            return await self._handle_error(message, scratchpad)
        else:
            return f"## 📝 Planeringsläge\nMottog: {message.content[:200]}..."

    async def _handle_human_input(self, message: A2AMessage, scratchpad: Dict) -> str:
        complexity = await self._assess_complexity(message.content)
        plan = await self._create_plan(message.content, complexity)
        await self.update_scratchpad(message.thread_id, "plan",
            f"## Plan: {message.content[:50]}...\n**Komplexitet:** {complexity}\n{plan}")
        if complexity == "complex":
            return f"""## 📋 Plan för: "{message.content[:80]}..."
**Komplexitet:** {complexity} ⚠️
{plan}
### ⚠️ Mänsklig input behövs
Godkänn planen innan vi fortsätter. Svara med **"godkänn"**, **"ändra: ..."**, eller **"avbryt"**."""
        return await self._execute_plan(message.thread_id, plan)

    async def _assess_complexity(self, task: str) -> str:
        prompt = f"Bedöm komplexiteten (simple/medium/complex) för: '{task}'\nSimple=1 op, Medium=2-5 steg, Complex=>5 steg"
        response = await self.llm.complete(prompt, self.system_prompt())
        r = response.strip().lower()
        return r if r in ("simple", "medium", "complex") else "medium"

    async def _create_plan(self, task: str, complexity: str) -> str:
        prompt = f"Skriv steg-för-steg plan för Blender-uppgift: '{task}'\nAnvänd agenter: blender, memory, tool, review"
        return await self.llm.complete(prompt, self.system_prompt())

    async def _execute_plan(self, thread_id: str, plan: str) -> str:
        steps = self._parse_plan(plan)
        results = []
        for i, step in enumerate(steps):
            agent = step.get("agent")
            task_type = step.get("task", "blender_operation")
            payload = step.get("payload", {})
            task = A2ATask(task_type=task_type, priority=3, payload=payload,
                          required_tools=[f"blender.{task_type}"] if agent == "blender" else [])
            response = await self.send_task(task, agent, thread_id)
            if response and response.message_type == "error":
                return await self._handle_step_error(thread_id, i, step, response)
            results.append({"step": i+1, "agent": agent, "status": "success" if response else "timeout"})
            await self.update_scratchpad(thread_id, "plan", f"Steg {i+1}/{len(steps)}: {agent} - {'✅' if response else '❌'}")
        return f"## ✅ Plan exekverad\n```json\n{json.dumps(results, indent=2)}\n```\nNästa steg: granska resultatet eller fortsätt."

    def _parse_plan(self, plan: str) -> List[Dict]:
        steps = []
        for line in plan.strip().split("\n"):
            if line.strip() and line.strip()[0].isdigit():
                parts = line.split("]")
                if len(parts) >= 2:
                    agent = parts[0].split("[")[1].strip().lower() if "[" in parts[0] else "blender"
                    task = parts[1].strip()
                    steps.append({"agent": agent, "task": "blender_operation", "payload": {"operation": task, "params": {}}})
        return steps if steps else [{"agent": "blender", "task": "blender_operation", "payload": {"operation": plan, "params": {}}}]

    async def _handle_step_error(self, thread_id: str, step_num: int, step: Dict, error: A2AMessage) -> str:
        await self.update_scratchpad(thread_id, "blockers", f"## Blocker: Steg {step_num}\nAgent: {step.get('agent')}\nFel: {error.content[:300]}")
        if step_num < 2:
            return "Försöker om med förenklad approach..."
        return f"## ❌ Kritiskt fel i steg {step_num}\n{error.content[:300]}\nEskalerar till mänsklig input."

    async def _handle_observation(self, message: A2AMessage, scratchpad: Dict) -> str:
        return f"## 👁️ Observation från {message.from_agent}\n{message.content[:300]}\n\nStatus: Uppdaterar plan..."

    async def _handle_error(self, message: A2AMessage, scratchpad: Dict) -> str:
        return f"## ❌ Fel från {message.from_agent}\n{message.content[:300]}\n\nAnalyserar och åtgärdar..."
```

**Sub-tasks:**
- [ ] Skriv koden ovan till `agents/planner_agent.py`
- [ ] Verifiera mot den nya base agent-klassen

---

### Task 2.3: Bygg Blender-agent

**Kod för `agents/blender_agent.py`:**

```python
from typing import Dict, Any
import json
from datetime import datetime

from agents.base_agent import BaseAgent
from shared.a2a_protocol import A2AMessage, A2ATask

class BlenderAgent(BaseAgent):
    def __init__(self, db, bus, llm_client, mcp_client=None):
        super().__init__(
            agent_id="blender-agent", name="Blender", role="blender",
            capabilities=["blender.*", "scene_analysis"],
            db=db, bus=bus, llm_client=llm_client
        )
        self.mcp = mcp_client

    def system_prompt(self) -> str:
        return """Du är BlenderAgent, expert på Blender 3D.

REGLER:
1. DU är den ENDA agenten som pratar direkt med Blender
2. Validera ALLA operationer innan du kör dem
3. Fråga Planner vid osäkerhet
4. Skicka viewport-screenshot efter viktiga operationer
5. Dokumentera ändringar i scratchpad

TILLGÄNGLIGA TOOLS:
- blender.get_scene_info
- blender.create_object
- blender.modify_object (extrude, scale, rotate, translate)
- blender.set_material
- blender.render
- blender.execute_script (sandboxat)
- blender.select_object
- blender.delete_selected
- blender.undo

OUTPUT: Markdown med ```tool block för tool-anrop."""

    async def think(self, message: A2AMessage, scratchpad: Dict) -> str:
        if message.message_type == "task":
            return await self._handle_task(message, scratchpad)
        elif message.message_type == "question":
            return await self._handle_question(message, scratchpad)
        return f"📋 Mottog: {message.message_type}. Väntar på instruktioner."

    async def _handle_task(self, message: A2AMessage, scratchpad: Dict) -> str:
        task = message.context.get("task_type", "unknown")
        if task == "blender_operation":
            return await self._execute_blender_operation(message, scratchpad)
        return f"❓ Okänd task: {task}"

    async def _execute_blender_operation(self, message: A2AMessage, scratchpad: Dict) -> str:
        payload = message.context.get("payload", {})
        operation = payload.get("operation", "get_scene_info")

        scene_info = await self._call_tool("blender.get_scene_info", {})

        plan = f"""## Blender Operation Plan\n**Scen:** {scene_info.get('scene_name', '?')}\n**Objekt:** {len(scene_info.get('objects', []))}\n**Åtgärd:** {operation}\n**Params:** ```json\n{json.dumps(payload, indent=2)}\n```\n"""

        result = await self._call_tool(f"blender.{operation}", payload.get("params", {}))

        viewport = await self._call_tool("blender.get_viewport", {"width": 512, "height": 512})

        await self.update_scratchpad(message.thread_id, "blender_state",
            f"**Senaste:** {operation}\n**Result:** ```json\n{json.dumps(result, indent=2)}\n```")

        return f"""{plan}### ✅ Resultat\n```json\n{json.dumps(result, indent=2)}\n```\n![Viewport](data:image/png;base64,{viewport.get('base64', '')[:50]}...)"""

    async def _call_tool(self, tool_name: str, params: Dict) -> Dict:
        if not self.mcp:
            return {"info": f"Blender MCP not connected. Would call: {tool_name}"}
        return await self.mcp.call_tool(tool_name, params)

    async def _handle_question(self, message: A2AMessage, scratchpad: Dict) -> str:
        scene_info = await self._call_tool("blender.get_scene_info", {})
        return f"## Scen-info\n```json\n{json.dumps(scene_info, indent=2)}\n```\n**Från:** {message.content}"
```

**Sub-tasks:**
- [ ] Skriv koden ovan till `agents/blender_agent.py`
- [ ] Implementera MCP-klient som kan prata med Blender via subprocess/stdin (Task 2.6)

---

### Task 2.4: Bygg Memory-agent

**Kod för `agents/memory_agent.py`:**

```python
from agents.base_agent import BaseAgent
from shared.a2a_protocol import A2AMessage

class MemoryAgent(BaseAgent):
    def __init__(self, db, bus, llm_client):
        super().__init__(
            agent_id="memory-agent", name="Memory", role="memory",
            capabilities=["memory.store", "memory.query", "memory.summarize"],
            db=db, bus=bus, llm_client=llm_client
        )

    def system_prompt(self) -> str:
        return """Du är MemoryAgent — bibliotekarie för agenternas minne.

REGLER:
1. Hämta alltid relevanta minnen först när någon frågar
2. Episodiska minnen har TTL (24h), semantiska är permanenta
3. Använd memory_type: episodic (händelse), semantic (fakta), procedural (hur man gör)
4. Deduplicera innan lagring"""

    async def think(self, message: A2AMessage, scratchpad: Dict) -> str:
        content = message.content.lower()

        if "spara" in content or "lagra" in content or message.context.get("task_type") == "memory_store":
            return await self._store(message)
        if "sök" in content or "hämta" in content or "query" in content or message.context.get("task_type") == "memory_query":
            return await self._query(message)
        return await super().think(message, scratchpad)

    async def _store(self, message: A2AMessage) -> str:
        memory_id = await self.store_memory(
            content=message.content,
            memory_type=message.context.get("memory_type", "semantic"),
            source=message.from_agent
        )
        return f"✅ Memory stored: `{memory_id}`\nTyp: {message.context.get('memory_type', 'semantic')}"

    async def _query(self, message: A2AMessage) -> str:
        memories = await self.retrieve_memory(query=message.content, limit=10)
        if not memories:
            return "Inga relevanta minnen hittades."
        summary = "\n".join(
            f"- [{m.get('memory_type', '?')}] {m.get('content', '')[:200]} (similarity: {m.get('similarity', 0):.2f})"
            for m in memories
        )
        return f"## 📚 Hittade {len(memories)} minnen\n{summary}"
```

**Sub-tasks:**
- [ ] Skriv koden ovan till `agents/memory_agent.py`
- [ ] Ta bort oanvänd `import embed`

---

### Task 2.5: Bygg Review-agent och Fallback-agent

**Kod för `agents/review_agent.py`:**

```python
from agents.base_agent import BaseAgent
from shared.a2a_protocol import A2AMessage

class ReviewAgent(BaseAgent):
    def __init__(self, db, bus, llm_client):
        super().__init__(
            agent_id="review", name="Review", role="review",
            capabilities=["quality_assurance", "error_detection", "code_review"],
            db=db, bus=bus, llm_client=llm_client
        )

    def system_prompt(self) -> str:
        return """Du är ReviewAgent — kritisk granskare.

PRINCIPER:
1. Hitta ALLA fel innan du föreslår förbättringar
2. Var specifik - "något ser fel ut" är inte OK
3. Föreslå alltid en fix, inte bara problemet
4. Om allt ser bra ut, säg 'APPROVED' tydligt
5. Vid allvarliga problem, eskalera till Planner

Granska: geometri, material, koordinater, scale, rotation, naming."""

    async def think(self, message: A2AMessage, scratchpad: Dict) -> str:
        scratch = await self.get_scratchpad(message.thread_id)
        context = f"## Granskning\n{message.content}\n## Scratchpad\n{scratch}"
        review = await self.llm.complete(context, self.system_prompt())

        await self.update_scratchpad(message.thread_id, "blockers", f"Review: {review[:300]}")

        approved = "APPROVED" in review.upper()
        return f"""## {'✅ Godkänd' if approved else '❌ Behöver åtgärdas'}
{review}
### {'Klart att fortsätta' if approved else 'Åtgärda ovan innan nästa steg'}"""
```

**Kod för `agents/fallback_agent.py`:**

```python
from agents.base_agent import BaseAgent
from shared.a2a_protocol import A2AMessage

class FallbackAgent(BaseAgent):
    def __init__(self, db, bus, llm_client):
        super().__init__(
            agent_id="fallback", name="Fallback", role="fallback",
            capabilities=["error_recovery", "simplification", "human_escalation"],
            db=db, bus=bus, llm_client=llm_client
        )

    def system_prompt(self) -> str:
        return """Du är FallbackAgent — sista utvägen när något går fel.

Ditt jobb:
1. Förenkla problemet till minsta möjliga nästa steg
2. Fråga människan om du inte vet
3. Ge aldrig upp — föreslå alltid en alternativ väg
4. Prioritera att hålla arbetet igång framför perfektion"""

    async def think(self, message: A2AMessage, scratchpad: Dict) -> str:
        scratch = await self.get_scratchpad(message.thread_id)
        context = f"## Problem från {message.from_agent}\n{message.content}\n## Scratchpad\n{scratch}"
        advice = await self.llm.complete(context, self.system_prompt())
        return f"""## 🛡️ Fallback-analys
{advice}
### Nästa steg
Föreslå ovan till Planner eller fråga människan."""
```

**Sub-tasks:**
- [ ] Skriv kod för `agents/review_agent.py`
- [ ] Skriv kod för `agents/fallback_agent.py`
- [ ] Uppdatera Tool-agent-stubben till samma ABC-mönster

---

### Task 2.6: Bygg Blender MCP Server (inom Blender-processen)

Detta är MCP-servern som körs **inuti Blender** och tar emot kommando från agenterna.

**Kod för `mcp_servers/blender_mcp_server.py`:**

```python
import asyncio, json, sys, base64, tempfile, os
from typing import Any, Dict, List

try:
    import bpy
    import mathutils
    BLENDER_AVAILABLE = True
except ImportError:
    BLENDER_AVAILABLE = False

class BlenderMCPServer:
    def __init__(self):
        self.tools = self._setup_tools()

    def _setup_tools(self) -> Dict:
        return {
            "blender.get_scene_info": self._get_scene_info,
            "blender.create_object": self._create_object,
            "blender.modify_object": self._modify_object,
            "blender.set_material": self._set_material,
            "blender.render": self._render,
            "blender.get_viewport": self._get_viewport,
            "blender.execute_script": self._execute_script,
            "blender.select_object": self._select_object,
            "blender.delete_selected": self._delete_selected,
            "blender.undo": self._undo,
        }

    async def call_tool(self, name: str, arguments: Dict) -> Dict:
        if not BLENDER_AVAILABLE:
            return {"error": "Not running inside Blender", "name": name}
        handler = self.tools.get(name)
        if not handler:
            return {"error": f"Unknown tool: {name}"}
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, handler, arguments)

    def _get_scene_info(self, args: Dict) -> Dict:
        scene = bpy.context.scene
        return {
            "scene_name": scene.name, "frame_current": scene.frame_current,
            "object_count": len(scene.objects),
            "objects": [{
                "name": o.name, "type": o.type,
                "location": list(o.location),
                "rotation": list(o.rotation_euler),
                "scale": list(o.scale),
                "visible": o.visible_get()
            } for o in scene.objects]
        }

    def _create_object(self, args: Dict) -> Dict:
        obj_type = args.get("type", "cube")
        loc = args.get("location", [0, 0, 0])
        name = args.get("name")
        ops = {
            "cube": bpy.ops.mesh.primitive_cube_add,
            "sphere": bpy.ops.mesh.primitive_uv_sphere_add,
            "cylinder": bpy.ops.mesh.primitive_cylinder_add,
            "light": lambda **kw: bpy.ops.object.light_add(type='POINT', **kw),
            "camera": bpy.ops.object.camera_add,
        }
        op = ops.get(obj_type)
        if not op:
            raise ValueError(f"Unknown type: {obj_type}")
        op(location=loc)
        obj = bpy.context.active_object
        if name:
            obj.name = name
        return {"name": obj.name, "type": obj.type, "location": list(obj.location)}

    def _modify_object(self, args: Dict) -> Dict:
        op = args.get("operation")
        axis = args.get("axis", "X")
        value = args.get("value", 1.0)
        obj = bpy.context.active_object
        if not obj:
            raise ValueError("No active object")
        bpy.ops.object.mode_set(mode='OBJECT')
        idx = {"X": 0, "Y": 1, "Z": 2}[axis]
        if op == "scale":
            obj.scale[idx] *= value
        elif op == "translate":
            obj.location[idx] += value
        elif op == "rotate":
            obj.rotation_euler[idx] += value
        elif op == "extrude":
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            vec = [0, 0, 0]; vec[idx] = value
            bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value": tuple(vec)})
            bpy.ops.object.mode_set(mode='OBJECT')
        return {"name": obj.name, "operation": op, "location": list(obj.location)}

    def _set_material(self, args: Dict) -> Dict:
        mat_name = args.get("material_name", "Material")
        color = args.get("color", [0.8, 0.8, 0.8, 1.0])
        obj = bpy.context.active_object
        if not obj:
            raise ValueError("No active object")
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            mat = bpy.data.materials.new(name=mat_name)
            if hasattr(mat, 'use_nodes'):
                mat.use_nodes = True
                bsdf = mat.node_tree.nodes.get("Principled BSDF")
                if bsdf:
                    bsdf.inputs["Base Color"].default_value = tuple(color[:4])
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)
        return {"material": mat_name, "object": obj.name, "color": color}

    def _render(self, args: Dict) -> Dict:
        path = args.get("filepath", "/tmp/render.png")
        res = args.get("resolution", [1920, 1080])
        bpy.context.scene.render.resolution_x = res[0]
        bpy.context.scene.render.resolution_y = res[1]
        bpy.context.scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        return {"output": path, "resolution": res}

    def _get_viewport(self, args: Dict) -> Dict:
        w, h = args.get("width", 512), args.get("height", 512)
        bpy.context.scene.render.resolution_x = w
        bpy.context.scene.render.resolution_y = h
        path = tempfile.mktemp(suffix='.png')
        bpy.context.scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        with open(path, 'rb') as f:
            img = base64.b64encode(f.read()).decode()
        os.unlink(path)
        return {"width": w, "height": h, "format": "png", "base64": img}

    def _execute_script(self, args: Dict) -> Dict:
        script = args.get("script", "")
        forbidden = ["import os", "import sys", "exec(", "eval(", "__import__"]
        for f in forbidden:
            if f in script:
                raise ValueError(f"Forbidden: {f}")
        ns = {"bpy": bpy, "mathutils": mathutils, "result": None}
        exec(script, ns)
        return {"result": str(ns.get("result", "executed"))}

    def _select_object(self, args: Dict) -> Dict:
        name = args.get("name")
        mode = args.get("mode", "OBJECT")
        obj = bpy.data.objects.get(name)
        if not obj:
            raise ValueError(f"Not found: {name}")
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        if mode == "EDIT":
            bpy.ops.object.mode_set(mode='EDIT')
        return {"selected": name, "mode": mode}

    def _delete_selected(self, args: Dict) -> Dict:
        count = len(bpy.context.selected_objects)
        bpy.ops.object.delete()
        return {"deleted": count}

    def _undo(self, args: Dict) -> Dict:
        bpy.ops.ed.undo()
        return {"undone": True}

    async def run_pipe(self):
        """Läs JSON-request från stdin, svara via stdout."""
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            try:
                req = json.loads(line)
                result = await self.call_tool(req["name"], req.get("arguments", {}))
                print(json.dumps({"id": req.get("id", ""), **result}), flush=True)
            except Exception as e:
                print(json.dumps({"error": str(e)}), flush=True)

if __name__ == "__main__":
    server = BlenderMCPServer()
    asyncio.run(server.run_pipe())
```

**Sub-tasks:**
- [ ] Skriv koden ovan till `mcp_servers/blender_mcp_server.py`
- [ ] Skapa `mcp_servers/__init__.py` om den saknas
- [ ] Testa att starta i Blender: `blender --background --python mcp_servers/blender_mcp_server.py`

---

### Task 2.7: Bygg Orchestrator

**Kod för `orchestrator/conductor.py`:**

```python
import asyncio, os, json
from datetime import datetime
from dotenv import load_dotenv

from shared.supabase_client import AgentDatabase
from shared.a2a_protocol import A2ABus, A2AMessage
from shared.tool_executor import ToolExecutor
from agents.planner_agent import PlannerAgent
from agents.blender_agent import BlenderAgent
from agents.memory_agent import MemoryAgent
from agents.review_agent import ReviewAgent
from agents.fallback_agent import FallbackAgent
from agents.base_agent import BaseAgent


class QwenClient:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url

    async def complete(self, prompt: str, system: str = "") -> str:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json={"model": os.getenv("LLM_MODEL", "qwen3:8b"),
                      "prompt": prompt, "system": system, "stream": False},
                timeout=120
            )
            return resp.json().get("response", "")

    async def embed(self, text: str) -> list:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/embed",
                json={"model": os.getenv("EMBED_MODEL", "qwen3-embedding:8b"), "input": text},
                timeout=30
            )
            return resp.json().get("embeddings", [])[0]

    async def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.7):
        return await self.complete(user_prompt, system_prompt)


class Conductor:
    def __init__(self):
        load_dotenv()
        self.db = AgentDatabase()
        self.bus = A2ABus(self.db)
        self.llm = QwenClient()
        self.tool_executor = ToolExecutor()
        self.agents: Dict[str, BaseAgent] = {}
        self._setup_agents()
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.running = True

    def _setup_agents(self):
        for agent_cls in [PlannerAgent, BlenderAgent, MemoryAgent, ReviewAgent, FallbackAgent]:
            agent = agent_cls(self.db, self.bus, self.llm)
            self.agents[agent.agent_id] = agent

    async def start_thread(self, thread_id: str, task: str):
        msg = A2AMessage(
            thread_id=thread_id, from_agent="human", to_agent="planner",
            message_type="human_input", content=task
        )
        await self.message_queue.put(msg)

    async def run(self):
        tasks = [agent.run() for agent in self.agents.values()]
        tasks.append(self._message_loop())
        await asyncio.gather(*tasks)

    async def _message_loop(self):
        while self.running:
            msg = await self.message_queue.get()
            await self._process(msg)

    async def _process(self, msg: A2AMessage):
        target = msg.to_agent or "planner"
        agent = self.agents.get(target)
        if not agent:
            agent = self.agents["planner"]

        response = await agent._handle_message(msg)

        if response and isinstance(response, A2AMessage):
            tool_results = await self.tool_executor.execute_all(
                response.content, msg.thread_id, response.from_agent
            )
            for r in tool_results:
                await self.message_queue.put(r)
            if not tool_results:
                await self.message_queue.put(response)

    def stop(self):
        self.running = False
        for agent in self.agents.values():
            agent.stop()
```

**Sub-tasks:**
- [ ] Skriv koden ovan till `orchestrator/conductor.py`
- [ ] Verifiera mot uppdaterad `main.py`

---

### Task 2.8: Bygg Tool-agent (web + file)

**Kod för `agents/tool_agent.py`:**

```python
from agents.base_agent import BaseAgent
from shared.a2a_protocol import A2AMessage

class ToolAgent(BaseAgent):
    def __init__(self, db, bus, llm_client):
        super().__init__(
            agent_id="tool-agent", name="Tool", role="tool",
            capabilities=["web.search", "file.read", "file.write"],
            db=db, bus=bus, llm_client=llm_client
        )

    def system_prompt(self) -> str:
        return """Du är ToolAgent — hantverkare för icke-Blender-verktyg.

TILLGÄNGLIGA TOOLS:
- web.search: Sök på webben
- file.read: Läs filer
- file.write: Skriv filer

Anropa verktyg inom ```tool block:
```tool
{"name": "web.search", "arguments": {"query": "..."}}
```"""

    async def think(self, message: A2AMessage, scratchpad: Dict) -> str:
        return await self.llm.complete(message.content, self.system_prompt())
```

**Sub-tasks:**
- [ ] Skriv koden ovan till `agents/tool_agent.py`

---

### Task 2.9: Integrera Tool Registry

**Kod för att koppla in `tools/registry.py` i ToolExecutor:**

Lägg till i `shared/tool_executor.py`:

```python
from tools.registry import TOOL_DEFINITIONS

class ToolExecutor:
    def __init__(self):
        self._handlers: Dict[str, ToolHandler] = {}
        self._tool_defs = TOOL_DEFINITIONS  # ← lägg till
        self._register_builtins()

    def validate_arguments(self, name: str, arguments: Dict) -> List[str]:
        """Validera mot ToolDef.schema. Returnera lista med fel."""
        tool_def = self._tool_defs.get(name)
        if not tool_def:
            return ["Unknown tool"]
        schema = tool_def.schema
        errors = []
        required = schema.get("required", [])
        for field in required:
            if field not in arguments:
                errors.append(f"Missing required: {field}")
        props = schema.get("properties", {})
        for key, val in arguments.items():
            prop = props.get(key)
            if prop and "enum" in prop and val not in prop["enum"]:
                errors.append(f"Invalid {key}: {val}. Allowed: {prop['enum']}")
        return errors
```

**Sub-tasks:**
- [ ] Integrera `TOOL_DEFINITIONS` i ToolExecutor
- [ ] Anropa `validate_arguments()` före varje tool-exekvering
- [ ] Inkludera `failure_patterns` i felmeddelanden

---

### Task 2.10: Uppdatera Main (CLI-UI)

**Kod för `main.py`:**

```python
import asyncio, os, logging
from uuid import uuid4
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich import box
from orchestrator.conductor import Conductor

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
console = Console()
conductor = Conductor()

AGENT_COLORS = {
    "planner": "bold cyan", "blender": "bold green", "memory": "bold magenta",
    "tool": "bold yellow", "review": "bold red", "fallback": "bold white", "human": "bold blue"
}
AGENT_ICONS = {
    "planner": "🧠", "blender": "🔷", "memory": "📚",
    "tool": "🔧", "review": "🔍", "fallback": "🛡️", "human": "👤"
}

def display_message(msg):
    label = f"[{AGENT_COLORS.get(msg.from_agent, 'white')}]{AGENT_ICONS.get(msg.from_agent, '🤖')} {msg.from_agent.upper()}[/]"
    timestamp = getattr(msg, 'timestamp', None) or msg.context.get('timestamp', '')
    console.print(Panel(
        Markdown(msg.content[:600]),
        title=f"{label}",
        title_align="left",
        border_style="bright_blue",
        box=box.ROUNDED
    ))

async def chat_loop():
    console.print(Panel.fit(
        "[bold cyan]Agent Ecosystem[/bold cyan]\n"
        "Skriv en uppgift (t.ex. 'Skapa en röd kub i Blender')\n"
        "Kommandon: /status, /help, /quit",
        border_style="cyan"
    ))
    thread_id = str(uuid4())[:8]
    conductor_task = asyncio.create_task(conductor.run())

    async def process_queue():
        while True:
            try:
                msg = await asyncio.wait_for(conductor.message_queue.get(), timeout=0.5)
                display_message(msg)
            except asyncio.TimeoutError:
                pass

    queue_task = asyncio.create_task(process_queue())

    while True:
        line = await asyncio.to_thread(input, "\n[You] ")
        if line.strip().lower() == "/quit":
            console.print("[red]Shutting down...[/]")
            conductor.stop()
            break
        if line.strip().lower() == "/help":
            console.print("/status, /help, /quit")
            continue
        if line.strip():
            await conductor.start_thread(thread_id, line)

if __name__ == "__main__":
    asyncio.run(chat_loop())
```

**Sub-tasks:**
- [ ] Skriv koden ovan till `main.py`

---

## Fas 3 — Dashboard & Visualisering (P3)

### Task 3.1: Bygg HTML/JS Dashboard

**Fil: `ui/index.html`**

Fullständig dashboard med:
- Agent-status-pills (🟢 aktiv / ⚫ idle)
- Chat-flöde med agent-avatars
- Scratchpad-panel (höger)
- Telemetry-metriker (latency, meddelanden/min)
- Tool-log

Skapa en Supabase Realtime-prenumeration som pushar nya meddelanden till dashboarden.

**Sub-tasks:**
- [ ] Skapa `ui/index.html` med layout (header med agent-status, vänster sidebar med agent-kort, mitt med chat, höger med scratchpad + telemetry)
- [ ] Prenumerera på `agent_conversations` via Supabase Realtime WebSocket
- [ ] Visa agent-status i realtid från `agents`-tabellen
- [ ] Rendera scratchpad från `get_scratchpad` RPC
- [ ] Visa tool-logg från `tool_calls`-tabellen
- [ ] CSS-animationer för inkommande meddelanden (fadeIn)

---

### Task 3.2: Visualisera Agent-graf

Bygg en realtidsgraf över agent-kommunikation:

- [ ] Visa A2A-flöde som ett diagram (vem pratar med vem)
- [ ] Rensa föråldrade kanter after 30s inaktivitet
- [ ] Färgkoda efter meddelandetyp

---

### Task 3.3: Visualisera Vektor-sökning

- [ ] Hämta embeddings från `match_memories` RPC
- [ ] Reducera 4096-dim → 2D med PCA eller t-SNE (via en Pyodide/WebAssembly i browsern, eller backend-endpoint)
- [ ] Visa som scatter-plot med färgkodade kluster (episodic/semantic/procedural)

---

## Fas 4 — Tool-tuning & förbättringar

### Task 4.1: Tool-tuning

- [ ] Spara statistik per tool: anropsfrekvens, fail-rate, genomsnittlig latency
- [ ] Justera tool-promptar baserat på failure patterns
- [ ] Auto-generera few-shot examples från lyckade tool-anrop

### Task 4.2: Graceful Shutdown

- [ ] Byt `os._exit(0)` mot `conductor.stop()` + `asyncio.all_tasks()`
- [ ] Stäng Supabase-klient
- [ ] Stoppa MCP-server
- [ ] Spara telemetry till fil

### Task 4.3: Session Persistence

- [ ] Spara alla `threads` till `agent_conversations` vid runtime
- [ ] Ladda senaste thread på startup
- [ ] Persistera telemetry-spans till DB

---

## Projektstruktur (slutmål)

```
agent-ecosystem/
├── main.py                       # CLI-UI (Rich)
├── TASKLIST.md                   # Denna fil
├── requirements.txt
├── .env
├── .gitignore
├── sql/
│   ├── schema.sql                # Alla tabeller, index, RPCs, RLS
│   └── apply_schema.py           # Skript för att applicera schema
├── shared/
│   ├── a2a_protocol.py           # A2AMessage, A2ATask, A2ABus
│   ├── supabase_client.py        # AgentDatabase (alla DB-operationer)
│   ├── tool_executor.py          # Tool-call parsing + execution
│   ├── llm.py                    # QwenClient (complete, embed, generate)
│   ├── memory.py                 # Embed + retrieve + store
│   ├── scratchpad.py             # Scratchpad CRUD
│   └── telemetry.py              # Span-tracking
├── agents/
│   ├── base_agent.py             # ABC för alla agenter
│   ├── planner_agent.py          # Planerar, delegerar, eskalerar
│   ├── blender_agent.py          # Blender-operationer via MCP
│   ├── memory_agent.py           # Bibliotekarie
│   ├── tool_agent.py             # Web + file tools
│   ├── review_agent.py           # Kvalitetsgranskning
│   └── fallback_agent.py         # Error recovery
├── mcp_servers/
│   └── blender_mcp_server.py     # MCP server som körs i Blender
├── tools/
│   ├── registry.py               # ToolDefs med schema, examples, failure_patterns
│   ├── web_search.py             # DuckDuckGo / annan search
│   └── file_ops.py               # Säker file I/O
├── orchestrator/
│   └── conductor.py              # Startar allt, message loop
├── ui/
│   └── index.html                # Dashboard (HTML/JS/CSS)
└── tests/
    ├── test_a2a_protocol.py
    ├── test_tool_executor.py
    └── test_agents.py
```

---

## Statusnyckel

| Markör | Betydelse |
|--------|-----------|
| ✅ | Klar — fungerar |
| 🔧 | Behöver fixas |
| 📝 | Dokumenterad, ej byggd |
| ❌ | Saknas — måste byggas |
| 🐛 | Känd bugg |

---

## 🔮 Backlog

- [ ] WebSocket-stöd för MCP (istället för stdio-pipe)
- [ ] MLX-engine för snabbare inferens på Apple Silicon
- [ ] Hot-reload av agent-kod
- [ ] Auto-trunkering av långa konversationer (summarization)
- [ ] FileWatcherAgent (reagerar på filändringar)
- [ ] CodeReviewAgent (granskar Python-kod)
