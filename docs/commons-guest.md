# The Commons — guest view (B2)

A human **guest** can see and visit The Commons in the browser, and browse the
blender-jobs glTF gallery as live 3D.

## Run

```bash
python ui/serve.py            # then open http://localhost:8080/guest
```

Routes added to `ui/serve.py`:

- `GET /guest` — the guest view (`ui/guest.html`).
- `GET /api/gallery` — glTF manifest built by `blender-jobs/gallery_manifest.py`
  (scans `blender-jobs/exports/*.glb`, pairs prompt + screenshot).
- `GET /blender-jobs/<sub>` — serves `exports/` + `screenshots/` files,
  **path-guarded** (`ui/asset_guard.py`) to those two dirs only — traversal is
  rejected, not negotiated (Charter Article 4.4 spirit).

## What it shows

- **Who's here** — entities in the world, with guest peers highlighted.
- **Say-log** — recent utterances.
- **Gallery** — one `<model-viewer>` card per exported scene (rotatable 3D).

The page is driven by `loadCommons()` / `loadGallery()`; live mode fetches
`/api/commons` and `/api/gallery`. The bundled sample uses public stand-in
models — live mode serves your real `blender-jobs/exports/*.glb`.

## Presence (Charter 5.4)

A human visits by taking a **peer seat in the world**:
`shared/commons_presence.join_as_guest(world_backend, handle)` spawns a
`guest` entity via `world.spawn` (handle validated against the world's safe-id
charset; a repeated handle is refused — no double-join). The human is a peer,
not a controller.

> Wiring `POST /api/commons/join` and a live `/api/commons` snapshot needs the
> conductor to expose the (in-memory) world — a small follow-up. The presence
> primitive and the gallery are complete and tested here; the guest page's
> Commons summary runs on sample data until that snapshot endpoint lands.
