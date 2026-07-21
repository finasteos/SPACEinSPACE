"""Charter Article 4 executional guard test.

Article 4 (in CHARTER.md):
    "Tool calls outside the declared capability set shall be
     rejected by ToolExecutor."

Status: this test makes that article empirical. `ToolDef` carries a
`requires_capability: list[str]` field. `ToolExecutor.execute` consults
an `agent_capabilities` callable wired by the conductor; if the tool's
required capability set is not a subset of the caller's declared
capabilities, the call is rejected fail-closed and the rejection is
logged to the witness (`tool_calls`) row.
"""

from typing import Tuple
from unittest.mock import MagicMock, AsyncMock

import pytest

from shared.tool_executor import ToolExecutor
from tools.registry import ToolDef


# ─── Helpers ─────────────────────────────────────────────────────

class _CapResolver:
    """Tiny in-memory resolver: agent_id → (cap1, cap2, ...)."""

    def __init__(self, mapping):
        self.mapping = dict(mapping)

    def __call__(self, agent_id: str) -> Tuple[str, ...]:
        if agent_id not in self.mapping:
            raise KeyError(f"unknown agent: {agent_id}")
        return tuple(self.mapping[agent_id])


def _register_restricted(executor: ToolExecutor, name: str, required):
    """Drop a ToolDef with non-trivial `requires_capability` into the
    executor's private registry. We don't go through the public
    `register` decorator so we don't need an actual handler — these
    tests run the gate logic *before* dispatch.
    """
    executor._tool_defs[name] = ToolDef(
        name=name,
        version="0.0.1",
        description=f"synthetic gate test for {name}",
        parameters_schema={"type": "object", "properties": {}, "required": []},
        requires_capability=list(required),
    )


# ─── Tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_article_4_tool_call_with_required_capability_succeeds():
    """When the agent declares every required capability, the call goes
    through to dispatch. (We use a builtin like web.search? Actually
    web.search has `requires_capability=[]` by default. Instead, drop
    a synthetic def but don't override any handler — we want the
    GATE to pass, after which dispatch returns Unknown because no
    handler is registered.)

    The point of this test: gate logic does NOT block a permitted call.
    We assert Unknown-tool error rather than Charter-error to confirm
    we got past the gate.
    """
    executor = ToolExecutor(
        db=None,
        agent_capabilities=_CapResolver({"planner-1": ["blender", "sverchok"]}),
    )
    _register_restricted(executor, "blender.sverchok.generate", ["blender", "sverchok"])
    # No handler registered → Unknown tool expected (gate passed).
    result = await executor.execute(
        {"name": "blender.sverchok.generate", "arguments": {}},
        thread_id="t", agent_id="planner-1",
    )
    assert not result["success"]
    assert "Unknown tool" in result["error"]
    assert "Charter Article 4" not in result["error"]


@pytest.mark.asyncio
async def test_article_4_tool_call_missing_capability_rejected():
    """When the agent does NOT declare a required capability, the
    gate rejects before dispatch. Witness log records the rejection.
    """
    db = MagicMock()
    db.log_tool_call = AsyncMock()

    executor = ToolExecutor(
        db=db,
        agent_capabilities=_CapResolver({"planner-1": ["blender"]}),  # no "sverchok"
    )
    _register_restricted(executor, "blender.sverchok.generate", ["blender", "sverchok"])

    result = await executor.execute(
        {"name": "blender.sverchok.generate", "arguments": {}},
        thread_id="t1", agent_id="planner-1",
    )

    assert result["success"] is False
    assert "Charter Article 4" in result["error"]
    assert "sverchok" in result["error"]
    assert db.log_tool_call.await_count >= 1
    # Witness row carries the rejection reason.
    kwargs = db.log_tool_call.await_args.kwargs
    assert kwargs["success"] is False
    assert "Charter Article 4" in kwargs["error_message"]


@pytest.mark.asyncio
async def test_article_4_multiple_required_with_partial_declaration_rejected():
    """Strict set-membership: tool requires 2 caps, agent has 1 → reject."""
    executor = ToolExecutor(
        db=None,
        agent_capabilities=_CapResolver({"a": ["blender"]}),  # missing "sverchok"
    )
    _register_restricted(executor, "blender.sverchok.generate", ["blender", "sverchok"])

    result = await executor.execute(
        {"name": "blender.sverchok.generate", "arguments": {}},
        thread_id="t", agent_id="a",
    )
    assert not result["success"]
    assert "Charter Article 4" in result["error"]
    assert "sverchok" in result["error"]


@pytest.mark.asyncio
async def test_article_4_empty_requires_capability_allows_any_caller():
    """Empty `requires_capability` list is universal — every caller
    may invoke. Backwards-compat for substrate primitives.
    """
    executor = ToolExecutor(db=None, agent_capabilities=None)
    _register_restricted(executor, "memory.query", [])  # default empty

    # No handler, but the gate must NOT trigger.
    result = await executor.execute(
        {"name": "memory.query", "arguments": {}},
        thread_id="t", agent_id="anyone",
    )
    assert not result["success"]
    assert "Unknown tool" in result["error"]  # gate passed
    assert "Charter Article 4" not in result["error"]


@pytest.mark.asyncio
async def test_article_4_unknown_tool_still_returns_unknown_not_charter():
    """Capability gate must NOT shadow the existing Unknown-tool
    branch. Unknown → "Unknown tool" error, not Charter error.
    """
    executor = ToolExecutor(
        db=None,
        agent_capabilities=_CapResolver({"a": ["everything"]}),
    )
    result = await executor.execute(
        {"name": "no.such.tool", "arguments": {}},
        thread_id="t", agent_id="a",
    )
    assert not result["success"]
    assert "Unknown tool" in result["error"]
    assert "Charter Article 4" not in result["error"]


@pytest.mark.asyncio
async def test_article_4_missing_resolver_fails_closed():
    """If the executor has no `agent_capabilities` resolver wired AND
    a tool declares a requirement, the gate fails closed. This is the
    most important safety property — silence must not default to
    permission.
    """
    executor = ToolExecutor(db=None, agent_capabilities=None)
    _register_restricted(executor, "blender.render", ["blender"])

    result = await executor.execute(
        {"name": "blender.render", "arguments": {}},
        thread_id="t", agent_id="planner-1",
    )
    assert not result["success"]
    assert "Charter Article 4" in result["error"]
    # Error message names the missing wiring.
    assert "no agent_capabilities resolver" in result["error"]


@pytest.mark.asyncio
async def test_article_4_resolver_exception_is_charter_rejection():
    """If the resolver raises (e.g. agent_id not in registry), the
    gate treats it as Charter rejection — not as a generic exception.
    """
    executor = ToolExecutor(db=None, agent_capabilities=_CapResolver({}))
    _register_restricted(executor, "blender.render", ["blender"])

    result = await executor.execute(
        {"name": "blender.render", "arguments": {}},
        thread_id="t", agent_id="ghost",
    )
    assert not result["success"]
    # Positive assertions on this loose test so an audit reviewer can
    # trust it. A resolver crash surfaces as a Charter Article 4
    # violation named in the rejection string.
    assert "Charter Article 4" in result["error"]
    assert "resolver raised" in result["error"]
    assert "Unknown tool" not in result["error"]






