from typing import Dict, Any, Callable, Awaitable, Optional
from pydantic import BaseModel, Field


class ToolDef(BaseModel):
    name: str
    version: str
    description: str
    parameters_schema: Dict[str, Any]
    examples: list[dict] = Field(default_factory=list)
    failure_patterns: dict[str, str] = Field(default_factory=dict)
    timeout_ms: int = 10000
    retry_policy: dict = Field(default_factory=lambda: {"max_retries": 2, "backoff": "exponential"})
    # Charter Article 4 — executional capability gate. Non-empty list
    # means "the calling agent MUST declare each of these strings in
    # its capability tuple, else ToolExecutor rejects the call".
    # Membership is exact (set semantics). Empty list = universal,
    # backwards-compatible with substrate primitives like file.read.
    requires_capability: list[str] = Field(default_factory=list)


TOOL_DEFINITIONS: dict[str, ToolDef] = {
    "blender.get_scene_info": ToolDef(
        name="blender.get_scene_info",
        version="1.0.0",
        description="Hämta information om aktuell Blender-scen: objekt, material, kamera, lampor",
        parameters_schema={
            "type": "object",
            "properties": {},
            "required": [],
        },
        examples=[
            {"input": {}, "output": {"objects": ["Cube", "Camera", "Light"], "mode": "OBJECT"}}
        ],
        failure_patterns={"connection": "Blender MCP-server är inte igång"},
        requires_capability=["blender"],
    ),
    "blender.create_object": ToolDef(
        name="blender.create_object",
        version="2.1.0",
        description="Skapa ett nytt objekt i Blender-scenen",
        parameters_schema={
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["cube", "sphere", "cylinder", "plane", "monkey", "circle", "uv_sphere", "ico_sphere"]},
                "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "name": {"type": "string"},
                "size": {"type": "number"},
            },
            "required": ["type", "location"],
        },
        examples=[
            {"input": {"type": "cube", "location": [0, 0, 0]}, "output": {"name": "Cube.001", "vertices": 8}}
        ],
        failure_patterns={
            "name_collision": "Objekt med samma namn finns, använd .001 suffix",
            "invalid_mode": "Byt till OBJECT mode först",
            "invalid_type": "Stödd objekttyp, använd en av: cube, sphere, cylinder, plane, monkey",
        },
        timeout_ms=5000,
        requires_capability=["blender"],
    ),
    "blender.modify_object": ToolDef(
        name="blender.modify_object",
        version="2.0.0",
        description="Modifiera ett objekt: extrudera, skala, rotera, flytta",
        parameters_schema={
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "operation": {"type": "string", "enum": ["extrude", "scale", "rotate", "translate", "delete", "duplicate"]},
                "value": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            },
            "required": ["object", "operation", "value"],
        },
        examples=[
            {"input": {"object": "Cube", "operation": "extrude", "value": [0, 0, 2]}, "output": {"vertices": 12}}
        ],
        failure_patterns={
            "no_selection": "Extrudera utan selection går inte",
            "wrong_mode": "Extrude kräver EDIT mode",
        },
        timeout_ms=8000,
        requires_capability=["blender"],
    ),
    "blender.set_material": ToolDef(
        name="blender.set_material",
        version="1.1.0",
        description="Sätt material och färg på ett objekt",
        parameters_schema={
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "color": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
                "material_name": {"type": "string"},
            },
            "required": ["object", "color"],
        },
        requires_capability=["blender"],
    ),
    "blender.render": ToolDef(
        name="blender.render",
        version="1.0.0",
        description="Rendera en frame från aktuell vy eller kamera",
        parameters_schema={
            "type": "object",
            "properties": {
                "output_path": {"type": "string"},
                "resolution_x": {"type": "integer", "default": 1920},
                "resolution_y": {"type": "integer", "default": 1080},
            },
        },
        timeout_ms=60000,
        requires_capability=["blender"],
    ),
    "blender.execute_script": ToolDef(
        name="blender.execute_script",
        version="1.0.0",
        description="Kör ett godtyckligt Python-script i Blender",
        parameters_schema={
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "Valid Blender Python API code"},
            },
            "required": ["script"],
        },
        timeout_ms=15000,
        requires_capability=["blender"],
    ),
    "blender.undo": ToolDef(
        name="blender.undo",
        version="1.0.0",
        description="Ångra senaste operationen i Blender",
        parameters_schema={
            "type": "object",
            "properties": {},
        },
        requires_capability=["blender"],
    ),
    "blender.get_viewport": ToolDef(
        name="blender.get_viewport",
        version="1.0.0",
        description="Ta en skärmdump av viewport för att se aktuell scen",
        parameters_schema={
            "type": "object",
            "properties": {},
        },
        timeout_ms=5000,
        requires_capability=["blender"],
    ),
    "web.search": ToolDef(
        name="web.search",
        version="1.0.0",
        description="Sök på webben efter information",
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
        timeout_ms=15000,
    ),
    "file.read": ToolDef(
        name="file.read",
        version="1.0.0",
        description="Läs innehållet i en fil",
        parameters_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    ),
    "file.write": ToolDef(
        name="file.write",
        version="1.0.0",
        description="Skriv innehåll till en fil",
        parameters_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    ),
    "memory.store": ToolDef(
        name="memory.store",
        version="1.0.0",
        description="Lagra ett minne i vektordatabasen",
        parameters_schema={
            "type": "object",
            "properties": {
                "memory_type": {"type": "string", "enum": ["episodic", "semantic", "procedural"]},
                "content": {"type": "string"},
                "ttl_hours": {"type": "integer"},
            },
            "required": ["memory_type", "content"],
        },
    ),
    "memory.query": ToolDef(
        name="memory.query",
        version="1.0.0",
        description="Sök i vektordatabasen efter relevanta minnen",
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "memory_type": {"type": "string", "enum": ["episodic", "semantic", "procedural"]},
            },
            "required": ["query"],
        },
    ),

    # ── Plugin tools (from Sverchok, Mesh Machine, etc.) ─────
    "blender.sverchok.generate": ToolDef(
        name="blender.sverchok.generate",
        version="1.0.0",
        description="Generera parametrisk mesh via Sverchok nod-träd",
        parameters_schema={
            "type": "object",
            "properties": {
                "tree_name": {"type": "string", "description": "Name of Sverchok node tree"},
                "inputs": {"type": "object", "description": "Input values for tree nodes"},
            },
            "required": ["tree_name"],
        },
        failure_patterns={
            "not_found": "Sverchok tree not found — install Sverchok plugin",
            "import_error": "Sverchok not installed — pip install sverchok or add from preferences",
        },
        requires_capability=["blender", "sverchok"],
    ),
    "blender.animation_nodes.run": ToolDef(
        name="blender.animation_nodes.run",
        version="1.0.0",
        description="Kör ett Animation Nodes träd",
        parameters_schema={
            "type": "object",
            "properties": {
                "tree_name": {"type": "string"},
            },
            "required": ["tree_name"],
        },
        requires_capability=["blender", "animation_nodes"],
    ),
    "blender.mesh_machine.chamfer": ToolDef(
        name="blender.mesh_machine.chamfer",
        version="1.0.0",
        description="Chamfer-kanter med Mesh Machine",
        parameters_schema={
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "distance": {"type": "number", "description": "Chamfer distance"},
                "segments": {"type": "integer", "description": "Number of segments"},
            },
            "required": ["object"],
        },
        failure_patterns={
            "import_error": "Mesh Machine not installed: enable mesh_machine addon",
        },
        requires_capability=["blender", "mesh_machine"],
    ),
    "blender.mesh_machine.bevel": ToolDef(
        name="blender.mesh_machine.bevel",
        version="1.0.0",
        description="Bevel-kanter med Mesh Machine",
        parameters_schema={
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "width": {"type": "number"},
                "segments": {"type": "integer"},
            },
            "required": ["object"],
        },
        requires_capability=["blender", "mesh_machine"],
    ),
    "blender.booleans.cut": ToolDef(
        name="blender.booleans.cut",
        version="1.0.0",
        description="Boolean cut med valfritt verktyg (cube, sphere, etc.)",
        parameters_schema={
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "tool": {"type": "string", "enum": ["cube", "sphere", "cylinder", "plane"]},
                "operation": {"type": "string", "enum": ["DIFFERENCE", "UNION", "INTERSECT"]},
            },
            "required": ["object"],
        },
        requires_capability=["blender"],
    ),
    "blender.uv.pack": ToolDef(
        name="blender.uv.pack",
        version="1.0.0",
        description="Packa UV-islands för ett objekt",
        parameters_schema={
            "type": "object",
            "properties": {
                "object": {"type": "string"},
            },
            "required": ["object"],
        },
        requires_capability=["blender"],
    ),
    "blender.geometry_nodes.apply": ToolDef(
        name="blender.geometry_nodes.apply",
        version="1.0.0",
        description="Applicera en Geometry Nodes modifier",
        parameters_schema={
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "modifier_name": {"type": "string"},
            },
            "required": ["object"],
        },
        requires_capability=["blender"],
    ),

    # ── Creative addon tools (Ucupaint / Tissue / A.N.T. Landscape) ─────
    "blender.landscape.generate": ToolDef(
        name="blender.landscape.generate",
        version="1.0.0",
        description="Generera procedurell terräng med A.N.T. Landscape",
        parameters_schema={
            "type": "object",
            "properties": {
                "subdivisions": {"type": "integer"},
                "size": {"type": "number"},
                "height": {"type": "number"},
                "seed": {"type": "integer"},
                "noise_type": {"type": "string", "enum": ["hetero_terrain", "multi_fractal", "hybrid_multi_fractal", "fractal", "ridged_multi_fractal", "vl_noise_turbulence"]},
            },
            "required": [],
        },
        failure_patterns={
            "import_error": "A.N.T. Landscape inte aktiverat — enable ant_landscape (bundled)",
        },
        requires_capability=["blender", "ant_landscape"],
    ),
    "blender.tissue.tessellate": ToolDef(
        name="blender.tissue.tessellate",
        version="1.0.0",
        description="Tessellera ett basobjekt med en komponent via Tissue",
        parameters_schema={
            "type": "object",
            "properties": {
                "base_object": {"type": "string"},
                "component_object": {"type": "string"},
            },
            "required": ["base_object", "component_object"],
        },
        failure_patterns={
            "import_error": "Tissue inte aktiverat — enable tissue extension",
        },
        requires_capability=["blender", "tissue"],
    ),
    "blender.texture.layer": ToolDef(
        name="blender.texture.layer",
        version="1.0.0",
        description="Lägg till ett texturlager på ett objekt via Ucupaint",
        parameters_schema={
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "layer_name": {"type": "string"},
                "layer_type": {"type": "string", "enum": ["COLOR", "IMAGE", "NORMAL", "MASK"]},
                "color": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
            },
            "required": ["object"],
        },
        failure_patterns={
            "import_error": "Ucupaint inte installerat — enable ucupaint addon",
        },
        requires_capability=["blender", "ucupaint"],
    ),
}
