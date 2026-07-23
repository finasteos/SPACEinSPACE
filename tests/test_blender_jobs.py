"""B1 — blender-jobs queue: approve gate + run-via-B0-ambassador + glTF export.

The worker (`blender-jobs/worker.py`) isn't an importable package (hyphen), so
it's loaded by path. Queue dirs are redirected to a tmp dir per test, and a fake
ambassador stands in for B0's persistent Blender (no real Blender in CI).
"""
import importlib.util
from pathlib import Path

import pytest

from mcp_servers.blender_mcp_server import BlenderMCPServer
from tools.registry import TOOL_DEFINITIONS

_WORKER_PATH = Path(__file__).resolve().parent.parent / "blender-jobs" / "worker.py"
_spec = importlib.util.spec_from_file_location("blender_jobs_worker", _WORKER_PATH)
worker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(worker)


class FakeAmb:
    """Stand-in for B0's ambassador: records calls, writes stub output files."""

    def __init__(self):
        self.calls = []

    @property
    def tools(self):
        return {
            "blender.execute_script": self._exec,
            "blender.export_gltf": self._export,
            "blender.render": self._render,
        }

    async def _exec(self, script):
        self.calls.append(("execute_script", script[:40]))
        return {"status": "ok", "success": True}

    async def _export(self, filepath, **kw):
        self.calls.append(("export_gltf", filepath))
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("GLB")
        return {"filepath": filepath, "exists": True, "success": True}

    async def _render(self, output_path, **kw):
        self.calls.append(("render", output_path))
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("PNG")
        return {"output": output_path, "success": True}

    async def stop(self):
        pass


@pytest.fixture
def wq(tmp_path, monkeypatch):
    """Redirect all queue dirs + gallery to a temp tree."""
    for attr in ["PENDING", "APPROVED", "ACTIVE", "DONE", "FAILED",
                 "SCREENSHOTS", "EXPORTS"]:
        d = tmp_path / attr.lower()
        d.mkdir()
        monkeypatch.setattr(worker, attr, d)
    monkeypatch.setattr(worker, "GALLERY", tmp_path / "gallery.md")
    return tmp_path


class TestApproveGate:
    @pytest.mark.asyncio
    async def test_run_ignores_unapproved_pending(self, wq):
        (worker.PENDING / "p1_zen-garden.md").write_text("Create a zen garden\n")
        amb = FakeAmb()
        ran = await worker.run_approved(amb=amb)
        assert ran == 0
        assert (worker.PENDING / "p1_zen-garden.md").exists()  # untouched
        assert amb.calls == []                                  # Blender never touched

    def test_approve_moves_pending_to_approved(self, wq):
        (worker.PENDING / "j_zen-garden.md").write_text("Create a zen garden\n")
        assert worker.cmd_approve("zen") == 1
        assert (worker.APPROVED / "j_zen-garden.md").exists()
        assert not (worker.PENDING / "j_zen-garden.md").exists()

    def test_approve_all(self, wq):
        for n in ("a_chess.md", "b_cabin.md"):
            (worker.PENDING / n).write_text("prompt\n")
        assert worker.cmd_approve("all") == 2


class TestRunViaAmbassador:
    @pytest.mark.asyncio
    async def test_approved_job_runs_exports_and_renders(self, wq):
        (worker.APPROVED / "j_zen-garden.md").write_text("Create a zen garden\n")
        amb = FakeAmb()
        ran = await worker.run_approved(amb=amb)
        assert ran == 1
        # filed to done
        assert (worker.DONE / "j_zen-garden.md").exists()
        assert not (worker.APPROVED / "j_zen-garden.md").exists()
        # glTF exported + screenshot rendered (B1 deliverables)
        assert (worker.EXPORTS / "j_zen-garden.glb").exists()
        assert (worker.SCREENSHOTS / "j_zen-garden.png").exists()
        # order: scene-setup, template build, export, render — one session
        assert [c[0] for c in amb.calls] == [
            "execute_script", "execute_script", "export_gltf", "render"]
        # gallery updated with the prompt
        assert "zen garden" in worker.GALLERY.read_text().lower()

    @pytest.mark.asyncio
    async def test_build_failure_files_to_failed(self, wq):
        (worker.APPROVED / "j_boom.md").write_text("boom\n")

        class BadAmb(FakeAmb):
            async def _exec(self, script):
                self.calls.append(("execute_script", "x"))
                return {"success": False, "error": "kaboom"}

        ran = await worker.run_approved(amb=BadAmb())
        assert ran == 0
        assert (worker.FAILED / "j_boom.md").exists()
        assert not (worker.EXPORTS / "j_boom.glb").exists()  # never got to export


class TestExportGltfTool:
    @pytest.mark.asyncio
    async def test_builds_export_script(self):
        server = BlenderMCPServer()
        captured = {}

        async def _stub(script):
            captured["script"] = script
            return {"success": True, "stub": True}

        server._run_blender_script = _stub  # type: ignore[assignment]
        res = await server.tools["blender.export_gltf"](filepath="/tmp/out/scene.glb")
        assert res.get("stub") is True
        assert "export_scene.gltf" in captured["script"]
        assert "/tmp/out/scene.glb" in captured["script"]

    def test_registered_and_gated(self):
        assert "blender.export_gltf" in TOOL_DEFINITIONS
        assert "blender" in TOOL_DEFINITIONS["blender.export_gltf"].requires_capability
