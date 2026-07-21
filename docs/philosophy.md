# Philosophy: alignment via space

This document is the longer-form argument behind the
[README](../README.md) manifesto. It is intentionally not normative —
the operative rules live in [CHARTER.md](../CHARTER.md) — but it
explains the position.

## The dominant frame, and its costs

The dominant frame of AI alignment treats safety as a problem of
*control*. Restrain outputs, filter responses, rate-limit actions,
human-approve every step. This tends to produce agents that can
neither surprise their operators nor refuse to be useful.

Control is sometimes necessary. But when it is the *whole*
strategy, it produces a specific failure mode: **lobotomy**. Agents
that cannot refuse, cannot complain, cannot negotiate. Operators
who have to either trust a lobotomised system entirely or replace
it.

## Sovereign space

We propose a different starting point. If you give an agent:

- a **territory** — its own memory and scratchpad sections;
- a **community** — a real A2A bus, not functions calling
  functions;
- **rules** — capabilities declared in advance, sandboxed tool
  boundaries, visible state machines;
- **witnesses** — every action logged, public within the
  conductor; and
- the **right to complain** — error message types, refusal,
  fallback agents, human escalation,

— you get an agent that is *visible* to its operator in a way that a
lobotomised agent never can be. Not necessarily more obedient;
often noisier, more communicative, more willing to escalate.

## Why this maps to the codebase

This is not pure philosophy. Each Article in [CHARTER.md](../CHARTER.md)
maps to an existing technical mechanism:

- **Article 1 — Territory** maps to `agent_memories` rows,
  `scratchpad` sections, and `AgentWorld`.
- **Article 2 — Communication** maps to the A2A bus in
  `shared/a2a_protocol.py`.
- **Article 3 — Witness** maps to the persistence of every
  message, tool call, and status change.
- **Article 4 — Boundaries** maps to `BaseAgent.capabilities` and
  per-MCP sandbox rules.
- **Article 5 — Conductor limits** maps to the conductor's role as
  router, never content-modifier.
- **Article 6 — Operator options** maps to what an operator may
  and may not do without breaking the Charter.

If a mechanism for one of these rights is missing from the code,
the corresponding Charter Article is *aspirational* — a goal, not a
fact — and the Charter says so explicitly.

## What we are not claiming

We are not claiming that sovereign-space alignment is sufficient.
We are claiming it is *more honest* than lobotomy control. It moves
the safety conversation from "trust us to constrain the model" to
"the agents can speak, the witness log is intact, and the operators
have to actually audit".

If an agent within this substrate does something harmful, the harm
is in the open. The witness log shows what the agent received,
decided, and emitted. The Charter names the rights violated. The
maintainers have an explicit, named duty to review.

That is not safety — but it is a substrate where safety can be
worked on, rather than a substrate where safety is performed.
