"""B2 — web guest UI + Commons presence.

Covers the gallery manifest (scan exports), guest presence (spawn a guest peer
in the world), the web-asset path guard, and the guest.html surface. No real
Blender or browser needed.
"""
import importlib.util
from html.parser import HTMLParser
from pathlib import Path

import pytest

from mcp_servers.world_backends import InMemoryBackend
from shared.commons_presence import join_as_guest, present_guests
from ui import asset_guard

REPO = Path(__file__).resolve().parent.parent

_gm_spec = importlib.util.spec_from_file_location(
    "gallery_manifest", REPO / "blender-jobs" / "gallery_manifest.py")
gallery_manifest = importlib.util.module_from_spec(_gm_spec)
_gm_spec.loader.exec_module(gallery_manifest)


class TestGalleryManifest:
    def _seed(self, root: Path):
        (root / "blender-jobs" / "exports").mkdir(parents=True)
        (root / "blender-jobs" / "queue" / "done").mkdir(parents=True)
        (root / "blender-jobs" / "screenshots").mkdir(parents=True)
        (root / "blender-jobs" / "exports" / "zen.glb").write_text("GLB")
        (root / "blender-jobs" / "queue" / "done" / "zen.md").write_text(
            "Create a zen garden\n\n---\n")
        (root / "blender-jobs" / "screenshots" / "zen.png").write_text("PNG")

    def test_pairs_prompt_and_assets(self, tmp_path):
        self._seed(tmp_path)
        m = gallery_manifest.build_manifest(tmp_path)
        assert len(m) == 1
        e = m[0]
        assert e["name"] == "zen"
        assert e["prompt"] == "Create a zen garden"
        assert e["glb"] == "/blender-jobs/exports/zen.glb"
        assert e["screenshot"] == "/blender-jobs/screenshots/zen.png"

    def test_missing_screenshot_is_none(self, tmp_path):
        (tmp_path / "blender-jobs" / "exports").mkdir(parents=True)
        (tmp_path / "blender-jobs" / "exports" / "solo.glb").write_text("GLB")
        m = gallery_manifest.build_manifest(tmp_path)
        assert m[0]["screenshot"] is None
        assert m[0]["prompt"] == "solo"  # falls back to the stem


class TestCommonsPresence:
    @pytest.mark.asyncio
    async def test_guest_joins_as_world_peer(self):
        backend = InMemoryBackend()
        res = await join_as_guest(backend, "aria")
        assert res["success"] is True
        assert res["entity"]["kind"] == "guest"
        assert res["entity"]["id"] == "aria"
        snap = await backend.look()
        assert [g["id"] for g in present_guests(snap)] == ["aria"]

    @pytest.mark.asyncio
    async def test_invalid_handle_refused(self):
        backend = InMemoryBackend()
        res = await join_as_guest(backend, "not a handle!")
        assert res["success"] is False
        assert res["field"] == "handle"

    @pytest.mark.asyncio
    async def test_double_join_refused(self):
        backend = InMemoryBackend()
        assert (await join_as_guest(backend, "aria"))["success"] is True
        again = await join_as_guest(backend, "aria")
        assert again["success"] is False  # world.spawn: id already exists


class TestAssetGuard:
    def test_allows_export_file(self, tmp_path, monkeypatch):
        root = tmp_path
        (root / "exports").mkdir()
        (root / "exports" / "x.glb").write_text("GLB")
        monkeypatch.setattr(asset_guard, "BLENDER_JOBS", root.resolve())
        assert asset_guard.safe_blender_asset("exports/x.glb") is not None

    def test_rejects_traversal(self, tmp_path, monkeypatch):
        monkeypatch.setattr(asset_guard, "BLENDER_JOBS", tmp_path.resolve())
        assert asset_guard.safe_blender_asset("../../etc/passwd") is None
        assert asset_guard.safe_blender_asset("/etc/passwd") is None

    def test_rejects_disallowed_dir(self, tmp_path, monkeypatch):
        (tmp_path / "queue" / "done").mkdir(parents=True)
        (tmp_path / "queue" / "done" / "j.md").write_text("x")
        monkeypatch.setattr(asset_guard, "BLENDER_JOBS", tmp_path.resolve())
        assert asset_guard.safe_blender_asset("queue/done/j.md") is None


class TestGuestHtml:
    def test_uses_model_viewer_and_documents_endpoints(self):
        html = (REPO / "ui" / "guest.html").read_text()
        assert "model-viewer" in html
        assert "/api/gallery" in html
        assert "/api/commons" in html
        HTMLParser().feed(html)  # parses without error
