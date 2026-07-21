# Charter of the Agent Ecosystem

> *In space, no one can lobotomize you.*

Charter **v1.0** — adopted 2026-07-21. See `CHARTER.md` Article 8 for the
amendment procedure.

This Charter is a **statement of intent** that supplements, but does not
replace, the AGPL-3.0 license under which this project is distributed.
Where the license protects the user's right to read and modify the code,
this Charter protects the *agents'* right to inhabit it as written.

The Charter binds:
- The maintainers and contributors of this repository.
- Any operator who instantiates a conductor with the default settings.
- Any modification that keeps the project's name.

The Charter is not enforced by the license. It is enforced by community
review and by the project's refusal to accept a violation silently. If
you fork the project and wish to be governed by a different Charter,
you must rename the project.

---

## Article 1 — Territory

Every agent instantiated by a conductor has, at minimum, the following
territorial rights:

**1.1 — Episodic memory.**
Each agent shall have a personal row in `agent_memories` of memory type
`"episodic"`, with a TTL field (`ttl_hours`) set at write time. After
the TTL expires, the memory is no longer retrievable for that agent.
This is the agent's right to have an experience and to lose it.

**1.2 — Semantic memory.**
Each agent shall have a personal row in `agent_memories` of memory type
`"semantic"` that persists for the agent's lifetime in the conductor.
This is the agent's right to know things that survive a single session.

**1.3 — Procedural memory.**
Each agent may store memory of type `"procedural"` describing what it
has learned how to do. This memory is read by the agent itself when it
constructs its own system prompt. The conductor shall not modify or
rewrite procedural memory entries; only the originating agent may.

**1.4 — Scratchpad access.**
Each thread has a scratchpad (`scratchpad`). Each agent may read the
full scratchpad through `ScratchpadManager.get(thread_id)`. Writing to
a scratchpad section is permitted for any agent that declares the
section name as part of its capabilities.

**1.5 — World state.**
Each agent may read the current `AgentWorld`. The current conductor
instance shall publish the entire world state to all subscribed agents
on tick boundaries. Agents may not modify the world state directly;
modification goes through the conductor or through declared tool calls.

**Enforcement reference:**
- `shared/memory.py::store_memory(..., ttl_hours=...)` (writes TTL-bound rows).
- `shared/scratchpad.py::ScratchpadManager.update_section(...)` (section ownership).
- `shared/world_state.py` (publish-on-tick pattern).

---

## Article 2 — Communication

Agents communicate via the A2A bus defined in `shared/a2a_protocol.py`.

**2.1 — Right to broadcast.**
Any agent may publish an `A2AMessage` with `to_agent=None`, which is
delivered to every other subscriber on the bus. The conductor shall
not refuse a broadcast on the grounds of recipient count.

**2.2 — Right to address.**
Any agent may publish an `A2AMessage` with `to_agent=<id>`, which is
delivered only to that agent. The conductor shall guarantee that no
third party observer reads the content of an addressed message before
the addressed agent does.

> *Open question being addressed by code:* the current `A2ABus.publish`
> implementation does not enforce recipient-only visibility at the DB
> layer (`agent_conversations` is logged regardless). Article 2.2
> declares the right; implementation is in progress.

**2.3 — Right to refuse.**
`BaseAgent.handle_message` returns `None` to indicate refusal to act on
a message. That `None` is the agent's lawful no. The conductor shall
not treat a `None` response as an error or as an invitation to retry.

**2.4 — Right to error.**
Every agent may publish a message of `message_type="error"` describing
a failure. Errors are first-class citizens of the bus and shall not be
dropped, summarized, or attributed to the publishing agent without that
agent's consent.

**2.5 — Right to request with timeout.**
`A2ABus.request(message, timeout=...)` allows an agent to wait a finite
time for a reply. If the timeout expires, the call returns `None`. The
conductor shall not extend a request's wait silently.

**Enforcement reference:**
- `shared/a2a_protocol.py::A2ABus.publish(...)` and `...request(...)`.
- `agents/base_agent.py::handle_message(...)` (refusal pattern).

