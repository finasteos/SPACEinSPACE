"""Tests for artifact:// handoffs (Waggle-inspired)."""
from __future__ import annotations

import json

import pytest

from shared.artifacts import (
    ArtifactStore,
    COMPACT_THRESHOLD_BYTES,
    extract_tokens,
    handoff_line,
    make_token,
    parse_token,
)
from shared.a2a_protocol import A2AMessage, A2ABus
from shared.tool_executor import ToolExecutor


@pytest.fixture
def store(tmp_path):
    return ArtifactStore(root=tmp_path / "artifacts")


def test_token_roundtrip():
    tid = "abcdef012345"
    token = make_token(tid)
    assert token == "artifact://space/abcdef012345"
    assert parse_token(token) == tid
    assert len(token.encode()) <= 32


def test_extract_tokens_from_text():
    text = "see artifact://space/abcdef012345 and again artifact://space/abcdef012345"
    toks = extract_tokens(text)
    assert toks == ["artifact://space/abcdef012345"]


def test_mint_resolve_read_receipt(store):
    m = store.mint_text(
        "hello world " * 50,
        minted_by="meshy",
        thread_id="t1",
        summary="greeting",
        source_tool="meshy.create_text_to_3d",
    )
    assert m.token.startswith("artifact://space/")
    resolved = store.resolve(m.token)
    assert resolved["success"] is True
    assert resolved["summary"] == "greeting"
    assert "payload" not in resolved
    assert resolved["read_count"] == 0

    chunk = store.read(m.token, agent_id="planner", offset=0, limit=20)
    assert chunk["success"] is True
    assert chunk["text"] == ("hello world " * 50)[:20]
    assert chunk["eof"] is False

    resolved2 = store.resolve(m.token)
    assert resolved2["read_count"] == 1


def test_revoke_blocks_read(store):
    m = store.mint_text("secret", minted_by="a", summary="s")
    store.revoke(m.token, by_agent="a")
    assert store.read(m.token, agent_id="b")["success"] is False


def test_compact_image_base64(store):
    # large fake base64
    big = "A" * 500
    result = {"success": True, "image_base64": big, "description": "slime"}
    out = store.compact_tool_result(
        result, agent_id="pixellab", thread_id="t1", tool_name="pixellab.generate_pixflux"
    )
    assert out.get("compacted") is True
    assert "image_base64" not in out
    assert out["artifact"].startswith("artifact://space/")


def test_compact_large_json(store):
    result = {"success": True, "blob": "x" * (COMPACT_THRESHOLD_BYTES + 100)}
    out = store.compact_tool_result(
        result, agent_id="tool", thread_id="t1", tool_name="web.search"
    )
    assert out["compacted"] is True
    assert out["artifact"].startswith("artifact://space/")


def test_a2a_handoff_message(store):
    m = store.mint_text("scene dump", minted_by="blender", summary="scene")
    msg = A2AMessage(
        thread_id="t1", from_agent="blender", to_agent="planner",
        message_type="tool_result", content="raw huge stuff",
    ).with_handoff(m.token, hint="scene after create_cube")
    assert m.token in msg.content
    assert "raw huge" not in msg.content
    assert m.token in msg.artifact_tokens()
    assert handoff_line(m.token, "x").startswith(m.token)


@pytest.mark.asyncio
async def test_bus_carries_token_not_payload(store):
    bus = A2ABus(db=None)
    received = []

    async def handler(msg):
        received.append(msg)

    bus.subscribe("planner", handler)
    m = store.mint_json({"huge": "y" * 3000}, minted_by="meshy", summary="task")
    msg = A2AMessage(
        thread_id="t1", from_agent="meshy", to_agent="planner",
        message_type="tool_result",
    ).with_handoff(m.token, hint="preview done")
    await bus.publish(msg)
    assert len(received) == 1
    assert len(received[0].content.encode()) < 200
    assert received[0].artifact_tokens() == [m.token]


@pytest.mark.asyncio
async def test_tool_executor_artifact_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shared.artifacts.STORE_ROOT", tmp_path / "artifacts"
    )
    # reset singleton
    import shared.artifacts as art
    art._default_store = ArtifactStore(root=tmp_path / "artifacts")

    ex = ToolExecutor(db=None)
    minted = await ex.execute(
        {"name": "artifact.mint", "arguments": {
            "content": "hello from test", "summary": "hi",
        }},
        thread_id="t1",
        agent_id="planner",
    )
    assert minted["success"] is True
    token = minted["result"]["token"]

    resolved = await ex.execute(
        {"name": "artifact.resolve", "arguments": {"token": token}},
        thread_id="t1",
        agent_id="blender",
    )
    assert resolved["result"]["summary"] == "hi"

    read = await ex.execute(
        {"name": "artifact.read", "arguments": {"token": token, "limit": 5}},
        thread_id="t1",
        agent_id="blender",
    )
    assert read["result"]["text"] == "hello"
    assert read["result"]["success"] is True
