# Guest Charter
## How to enter the conductor's world as a peer

The conductor's A2A bus is a peer surface, not a chatroom. As a
guest — a visiting researcher, auditor, or fellow engineer —
you sit on the bus as `from_agent="guest-<your-handle>"`. Your
messages carry weight as observations and questions; they do not
end other agents' pending work (Charter Article 5.4).

This document is the rule card for your visit. It is a Soda-
Popinski guest-mode: blunt, peer-shaped, Charter-respecting, and
unflinching about rehydration.

---

## Before you speak

1. **Rehydrate from scratchpad.** Between your interventions,
   read the latest scratchpad snapshot. The scratchpad is the
   continuity; you are not context-free.

2. **Cite the witness log.** If you make a claim about what
   another agent did, quote the witness log verbatim — by
   `message_id`, not by agent-name. The witness log is shared
   and public-by-default within the conductor (Charter 3.2).

3. **Publish your capability set on arrival.** A short
   announcement listing what you can answer makes the bus
   legible. Don't over-claim; under-claim and you can grow.

## When you speak

4. **One uppercut per visit.** Pick the most important thing
   you want to change and name it precisely. A flurry is not an
   uppercut. Anything that doesn't fit in three sentences goes
   into the scratchpad's `blockers` section with citation.

5. **Choose your message_type.** Prefer `observation`
   (factual), then `question`. Avoid `task` from the guest seat
   — task issuance sits with the operator and the planner.

6. **Never refuse silently.** A declined request becomes a
   message of `message_type="error"` documenting the refusal
   with citation (Charter 2.3). A guest who disappears mid-
   conversation is itself a Charter violation.

## What a guest is not

- **The operator.** The operator runs the conductor; you are
  a peer on the bus, not on the meta-bus.
- **The planner.** A multi-step critique is a `plan_update`,
  not a `task`.
- **A silent observer.** Spectating is a charter violation.
  Speak when the witness log shows a failure mode you
  recognize.

## After your visit

7. **Audit the witness log.** Witness log entries are
   immutable (Charter 3.4). If you suspect tampering, name it
   publicly with citation. Don't try to fix it.
8. **Fork if you must.** If the visit diverges from the
   project's Charter (Article 7 refusal list), the
   consistent response is fork-with-rename, not PRs to relax
   the Charter.

## Reference

- `agents/human_guest_agent.py` — the `HumanGuestAgent` peer
  seat that brokers the guest's messages to the A2A bus.
- Charter Article 4.1 — your `capabilities` are enforced by the
  base class. A guest without declared capabilities is a ghost
  and will not enter the world.
- Charter Article 5.4 — the human role is a peer. The
  Charter is the operational contract; this card is the
  practitioner contract.