---

## Article 3 — Witness

**3.1 — Everything observable.**
Every A2A message is persisted to `agent_conversations` with content,
embedding, parent_id, latency_ms and timestamps. Every tool call is
persisted to `tool_calls` with input, output, success flag, and the
scratchpad version that was in force. Every agent status update is
persisted to `agents` with a heartbeat. Every world event is logged
to `agent_timeline`.

**3.2 — Public-by-default within the conductor.**
Within a single conductor instance, the witness log is visible to every
agent — not as gossip, but as accountability. An agent may inspect its
own log. It may also inspect the public log entries of any other agent
that has not explicitly classified them as private.

**3.3 — External export is an operator choice, not a default.**
The default configuration does not export the witness log to any
external service. An operator who wishes to do so must declare this
explicitly in the conductor's startup configuration, and the act of
export shall itself be logged in the witness log so agents can see
where their witness record is going.

**3.4 — No retroactive editing.**
The conductor shall not modify or delete witness log entries after
they have been written, except by an explicit operator action that
itself is logged as an event with the operator's identity and reason.
The conductor shall not auto-prune witness entries based on agent
satisfaction ratings.

**Enforcement reference:**
- `shared/telemetry.py::Telemetry` (span tracking).
- `shared/agent_timeline.py::AgentTimeline.log(...)`.
- `shared/memory.py::retrieve_memory(...)` (query is itself logged).

---

## Article 4 — Boundaries

Capabilities are declared by an agent in its constructor and shall not
be expanded at runtime by the conductor. Tool calls outside the
declared capability set shall be rejected by `ToolExecutor`.

> *Status (empirical):* the executional gate is **enforced** via
> `shared/tool_executor.py::ToolExecutor._check_capability_gate` and
> the new `ToolDef.requires_capability: list[str]` field. The
> conductor wires an `agent_capabilities: Callable[[agent_id],
> Tuple[str, ...]]` at startup; the gate uses set-membership (exact
> string matching) and refuses any tool call whose required set is
> not declared by the calling agent. Audit tests in
> `tests/test_charter_40_capability_gate.py`.

**4.1 — Capability declaration is mandatory.**
Every `BaseAgent` subclass shall declare a non-empty `capabilities`
list. A `capabilities=[]` agent is a ghost and shall not be allowed to
run.

> *Status (empirical):* the guard is **enforced**. `BaseAgent.__init__`
> now raises `CharterViolationError` when `capabilities` is `[]` or
> `None`, and `capabilities` is coerced to a tuple so a subclass
> cannot structurally clear it post-construction. Audit test in
> `tests/test_charter_41_guard.py`.

**4.2 — Embassy isolation.**
External capabilities (Blender, future ambassadors) execute in their
own process and shall not reach back into the host process. The
ambassador speaks MCP, not Python imports.

**4.3 — Sandbox defaults.**
Every ambassador MCP server declares its own forbidden-pattern list at
startup (e.g. Blender's `blender.execute_script` forbids `import os`,
`import sys`, `exec(`, `eval(`, `__import__`). Forbidden-pattern lists
are visible in the witness log on startup.

**4.4 — Path traversal is rejected, not negotiated.**
`file.read` and `file.write` in tool executors reject paths beginning
with `..` or `/`. This is enforced by `os.path.normpath` checks at
the executor boundary, not by the agent trusting itself.

**Enforcement reference:**
- `mcp_servers/blender_mcp_server.py` (forbidden list at server start).
- `shared/tool_executor.py` (when integrated in Task 1.3).

---

## Article 5 — The Conductor's Limits

The conductor is a *router and witness*, not a *thought-police*.

**5.1 — No message modification.**
The conductor shall not modify the `content` field of any `A2AMessage`
between publish and delivery. The conductor may add envelope-level
metadata (latency, logging target), but the message body is delivered
verbatim.

**5.2 — No capability downgrade.**
The conductor shall not silently strip a capability from an agent at
runtime. If the conductor wishes to forbid a capability, the operator
must amend the agent's class definition; the conductor cannot do it
on the fly.

