# Unity & Godot ambassadors

Game-engine MCP ambassadors ported from [gamedev-mcp-hub](https://github.com/) into SPACEinSPACE's Charter-bound embassy model.

## What ships

| Ambassador | Module | Default backend |
| --- | --- | --- |
| Unity | `mcp_servers/unity_mcp_server.py` | In-memory scene graph |
| Godot | `mcp_servers/godot_mcp_server.py` | In-memory scene graph |

Agents: `agents/unity_agent.py`, `agents/godot_agent.py` (registered in the conductor).

Catalog of optional external packages: `config/game-engines.json`.

## Quick test (no Editor required)

```bash
source .venv/bin/activate
python - <<'PY'
import asyncio
from mcp_servers.unity_mcp_server import UnityMCPServer

async def main():
    u = UnityMCPServer()
    print(await u.handle_request({
        "name": "unity.create_gameobject",
        "arguments": {"name": "Player", "primitive": "capsule", "position": [0, 1, 0]},
    }))
    print(await u.handle_request({"name": "unity.get_scene_info", "arguments": {}}))

asyncio.run(main())
PY
```

## Live Editor bridge

1. Install Unity (or Godot) and open your project.
2. In `.env`:

```bash
GAME_ENGINE_BACKEND=external
UNITY_PROJECT_PATH=/absolute/path/to/YourUnityProject
UNITY_EDITOR_PATH=/Applications/Unity/Hub/Editor/6000.0.0f1/Unity.app/Contents/MacOS/Unity
# optional package override:
UNITY_MCP_PACKAGE=@nurture-tech/unity-mcp-runner

# Godot:
GODOT_PROJECT_PATH=/absolute/path/to/YourGodotProject
GODOT_MCP_PACKAGE=godot-mcp
```

3. Restart `python main.py`.

The external backend spawns the MCP package via `npx` (same pattern as gamedev-mcp-hub's `UnityAdapter`).

## Charter notes

- Declarative scene ops only — no arbitrary C# / GDScript eval surface on the ambassador.
- Primitives and components are allowlisted (`mcp_servers/game_backends/`).
- Capability gate: tools require `unity` / `godot` capability (Article 4).
