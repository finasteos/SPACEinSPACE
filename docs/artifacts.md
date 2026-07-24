# Artifact handoffs (`artifact://space/…`)

Waggle-inspired references for the A2A bus: **the token travels; the payload does not.**

## Why

Multi-agent handoffs that paste Meshy task JSON, PixelLab base64, or scene dumps burn context and lose attribution. A short token (`artifact://space/<12hex>`, ~28 bytes) fixes that.

## Lifecycle

```
mint  →  hand off token on the bus  →  resolve (summary)  →  read (budgeted slice)
                                              ↘ revoke / supersede
```

| Op | What you get |
| --- | --- |
| `artifact.mint` | Create token from text/json |
| `artifact.resolve` | Attribution + summary — **never** payload |
| `artifact.read` | Byte-budgeted slice + **read receipt** |
| `artifact.revoke` | Further reads fail |

Auto-compact: `ToolExecutor` mints artifacts for bulky tool results (`image_base64`, JSON > 2KB) and returns `{artifact, summary, compacted: true}` instead.

## Bus helpers

```python
from shared.a2a_protocol import A2AMessage
from shared.artifacts import get_artifact_store

store = get_artifact_store()
m = store.mint_text("…", minted_by="meshy", summary="preview glb meta")
msg = A2AMessage(
    thread_id=tid, from_agent="meshy", to_agent="planner",
    message_type="tool_result",
).with_handoff(m.token, hint="preview done")
await bus.publish(msg)
# msg.content ≈ "artifact://space/a1b2c3d4e5f6  # preview done"
```

## Storage

Manifests + payloads live under `assets/artifacts/` (gitignored). Each artifact has `sha256`, lineage (`parent_id` / `supersedes`), and an append-only `reads[]` receipt log.

## Charter

- **Witnessed (3):** mint/read/revoke recorded on the manifest.
- **Bounded (4):** `read` caps at 64 KiB per call; store confined under `assets/artifacts/`.
- **No auto-expand:** tokens in `content` / `context.artifacts` never inflate into payloads unless an agent explicitly `read`s.

## Not a waggle fork

We borrowed the *idea* (cheap attributed handoff). Implementation is Python, local filesystem, SPACE-native — no Ed25519, no separate MCP binary. If we later need cross-host reach, waggle remains a candidate embassy.
