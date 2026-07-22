# Blender addons for the agent team

The Blender ambassador (`mcp_servers/blender_mcp_server.py`) is the studio the
agents make art in. `scripts/install_blender_plugins.sh` provisions the addons
that make Blender maximally *scriptable, node-based and headless-friendly* — so
the agents orchestrate more and click less.

This page reconciles a suggested stack (with thanks to **Kimi** for the list 🙏)
against what the repo **already installs**, so we add only what's genuinely new
and keep the project honest about what's in and what's out.

## Already installed (no action needed)

From `install_blender_plugins.sh` today:

- **Procedural / parametric:** Sverchok, Animation Nodes, Geometry Nodes
  (built-in, exposed via `blender.geometry_nodes.apply`)
- **Mesh / hard-surface:** Mesh Machine, BoxCutter, HardOps, MACHIN3Tools,
  Fluent, ModifierList, LoopTools, F2, Extra Objects
- **Material / shading:** Node Wrangler, Node Preview, Principled Baker, NodeKit
- **UV / retopo:** TexTools, Zen UV, RetopoFlow, Instant Meshes
- **Texturing (AI):** Dream Textures (+ `torch` / `diffusers` / `transformers`)
- **Pipeline / export:** glTF 2.0 (built-in), Better FBX, CAD Sketcher, MeasureIt

## Added in this change (all open-source)

| Addon | Source | Why it earns a slot |
| --- | --- | --- |
| **Ucupaint** | `ucupumar/ucupaint` | Layered, **scriptable** texturing — agents build materials programmatically by layer instead of hand-wiring nodes. Big, clean API. |
| **Tissue** | `alessandro-zomparelli/tissue` | Tessellation + generative surface patterns from simple inputs — a natural partner to Geometry Nodes. |
| **A.N.T. Landscape** | bundled (`ant_landscape`) | Parametric terrain: agent sets parameters → terrain, zero hand-sculpting. Great procedural base for planets/worlds. |
| **PolyQuilt** | `sakana3/PolyQuilt` | Sketch retopology for the rare manual touch-up on agent-generated sculpts. |

## Intentionally **not** added (and why)

This is an AGPL project that refuses to lean on closed tools (see `CHARTER.md`,
"What this is not"). So:

- **Quad Remesher** — commercial/trial. *Alternative already present:* Instant
  Meshes (auto-retopo) + RetopoFlow.
- **Render+ / paid "Batch Tools"** — commercial. *Alternative:* batch rendering
  is an **orchestration** concern the agent team already owns — loop
  `blender.render` over N variants overnight; no paid addon required.
- **BlenderKit "Space Kit" / StellarGenerator / Physical Atmosphere** — paid
  asset packs, not open addons. *Alternative that fits our ethos:* build space
  **procedurally** (starfields, nebulae, planets, atmosphere) with the Sverchok
  + Geometry Nodes stack already installed — and we can ship those as reusable
  node-group `.blend` assets later.
- **Dream Textures GPU stack** — already wired, but note it needs a local GPU +
  model weights; it's optional, not part of the minimal path.

## The agent pipeline these enable

```
generate ──▶ texture ──▶ retopo ──▶ export ──▶ render
Sverchok/    Ucupaint/   Instant    glTF/      blender.render
GeoNodes/    Dream Tex   Meshes/    Better     (agent loops
Tissue/      Node        RetopoFlow FBX        for batches)
A.N.T.       Wrangler
```

Everything above is reachable head-lessly, so the agents can run the whole loop
— generate → texture → retopo → export → render — with minimal human clicks.

## Follow-up: expose them as declarative MCP tools

Installing an addon makes it available *inside* Blender; the agents reach it
through the ambassador. A natural next step is a handful of new **declarative**
`blender.*` tools (kept structured — no arbitrary code, consistent with the
Article 4.3 sandbox), e.g.:

- `blender.landscape.generate` → A.N.T. Landscape parameters
- `blender.tissue.tessellate` → Tissue component/generator
- `blender.texture.layer` → Ucupaint layer ops

These touch `blender_mcp_server.py` and `tools/registry.py`, so they're best
landed **after** the Article 4.3 sandbox PR merges, to avoid editing the same
file in two open PRs.
