# PixelLab & Meshy ambassadors

Art-generation MCP ambassadors ported from gamedev-mcp-hub into SPACEinSPACE.

| Ambassador | Module | Default mode |
| --- | --- | --- |
| PixelLab | `mcp_servers/pixellab_mcp_server.py` | Stub without key; live REST with key |
| Meshy | `mcp_servers/meshy_mcp_server.py` | Stub without key; live OpenAPI with key |

Agents: `agents/pixellab_agent.py`, `agents/meshy_agent.py`.

## Keys

```bash
# .env
PIXELLAB_API_KEY=your-pixellab-secret   # also accepts PIXELLAB_SECRET
MESHY_API_KEY=msy_your_key              # from https://www.meshy.ai/settings/api
```

Without keys the ambassadors stay in **stub mode** (offline-safe for tests).

## PixelLab tools

- `pixellab.generate_pixflux` — text → pixel art (optional `save_to` under `assets/pixellab/`)
- `pixellab.rotate` — cardinal-direction sprite rotation
- `pixellab.get_balance`

Live API: `https://api.pixellab.ai/v1` (same surface as `pixellab-mcp`).

## Meshy tools

- `meshy.create_text_to_3d` / `meshy.get_text_to_3d` / `meshy.wait_text_to_3d`
- `meshy.create_image_to_3d` / `meshy.get_image_to_3d`
- `meshy.get_balance`
- `meshy.download_model` → `assets/meshy/`

Workflow: **preview → wait → refine (optional) → download**. Meshy assets expire (~3 days); always download.

## Cost fence

Both ambassadors log cost/sandbox policy at startup. Prefer Meshy `mode=preview` before `refine`. PixelLab caps resolution at 256×256 on the ambassador.

## Quick stub test

```bash
source .venv/bin/activate
pytest tests/test_art_gen.py -q
```
