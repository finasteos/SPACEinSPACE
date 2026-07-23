#!/usr/bin/env python3
"""Fake Blender-side MCP server for tests (no real Blender needed).

Speaks the same line-delimited JSON protocol as
``mcp_servers/base_mcp_server.BaseMCPServer.run_stdio()``: reads one JSON request
per line on stdin, writes one JSON response per line on stdout. Holds an
in-memory scene dict so scene continuity across calls can be asserted.

It deliberately prints a non-JSON banner line first, mimicking Blender's own
stdout noise, to prove the host backend skips it.
"""
import json
import sys


def handle(scene: dict, name: str, args: dict) -> dict:
    if name == "blender.create_object":
        typ = args.get("type", "cube")
        oname = args.get("name") or f"{typ}.{len(scene['objects']) + 1:03d}"
        scene["objects"][oname] = {
            "name": oname, "type": typ, "location": args.get("location", [0, 0, 0]),
        }
        return {"name": oname, "vertices": 8}
    if name == "blender.get_scene_info":
        return {
            "objects": [dict(o) for o in scene["objects"].values()],
            "count": len(scene["objects"]),
            "mode": "OBJECT",
        }
    if name == "blender.modify_object":
        obj = args.get("object")
        if obj not in scene["objects"]:
            return {"error": f"Object not found: {obj}"}
        op = args.get("operation")
        if op == "delete":
            scene["objects"].pop(obj, None)
            return {"deleted": obj}
        scene["objects"][obj]["last_op"] = op
        return {"object": obj, "operation": op}
    if name == "blender.delete_selected":
        scene["objects"].clear()
        return {"deleted": "all"}
    if name == "blender.undo":
        return {"status": "undone"}
    return {"tool": name, "args": args}  # default echo


def main() -> None:
    scene = {"objects": {}}
    # Banner noise, like Blender's startup output — the host must skip this.
    print("Blender 4.x (fake ambassador) — MCP on stdio", flush=True)
    while True:
        line = sys.stdin.readline()
        if not line:  # stdin closed → shut down (mirrors real ambassador)
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = req.get("id", "")
        try:
            result = handle(scene, req.get("name", ""), req.get("arguments", {}) or {})
            resp = {"id": rid, "result": result, "success": True}
        except Exception as e:  # noqa: BLE001
            resp = {"id": rid, "error": f"{type(e).__name__}: {e}", "success": False}
        print(json.dumps(resp), flush=True)


if __name__ == "__main__":
    main()
