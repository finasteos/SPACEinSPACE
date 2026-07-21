# Blender MCP

The Blender integration runs as an MCP (Model Context Protocol)
ambassador *inside* the Blender process itself. It speaks back to
the conductor over standard input/output as a JSON pipe.

## Start

```bash
blender --background --python mcp_servers/blender_mcp_server.py
```

The server reads JSON tool requests from stdin, writes JSON tool
results to stdout, and exposes ten tools (see
`mcp_servers/blender_mcp_server.py`):

- `blender.get_scene_info`
- `blender.create_object`
- `blender.modify_object`
- `blender.set_material`
- `blender.render`
- `blender.get_viewport`
- `blender.execute_script`
- `blender.select_object`
- `blender.delete_selected`
- `blender.undo`

## Sandbox

`blender.execute_script` is sandboxed. It refuses any of:

- `import os`
- `import sys`
- `exec(`
- `eval(`
- `__import__`

This corresponds to [CHARTER.md](../CHARTER.md) Article 4.3 — every
ambassador ships its own forbidden-pattern list, logged to the
witness log on startup.

## Headless rendering

`blender.render` writes a single frame to a path you specify. The
default size is 1920x1080. For previewing, `blender.get_viewport`
returns a base64 PNG of the current viewport.

## Permissions

The Blender ambassador runs with the same filesystem rights as the
user who launched it. Per Charter Article 4, this is acceptable
*only* because the conductor does not have access to the host
process; it talks to the ambassador through MCP only. Sandboxing
the ambassador's tools is the safety boundary; sandboxing tools
that drive the conductor is a different problem (Charter Article
4.2 — embassy isolation).

## Failure modes

- **Blender isn't installed** — the ambassador reports
  `BLENDER_AVAILABLE = False` and the conductor receives an error
  per tool call.
- **The MCP pipe breaks** — the conductor logs an `error` message
  in the witness log; the agent that initiated the call receives
  the error and may escalate via Charter Article 6.3 (operator
  interjection) or via its own internal logic.

## See also

- [philosophy.md](philosophy.md) — why ambassadors are isolated
  rather than integrated.
- `../shared/a2a_protocol.py` — the bus that connects the
  conductor to this ambassador.
