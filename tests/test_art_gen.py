"""Tests for PixelLab / Meshy ambassadors (stub mode, no API keys)."""
import pytest

from mcp_servers.pixellab_mcp_server import PixelLabMCPServer
from mcp_servers.meshy_mcp_server import MeshyMCPServer


@pytest.fixture
def pixellab(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PIXELLAB_API_KEY", raising=False)
    monkeypatch.delenv("PIXELLAB_SECRET", raising=False)
    return PixelLabMCPServer(api_key="")


@pytest.fixture
def meshy(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MESHY_API_KEY", raising=False)
    return MeshyMCPServer(api_key="")


@pytest.mark.asyncio
async def test_pixellab_generate_stub(pixellab):
    r = await pixellab.handle_request({
        "id": "1",
        "name": "pixellab.generate_pixflux",
        "arguments": {
            "description": "cute slime enemy",
            "width": 64,
            "height": 64,
            "no_background": True,
            "save_to": "slime.png",
        },
    })
    assert r["success"] is True
    assert r["result"]["stub"] is True
    assert r["result"]["saved_to"] is not None
    assert "image_base64" in r["result"]


@pytest.mark.asyncio
async def test_pixellab_rejects_huge_resolution(pixellab):
    r = await pixellab.handle_request({
        "id": "2",
        "name": "pixellab.generate_pixflux",
        "arguments": {"description": "x", "width": 512, "height": 512},
    })
    assert r["result"]["success"] is False


@pytest.mark.asyncio
async def test_pixellab_balance_stub(pixellab):
    r = await pixellab.handle_request({
        "id": "3", "name": "pixellab.get_balance", "arguments": {},
    })
    assert r["result"]["success"] is True
    assert r["result"]["stub"] is True


@pytest.mark.asyncio
async def test_pixellab_path_traversal_rejected(pixellab):
    r = await pixellab.handle_request({
        "id": "4",
        "name": "pixellab.generate_pixflux",
        "arguments": {
            "description": "x",
            "save_to": "../../etc/passwd.png",
        },
    })
    assert r["result"]["success"] is True
    assert r["result"]["saved_to"] is None  # traversal discarded


@pytest.mark.asyncio
async def test_meshy_text_to_3d_stub_flow(meshy):
    created = await meshy.handle_request({
        "id": "1",
        "name": "meshy.create_text_to_3d",
        "arguments": {"prompt": "medieval sword", "mode": "preview"},
    })
    assert created["result"]["success"] is True
    tid = created["result"]["task_id"]

    waited = await meshy.handle_request({
        "id": "2",
        "name": "meshy.wait_text_to_3d",
        "arguments": {"task_id": tid, "timeout_s": 5, "poll_interval_s": 0.01},
    })
    assert waited["result"]["success"] is True
    assert waited["result"]["task"]["status"] == "SUCCEEDED"

    dl = await meshy.handle_request({
        "id": "3",
        "name": "meshy.download_model",
        "arguments": {
            "url": waited["result"]["task"]["model_urls"]["glb"],
            "filename": "sword.glb",
        },
    })
    assert dl["result"]["success"] is True
    assert "assets/meshy" in dl["result"]["saved_to"]


@pytest.mark.asyncio
async def test_meshy_refine_requires_preview_id(meshy):
    r = await meshy.handle_request({
        "id": "4",
        "name": "meshy.create_text_to_3d",
        "arguments": {"prompt": "x", "mode": "refine"},
    })
    assert r["result"]["success"] is False


@pytest.mark.asyncio
async def test_registry_coverage():
    from tools.registry import TOOL_DEFINITIONS
    p = PixelLabMCPServer(api_key="")
    m = MeshyMCPServer(api_key="")
    for name in p.tools:
        assert name in TOOL_DEFINITIONS, f"missing ToolDef {name}"
    for name in m.tools:
        assert name in TOOL_DEFINITIONS, f"missing ToolDef {name}"
