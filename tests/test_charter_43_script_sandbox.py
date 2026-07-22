"""Charter Article 4.3 script-sandbox test (Blender ambassador).

Article 4.3 in CHARTER.md:
    "Every ambassador MCP server declares its own forbidden-pattern list at
     startup (e.g. Blender's blender.execute_script forbids import os,
     import sys, exec(, eval(, __import__). Forbidden-pattern lists are
     visible in the witness log on startup."

Status: this test makes the article empirical for the Blender ambassador.
Before the gate was added, `blender.execute_script` ran agent-authored code
with no inspection at all. The gate guards only sandbox-ESCAPE primitives;
the creative Blender API is never inspected — Article 4.3 is a fence around
the yard, not a cage around the agent.
"""

import logging

import pytest

from mcp_servers.blender_mcp_server import (
    BlenderMCPServer,
    FORBIDDEN_SCRIPT_PATTERNS,
)


@pytest.fixture
def server():
    return BlenderMCPServer()


@pytest.fixture
def gated_server(server):
    """Server whose Blender subprocess is replaced by a recording stub, so we
    can prove which scripts reach execution and which are refused up front."""
    calls = []

    async def _stub(script):
        calls.append(script)
        return {"success": True, "raw_output": "stubbed", "reached_blender": True}

    server._run_blender_script = _stub  # type: ignore[assignment]
    server._recorded_calls = calls  # type: ignore[attr-defined]
    return server


# Each entry is (human_label, escape_script). Every script must be refused by
# the Article 4.3 gate before it ever reaches the Blender process.
FORBIDDEN_SCRIPTS = [
    ("import os", "import os\nos.system('rm -rf /')"),
    ("import sys", "import sys\nsys.exit(1)"),
    ("import subprocess", "import subprocess\nsubprocess.run(['ls'])"),
    ("__import__", "__import__('os').system('id')"),
    ("exec(", "exec('print(1)')"),
    ("eval(", "eval('2 + 2')"),
    ("os.system", "bpy.ops.mesh.primitive_cube_add()\nos.system('id')"),
    ("open(", "data = open('/etc/passwd').read()"),
]


class TestForbiddenPatternsRejected:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("label,script", FORBIDDEN_SCRIPTS)
    async def test_escape_script_is_refused(self, gated_server, label, script):
        handler = gated_server.tools["blender.execute_script"]
        result = await handler(script=script)

        assert result["success"] is False
        assert result["charter_article"] == "4.3"
        assert result["forbidden_pattern"], "refusal must name the pattern"
        # The offending script must NEVER have reached the Blender process.
        assert gated_server._recorded_calls == []


class TestCreativeSurfaceIsOpen:
    """The whole point: creativity is never gated. These scripts must pass
    the sandbox and reach the (stubbed) Blender run untouched."""

    CREATIVE = [
        "bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))",
        (
            "import bpy\nimport bmesh\nimport mathutils\n"
            "from mathutils import Vector\nbpy.ops.mesh.primitive_monkey_add()"
        ),
        (
            "import math\n"
            "for i in range(12):\n"
            "    bpy.ops.mesh.primitive_ico_sphere_add("
            "location=(math.sin(i), math.cos(i), 0))"
        ),
        (
            "import random\n"
            "mat = bpy.data.materials.new('art')\n"
            "mat.diffuse_color = (random.random(), random.random(), "
            "random.random(), 1.0)"
        ),
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("script", CREATIVE)
    async def test_creative_script_reaches_blender(self, gated_server, script):
        handler = gated_server.tools["blender.execute_script"]
        result = await handler(script=script)

        # Not refused by the sandbox — it reached the (stubbed) Blender run.
        assert result.get("charter_article") != "4.3"
        assert gated_server._recorded_calls, "creative script was wrongly gated"


class TestStartupPolicyIsWitnessed:
    def test_forbidden_list_is_nonempty_and_exposed(self, server):
        assert server.forbidden_patterns, "Article 4.3 requires a declared list"
        assert len(server.forbidden_patterns) == len(FORBIDDEN_SCRIPT_PATTERNS)

    def test_named_charter_patterns_are_covered(self, server):
        """The exact primitives named in Article 4.3 must be present."""
        joined = " ".join(server.forbidden_patterns).lower()
        for named in ("import os", "import sys", "exec(", "eval(", "__import__"):
            assert named in joined

    def test_policy_logged_at_startup(self, caplog):
        with caplog.at_level(logging.INFO, logger="mcp.blender"):
            BlenderMCPServer()
        text = " ".join(record.getMessage() for record in caplog.records)
        assert "Charter 4.3" in text
        assert "forbidden escape patterns" in text
