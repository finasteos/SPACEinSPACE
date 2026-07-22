"""Tests for the creative Blender addon tools (Ucupaint / Tissue / A.N.T.).

These declarative tools are registered on the Blender ambassador and mirror the
existing plugin-tool style: they build a guarded Blender script and delegate to
`_run_blender_script`. Every one is capability-gated in the tool registry
(Charter Article 4). We stub the Blender subprocess so the tests run without
Blender installed.
"""

import pytest

from mcp_servers.blender_mcp_server import BlenderMCPServer
from tools.registry import TOOL_DEFINITIONS

NEW_TOOLS = [
    "blender.landscape.generate",
    "blender.tissue.tessellate",
    "blender.texture.layer",
]


@pytest.fixture
def server():
    return BlenderMCPServer()


class TestRegistration:
    def test_tools_registered_on_ambassador(self, server):
        for name in NEW_TOOLS:
            assert name in server.tools

    def test_tools_present_in_registry_and_gated(self):
        for name in NEW_TOOLS:
            assert name in TOOL_DEFINITIONS
            assert "blender" in TOOL_DEFINITIONS[name].requires_capability

    def test_plugin_specific_caps(self):
        assert "ant_landscape" in TOOL_DEFINITIONS["blender.landscape.generate"].requires_capability
        assert "tissue" in TOOL_DEFINITIONS["blender.tissue.tessellate"].requires_capability
        assert "ucupaint" in TOOL_DEFINITIONS["blender.texture.layer"].requires_capability

    def test_every_ambassador_blender_tool_has_a_registry_def(self, server):
        """Invariant: no dangling blender.* tool without a catalogue entry."""
        for name in server.tools:
            if name.startswith("blender."):
                assert name in TOOL_DEFINITIONS, f"{name} missing from registry"


class TestScriptsAreGuardedAndDelegate:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool,kwargs,needle", [
        ("blender.landscape.generate", {}, "landscape_add"),
        ("blender.tissue.tessellate",
         {"base_object": "Base", "component_object": "Comp"}, "tissue_tessellate"),
        ("blender.texture.layer", {"object": "Cube"}, "ucupaint"),
    ])
    async def test_builds_expected_guarded_script(self, server, tool, kwargs, needle):
        captured = {}

        async def _stub(script):
            captured["script"] = script
            return {"success": True, "stub": True}

        server._run_blender_script = _stub  # type: ignore[assignment]
        result = await server.tools[tool](**kwargs)

        assert result.get("stub") is True
        script = captured["script"]
        assert needle in script
        # Same defensive shape as the other plugin tools.
        assert "try:" in script and "except Exception" in script
