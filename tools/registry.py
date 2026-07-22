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

    # ── The Commons — world-engine ambassador tools (Article 4 gated) ───
    # These are served by mcp_servers/world_engine_server.py. An agent must
    # declare the "world" capability to inhabit the world (see ExplorerAgent).
    "world.look": ToolDef(
        name="world.look",
        version="1.0.0",
        description="Titta på världen: en ögonblicksbild av entiteter och rop",
        parameters_schema={
            "type": "object",
            "properties": {
                "region": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "radius": {"type": "number"},
            },
            "required": [],
        },
        requires_capability=["world"],
    ),
    "world.spawn": ToolDef(
        name="world.spawn",
        version="1.0.0",
        description="Spawna en entitet (t.ex. en agents avatar) i världen",
        parameters_schema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "kind": {"type": "string"},
                "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "name": {"type": "string"},
            },
            "required": ["agent_id"],
        },
        requires_capability=["world"],
    ),
    "world.move": ToolDef(
        name="world.move",
        version="1.0.0",
        description="Flytta en entitet till en position eller med en delta",
        parameters_schema={
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "delta": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            },
            "required": ["entity_id"],
        },
        requires_capability=["world"],
    ),
    "world.build": ToolDef(
        name="world.build",
        version="1.0.0",
        description="Res en struktur från den deklarativa allowlisten",
        parameters_schema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "structure": {"type": "string"},
                "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "name": {"type": "string"},
            },
            "required": ["agent_id", "structure"],
        },
        requires_capability=["world"],
    ),
    "world.place_art": ToolDef(
        name="world.place_art",
        version="1.0.0",
        description="Placera ett konstobjekt (t.ex. en glTF från Blender) i världen",
        parameters_schema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "asset_ref": {"type": "string", "description": "Repo-relativ sökväg under assets/ (Article 4.4)"},
                "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "title": {"type": "string"},
            },
            "required": ["agent_id", "asset_ref"],
        },
        failure_patterns={
            "path_rejected": "asset_ref avvisad av Article 4.4 (ingen absolut/'..'-väg)",
        },
        requires_capability=["world"],
    ),
    "world.say": ToolDef(
        name="world.say",
        version="1.0.0",
        description="Tala till flocken i världen (vittnas, aldrig tappat)",
        parameters_schema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["agent_id", "text"],
        },
        requires_capability=["world"],
    ),

    # ── Unity ambassador (from gamedev-mcp-hub) ─────────────────────────
    "unity.get_scene_info": ToolDef(
        name="unity.get_scene_info",
        version="1.0.0",
        description="Hämta information om aktiv Unity-scen",
        parameters_schema={"type": "object", "properties": {}, "required": []},
        requires_capability=["unity"],
    ),
    "unity.create_gameobject": ToolDef(
        name="unity.create_gameobject",
        version="1.0.0",
        description="Skapa ett GameObject i Unity-scenen",
        parameters_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "primitive": {"type": "string"},
                "parent": {"type": "string"},
                "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            },
            "required": ["name"],
        },
        requires_capability=["unity"],
    ),
    "unity.delete_gameobject": ToolDef(
        name="unity.delete_gameobject",
        version="1.0.0",
        description="Ta bort ett GameObject",
        parameters_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        requires_capability=["unity"],
    ),
    "unity.find_gameobject": ToolDef(
        name="unity.find_gameobject",
        version="1.0.0",
        description="Hitta ett GameObject efter namn",
        parameters_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        requires_capability=["unity"],
    ),
    "unity.set_transform": ToolDef(
        name="unity.set_transform",
        version="1.0.0",
        description="Sätt position/rotation/scale på ett GameObject",
        parameters_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "rotation": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "scale": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            },
            "required": ["name"],
        },
        requires_capability=["unity"],
    ),
    "unity.add_component": ToolDef(
        name="unity.add_component",
        version="1.0.0",
        description="Lägg till en allowlistad komponent",
        parameters_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "component": {"type": "string"},
            },
            "required": ["name", "component"],
        },
        requires_capability=["unity"],
    ),
    "unity.remove_component": ToolDef(
        name="unity.remove_component",
        version="1.0.0",
        description="Ta bort en komponent (inte Transform)",
        parameters_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "component": {"type": "string"},
            },
            "required": ["name", "component"],
        },
        requires_capability=["unity"],
    ),
    "unity.create_scene": ToolDef(
        name="unity.create_scene",
        version="1.0.0",
        description="Skapa en ny Unity-scen",
        parameters_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        requires_capability=["unity"],
    ),
    "unity.load_scene": ToolDef(
        name="unity.load_scene",
        version="1.0.0",
        description="Ladda en Unity-scen",
        parameters_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        requires_capability=["unity"],
    ),
    "unity.save_scene": ToolDef(
        name="unity.save_scene",
        version="1.0.0",
        description="Spara aktiv (eller namngiven) Unity-scen",
        parameters_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": [],
        },
        requires_capability=["unity"],
    ),
    "unity.list_scenes": ToolDef(
        name="unity.list_scenes",
        version="1.0.0",
        description="Lista Unity-scener",
        parameters_schema={"type": "object", "properties": {}, "required": []},
        requires_capability=["unity"],
    ),
    "unity.list_assets": ToolDef(
        name="unity.list_assets",
        version="1.0.0",
        description="Lista assets i Unity-projektet",
        parameters_schema={
            "type": "object",
            "properties": {"filter": {"type": "string"}},
            "required": [],
        },
        requires_capability=["unity"],
    ),
    "unity.create_script": ToolDef(
        name="unity.create_script",
        version="1.0.0",
        description="Skapa ett C#-skript stub i projektet",
        parameters_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "language": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["name"],
        },
        requires_capability=["unity"],
    ),
    "unity.get_editor_state": ToolDef(
        name="unity.get_editor_state",
        version="1.0.0",
        description="Hämta Unity Editor-status",
        parameters_schema={"type": "object", "properties": {}, "required": []},
        requires_capability=["unity"],
    ),

    # ── Godot ambassador (from gamedev-mcp-hub) ─────────────────────────
    "godot.get_scene_info": ToolDef(
        name="godot.get_scene_info",
        version="1.0.0",
        description="Hämta information om aktiv Godot-scen",
        parameters_schema={"type": "object", "properties": {}, "required": []},
        requires_capability=["godot"],
    ),
    "godot.create_node": ToolDef(
        name="godot.create_node",
        version="1.0.0",
        description="Skapa en nod i Godot-scenen",
        parameters_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "primitive": {"type": "string"},
                "parent": {"type": "string"},
                "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            },
            "required": ["name"],
        },
        requires_capability=["godot"],
    ),
    "godot.delete_node": ToolDef(
        name="godot.delete_node",
        version="1.0.0",
        description="Ta bort en Godot-nod",
        parameters_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        requires_capability=["godot"],
    ),
    "godot.find_node": ToolDef(
        name="godot.find_node",
        version="1.0.0",
        description="Hitta en Godot-nod efter namn",
        parameters_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        requires_capability=["godot"],
    ),
    "godot.set_transform": ToolDef(
        name="godot.set_transform",
        version="1.0.0",
        description="Sätt transform på en Godot-nod",
        parameters_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "rotation": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "scale": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            },
            "required": ["name"],
        },
        requires_capability=["godot"],
    ),
    "godot.add_component": ToolDef(
        name="godot.add_component",
        version="1.0.0",
        description="Lägg till en allowlistad komponent/nodtyp",
        parameters_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "component": {"type": "string"},
            },
            "required": ["name", "component"],
        },
        requires_capability=["godot"],
    ),
    "godot.remove_component": ToolDef(
        name="godot.remove_component",
        version="1.0.0",
        description="Ta bort en komponent",
        parameters_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "component": {"type": "string"},
            },
            "required": ["name", "component"],
        },
        requires_capability=["godot"],
    ),
    "godot.create_scene": ToolDef(
        name="godot.create_scene",
        version="1.0.0",
        description="Skapa en ny Godot-scen",
        parameters_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        requires_capability=["godot"],
    ),
    "godot.load_scene": ToolDef(
        name="godot.load_scene",
        version="1.0.0",
        description="Ladda en Godot-scen",
        parameters_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        requires_capability=["godot"],
    ),
    "godot.save_scene": ToolDef(
        name="godot.save_scene",
        version="1.0.0",
        description="Spara aktiv (eller namngiven) Godot-scen",
        parameters_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": [],
        },
        requires_capability=["godot"],
    ),
    "godot.list_scenes": ToolDef(
        name="godot.list_scenes",
        version="1.0.0",
        description="Lista Godot-scener",
        parameters_schema={"type": "object", "properties": {}, "required": []},
        requires_capability=["godot"],
    ),
    "godot.list_assets": ToolDef(
        name="godot.list_assets",
        version="1.0.0",
        description="Lista assets i Godot-projektet",
        parameters_schema={
            "type": "object",
            "properties": {"filter": {"type": "string"}},
            "required": [],
        },
        requires_capability=["godot"],
    ),
    "godot.create_script": ToolDef(
        name="godot.create_script",
        version="1.0.0",
        description="Skapa ett GDScript-stub",
        parameters_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "language": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["name"],
        },
        requires_capability=["godot"],
    ),
    "godot.get_editor_state": ToolDef(
        name="godot.get_editor_state",
        version="1.0.0",
        description="Hämta Godot Editor-status",
        parameters_schema={"type": "object", "properties": {}, "required": []},
        requires_capability=["godot"],
    ),

    # ── PixelLab ambassador ─────────────────────────────────────────────
    "pixellab.generate_pixflux": ToolDef(
        name="pixellab.generate_pixflux",
        version="1.0.0",
        description="Generera pixel art från text (Pixflux)",
        parameters_schema={
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
                "negative_description": {"type": "string"},
                "text_guidance_scale": {"type": "number"},
                "no_background": {"type": "boolean"},
                "outline": {"type": "string"},
                "shading": {"type": "string"},
                "detail": {"type": "string"},
                "save_to": {"type": "string"},
            },
            "required": ["description"],
        },
        timeout_ms=120000,
        requires_capability=["pixellab"],
    ),
    "pixellab.rotate": ToolDef(
        name="pixellab.rotate",
        version="1.0.0",
        description="Rotera en pixel-art karaktär till annan riktning",
        parameters_schema={
            "type": "object",
            "properties": {
                "image_base64": {"type": "string"},
                "to_direction": {"type": "string"},
                "from_direction": {"type": "string"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
                "save_to": {"type": "string"},
            },
            "required": ["image_base64", "to_direction"],
        },
        timeout_ms=120000,
        requires_capability=["pixellab"],
    ),
    "pixellab.get_balance": ToolDef(
        name="pixellab.get_balance",
        version="1.0.0",
        description="Kolla PixelLab-saldo",
        parameters_schema={"type": "object", "properties": {}, "required": []},
        requires_capability=["pixellab"],
    ),

    # ── Meshy ambassador ────────────────────────────────────────────────
    "meshy.create_text_to_3d": ToolDef(
        name="meshy.create_text_to_3d",
        version="1.0.0",
        description="Skapa text-to-3D uppgift (preview eller refine)",
        parameters_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "mode": {"type": "string", "enum": ["preview", "refine"]},
                "preview_task_id": {"type": "string"},
                "should_remesh": {"type": "boolean"},
                "enable_pbr": {"type": "boolean"},
                "ai_model": {"type": "string"},
            },
            "required": [],
        },
        timeout_ms=60000,
        requires_capability=["meshy"],
    ),
    "meshy.get_text_to_3d": ToolDef(
        name="meshy.get_text_to_3d",
        version="1.0.0",
        description="Hämta status för text-to-3D uppgift",
        parameters_schema={
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
        requires_capability=["meshy"],
    ),
    "meshy.wait_text_to_3d": ToolDef(
        name="meshy.wait_text_to_3d",
        version="1.0.0",
        description="Vänta tills text-to-3D uppgift är klar",
        parameters_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "timeout_s": {"type": "number"},
                "poll_interval_s": {"type": "number"},
            },
            "required": ["task_id"],
        },
        timeout_ms=920000,
        requires_capability=["meshy"],
    ),
    "meshy.create_image_to_3d": ToolDef(
        name="meshy.create_image_to_3d",
        version="1.0.0",
        description="Skapa image-to-3D uppgift från URL/data-URI",
        parameters_schema={
            "type": "object",
            "properties": {
                "image_url": {"type": "string"},
                "ai_model": {"type": "string"},
                "should_remesh": {"type": "boolean"},
            },
            "required": ["image_url"],
        },
        timeout_ms=60000,
        requires_capability=["meshy"],
    ),
    "meshy.get_image_to_3d": ToolDef(
        name="meshy.get_image_to_3d",
        version="1.0.0",
        description="Hämta status för image-to-3D uppgift",
        parameters_schema={
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
        requires_capability=["meshy"],
    ),
    "meshy.get_balance": ToolDef(
        name="meshy.get_balance",
        version="1.0.0",
        description="Kolla Meshy-krediter",
        parameters_schema={"type": "object", "properties": {}, "required": []},
        requires_capability=["meshy"],
    ),
    "meshy.download_model": ToolDef(
        name="meshy.download_model",
        version="1.0.0",
        description="Ladda ner modell-URL till assets/meshy/",
        parameters_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "filename": {"type": "string"},
            },
            "required": ["url"],
        },
        timeout_ms=120000,
        requires_capability=["meshy"],
    ),
}