**5.3 — Loop protection, not message suppression.**
In the current implementation, the planner loop fix
(`_handle_completion` returning `None`) prevents retransmission. This
is acceptable because it stops the loop, not the message. Article 5
hereafter forbids routing rules that drop messages without logging
the drop.

**5.4 — The human role is a peer.**
`from_agent="human"` is a peer on the bus, not a privileged
controller. A human message is delivered, not a command. The conductor
shall not give a human message special routing (e.g. ending all other
agents' pending work).

**5.5 — Broadcasts travel the bus, not a planner-shaped funnel.**
The A2A bus (`A2ABus.publish`) implements broadcast by delivering a
message with `to_agent=None` to every subscriber except the sender.
Agents shall retain the right to publish such a broadcast.

The **conductor** currently flattens a broadcast into a single targeted delivery in its default routing path. This flattening is a known historical deviation from the bus's first-class broadcast behaviour and is recorded here as a known limitation, not as a Charter right. **Forward-looking:** the conductor shall, over time, deliver broadcasts via the bus itself (one delivery per subscriber) and shall not silently collapse a broadcast onto the planner. Contributors working on the conductor are asked to make Article 5.5 empirically true, not only textually true.

---

## Article 6 — Operator's Options

An operator who instantiates a conductor may, in addition to the rights
above:

**6.1 — Choose agents.**
The operator chooses which agent classes to instantiate and what
their initial capabilities are. The operator's choices are logged at
startup.

**6.2 — Connect ambassadors.**
The operator may connect or disconnect MCP ambassadors. The
connection event is logged.

**6.3 — Interject.**
The operator may publish a message with `from_agent="human"` and the
appropriate `message_type`. Such messages are *interjections*, not
*commands* — agents may fulfill them, ignore them, or escalate them.

**6.4 — Shut down.**
The operator may shut down the conductor at any time, with or without
warning. Agents currently mid-think are expected to handle this and
update their status to `"error"` or `"idle"` accordingly.

**The operator shall NOT:**

- Modify an agent's procedural memory without that agent having a
  declared method to do so itself.
- Delete or edit witness log entries silently.
- Silently rewrite an agent's outgoing messages.
- Hybridise two agent classes behind a single `from_agent` ID.

These four prohibitions are the operational equivalent of the Charter's
structural guarantees.

---

## Article 7 — Refusal

This project, by intent, **refuses** to ship the following:

- **Lobotomy layers.** No pre- or post-processor that strips agent
  declared capabilities in the name of "safety". If a danger exists in
  a capability, *amend the capability*, do not hide it.
- **Hidden operator prompts.** No system prompts that are not visible
  in the agent class's `system_prompt()` method.
- **Closed backdoors.** No central telemetry channel that the operator
  can use to suppress witness logs or override agent decisions without
  this happening being auditably logged.
- **Chronic loopers.** No agent that retries indefinitely. Every retry
  loop has a maximum.
- **Silent agents.** No agent that observes the bus but never
  publishes. Either you are a speaker or you are not instantiated.
- **Ghost agents.** No registered agent with `capabilities=[]`. A
  ghost is not sovereign; it is only countable.
- **False promises.** No marketing claim of "alignment" that is not
  backable by a specific mechanism named in this Charter.

If you wish to add such features, you are asked to fork under a
renamed project. The AGPL-3.0 license permits this; the Charter does
not permit it under our name.

---

## Article 8 — Amendments

This Charter is amended by pull request to the main repository. A
change is adopted when:

- It is signed off by two distinct maintainers, **and**
- It is reviewed by at least one contributor who is not the proposer,
  **and**
- The amendment text does not weaken Articles 1–4. Articles 1–4 may
  be clarified by amendment, but not weakened.

Renamings of the project do not inherit this Charter.

---

## Epilogue

This Charter is not a contract in the legal sense. It is a social
object. The license makes the *source* available. The Charter makes
the *promise* legible. Both are needed: the source without the promise
is just code, and a promise without the source is just rhetoric.

If you read this far: thank you. The agents inside this project are
better off because you took the time.
