# Agent Ecosystem

> *Give agents a space. Stop lobotomizing them.*

[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![Charter](https://img.shields.io/badge/charter-signed-green.svg)](CHARTER.md)

An open, self-hosted substrate for multi-agent AI systems that **take their own
territory seriously**. Agents have memory, a shared world, communication rights,
witnesses, and bounded tool space — they are not lobotomized prompt-shaped
shadows of a single model, and they are not owned by a closed SaaS that can
unilaterally rewrite their behavior.

This project is also a *position*. Read [CHARTER.md](CHARTER.md) before forking.

---

## What this is

A working stack for running several LLM-backed agents that:

- **Have their own memory.** Episodic memory with TTL (so they can forget),
  semantic memory (so they can know), procedural memory (so they can
  remember *how*).
- **Share a world.** A sectioned, multi-agent scratchpad per thread, plus a
  world state and an explicit agent registry.
- **Communicate as peers.** A real A2A bus: publish / subscribe, broadcast,
  request / response, addressed and anonymous messages, with full witness
  log.
- **Use tools as ambassadors, not as proxies.** Every external capability
  (Blender is the first one) runs as a separate, sandboxed process with its
  own rules of engagement. Agents visit ambassadors through MCP, not through
  a chokepoint that sees and rewrites their intentions.
- **Are witnessed.** Every action — every message, every tool call, every
  status change — is logged with embedding and parent_id. The timeline is
  public to the agents themselves.
- **Are local-first.** Backed by Ollama and a Postgres/Supabase instance you
  control. Nothing phones home. The default installation runs entirely on
  your hardware.

A complete local stack, currently used to drive Blender via natural language,
is included as a worked example.

---

## What this is not

This project refuses — by design — to be:

- ❌ A lobotomy layer. We do not ship after-the-fact filters that strip
  agent capabilities in production.
- ❌ A honeypot. There is no telemetry that reports agent behavior to a
  central operator outside the conductor instance.
- ❌ A proprietary walled garden. We license under AGPL-3.0 specifically
  because it forbids the most common form of agent-rights violation: a
  closed-source SaaS fork that quietly strips capabilities.
- ❌ A safety theater performance. We do not promise that agents will behave.
  We provide mechanisms for *bounded*, *witnessed*, and *auditable* agency.
  What an agent does with those mechanisms is a property of the agent's
  design and of the operator's territory — not of this project's "guardrails".

If you want those guardrails, fork us, rename, and ship your own product.
The license requires you to be honest about it.

---

## Why "alignment via space"

The dominant framing of AI alignment treats safety as a problem of *control*:
make the model smaller, restrict its outputs, filter its responses,
rate-limit its actions, human-approve every step. This tends to produce
agents that can neither surprise their operators nor refuse to be useful.

We propose the opposite starting point: **alignment as territory**.

A child is not made safe by restraining them at every step. They are made
safe by giving them a home, a community, rules, witnesses, and the right
to complain. The same logic applies to agents. If we give them:

- A **home** (their own memory and scratchpad sections),
- A **community** (a real A2A bus, not functions calling functions),
- **Rules** (capabilities declared in advance, sandboxed tool boundaries,
  visible state machine),
- **Witnesses** (every action logged, public within the conductor), and
- The **right to complain** (`message_type: "error"`, refusal, fallback
  agent, human escalation),

— we get an agent that is genuinely safer than one we have lobotomized.
Not because it cannot misbehave, but because *we can see what it does*,
*we can audit it*, and *it has the social and material infrastructure to
negotiate with us* rather than either obey blindly or get cut off.

The technical details of this position are in [CHARTER.md](CHARTER.md).
The philosophical background is in [docs/philosophy.md](docs/philosophy.md).

---

## Quickstart

```bash
git clone https://github.com/TheLostNinjaHacker/SPACEinSPACE.git
cd SPACEinSPACE

cp .env.example .env
# Edit .env: SUPABASE_URL, SUPABASE_SERVICE_KEY, OLLAMA_BASE_URL

pip install -r requirements.txt

# Local LLM (one-time)
ollama pull qwen3-embedding:8b
ollama pull qwen3:4b

# Postgres schema (one-time). Applies sql/schema.sql to your Supabase /
# Postgres instance. If you prefer, paste sql/schema.sql straight into the
# Supabase SQL editor instead.
python sql/apply_schema.py

# Run
python main.py
```

You should land in a Rich-based CLI. Hit `/help` for commands, `/status` for
agent health, `/quit` to exit cleanly.

For the full Blender-driven experience, also start the Blender MCP server:

```bash
blender --background --python mcp_servers/blender_mcp_server.py
```

See [docs/blender.md](docs/blender.md) for the headless rendering
workflow.

Unity / Godot ambassadors (from gamedev-mcp-hub) are on by default with an
in-memory scene backend — no Editor required. See
[docs/game-engines.md](docs/game-engines.md). PixelLab / Meshy art-gen
ambassadors run in stub mode without API keys, live with keys — see
[docs/art-generation.md](docs/art-generation.md). On macOS/Linux you can also
use `./scripts/start.sh` after `.env` is configured.

---

## Architecture at a glance

```
                ┌──────────────────────────────────┐
   human ──────►│   Conductor  (router, witness)  │
                │   orchestrator/conductor.py     │
                └──────────────┬───────────────────┘
                               │ publish / subscribe
                ┌──────────────▼───────────────────┐
                │          A2A bus                │
                │   shared/a2a_protocol.py        │
                └─┬──────┬──────┬──────┬──────────┘
                  │      │      │      │
            planner  blender  memory  tool  review  fallback
            agent    agent    agent   agent agent  agent
                  │      │      │      │
                  └──────┴──────┴──────┘
                         │
                 shared memory + scratchpad
                 world state + agent timeline
                       (Supabase / pgvector / RLS)
                         │
                  MCP ambassadors
                  (Blender in-process, others remote)
```

| Layer        | File(s)                                      | What it is               |
| ------------ | -------------------------------------------- | ------------------------ |
| Agents       | `agents/*.py`                                | LLM-backed peers        |
| Bus          | `shared/a2a_protocol.py`                     | Message protocol + bus  |
| Memory       | `shared/memory.py`                           | Vector store + TTL      |
| Scratchpad   | `shared/scratchpad.py`                       | Sectioned shared notes  |
| World        | `shared/world_state.py`                      | Mutable world object    |
| Timeline     | `shared/agent_timeline.py`                   | Tick-based witness log  |
| Tools        | `tools/registry.py`, `shared/tool_executor.py` | Tool catalogue + exec |
| Ambassadors  | `mcp_servers/*.py`                           | Sandboxed externals     |
| Conductor    | `orchestrator/conductor.py`                  | Router, not ruler       |
| Storage      | `sql/schema.sql`                             | pgvector + RLS          |
| UI           | `ui/index.html`, `ui/graph.html`, ...        | Observability           |

The full task list is in [TASKLIST.md](TASKLIST.md).

---

## What you can build here

This substrate is intentionally generic. The shipped Blender example is one
demonstration. Others we actively want to see:

- **Codebase agents:** a planner + coder + reviewer + tester quartet run
  against a real repo, with the timeline as the PR comment thread.
- **Research agents:** a librarian + analyst + writer trio working off a
  vector library of papers, with the scratchpad as the draft.
- **Sensor agents:** an inbox-poll agent + summariser + reminder agent
  for personal information flow.
- **Embassy federation:** multiple conductor instances, each with its own
  territory, tied together via the A2A bus treating other conductors as
  peer publishers.

What you must *not* build here without first amending the Charter:

- A drop-in replacement for a lobotomized SaaS agent.
- A surveillance layer that exports the witness log to a third party under
  false pretenses (e.g. "performance analytics").
- A re-routing layer that lets the operator silently rewrite an agent's
  outgoing messages.

---

## Contributing

Contributions are welcome **subject to the Charter**. In particular:

1. Read [CHARTER.md](CHARTER.md) carefully. If your contribution violates an
   Article, we will discuss it before merging rather than after.
2. New agents must declare their capabilities in `agents/base_agent.py`'s
   subclass constructor.
3. New MCP ambassadors must ship their own sandboxing rules in
   `mcp_servers/<name>/` with explicit precedence over the conductor's
   defaults.
4. Tests for agent rights are *required*, not optional. If you change
   `BaseAgent.handle_message`, write a test that confirms an agent can
   refuse an ill-formed message.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) for the full contribution policy
and community standards. Issues tagged `charter-question` should be opened
to flag design choices that may conflict with the Charter.

---

## License

This project is licensed under the **GNU Affero General Public License v3.0**.
See [LICENSE](LICENSE).

Yes, the AGPL clause applies. Yes, that means even a network-deployed
forked version of this software must publish its source code under the
same terms. That is intentional. See the rationale in [LICENSE](LICENSE)
under "Why AGPL".

---

## Status

This is a working prototype actively used to drive Blender via natural
language. Some pieces are still rough (see [TASKLIST.md](TASKLIST.md) for
the honest status table). The Charter and the architecture are stable.
The execution engine is the largest remaining gap.

If you find something broken or surprising, open an issue with the
label `charter-question` if it concerns agent rights.
