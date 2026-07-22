import asyncio
import json
import re
import subprocess
import tempfile
import base64
import os
from typing import Optional

from mcp_servers.base_mcp_server import BaseMCPServer


# ── Charter Article 4.3 — sandbox defaults ─────────────────────────────────
# `blender.execute_script` runs *agent-authored* Python inside the Blender
# process. Per CHARTER.md Article 4.3, this ambassador declares its own
# forbidden-pattern list and makes it visible in the witness log at startup.
#
# The list guards ONLY sandbox-escape routes — process, filesystem, network
# and dynamic-eval primitives an agent could use to leave its territory. The
# entire *creative* Blender surface (bpy, bmesh, mathutils, geometry nodes,
# materials, modifiers, procedural generation) is deliberately left untouched:
# Article 4.3 is a fence around the yard, not a cage around the agent. If a
# capability is genuinely dangerous, amend the capability (Article 7) — do not
# lobotomise the creative API.
#
# Patterns are (human_label, regex) pairs. Word boundaries and negative
# lookbehinds keep them from tripping on creative code such as `retrieval`,
# `transform`, `import mathutils` or `bpy.data.images.load(...)`.
FORBIDDEN_SCRIPT_PATTERNS = [
    ("import os", r"\bimport\s+os\b"),
    ("import sys", r"\bimport\s+sys\b"),
    ("import subprocess", r"\bimport\s+subprocess\b"),
    ("import shutil", r"\bimport\s+shutil\b"),
    ("import socket", r"\bimport\s+socket\b"),
    ("from os", r"\bfrom\s+os\b"),
    ("from sys", r"\bfrom\s+sys\b"),
    ("from subprocess", r"\bfrom\s+subprocess\b"),
    ("__import__(", r"\b__import__\s*\("),
    ("exec(", r"(?<![\w.])exec\s*\("),
    ("eval(", r"(?<![\w.])eval\s*\("),
    ("os.system(", r"\bos\.system\s*\("),
    ("subprocess call", r"\bsubprocess\s*\."),
    ("open(", r"(?<![\w.])open\s*\("),
]


class BlenderMCPServer(BaseMCPServer):
    def __init__(self, blender_path: str = "blender"):
        super().__init__("blender")
        self.blender_path = blender_path
        # Charter Article 4.3 — compile the forbidden-pattern list once and
        # expose the human-readable labels for the witness log and for audits.
        self._forbidden_patterns = [
            (label, re.compile(pattern)) for label, pattern in FORBIDDEN_SCRIPT_PATTERNS
        ]
        self.forbidden_patterns = [label for label, _ in FORBIDDEN_SCRIPT_PATTERNS]
        self._setup_tools()
        self._log_sandbox_policy()

    def _log_sandbox_policy(self) -> None:
        """Charter Article 4.3 — make the fence legible.

        The forbidden-pattern list is published to the witness log at startup
        so an agent can see the exact shape of its sandbox. The creative
        Blender API is never part of this list, by design.
        """
        self.logger.info(
            "Charter 4.3 sandbox active for blender.execute_script — "
            "forbidden escape patterns: %s",
            ", ".join(self.forbidden_patterns),
        )
        self.logger.info(
            "Charter 4.3 — creative surface unrestricted: bpy, bmesh, "
            "mathutils, geometry nodes, materials, modifiers, procedural gen."
        )

    def _check_script_sandbox(self, script: str) -> Optional[str]:
        """Charter Article 4.3 gate for agent-authored scripts.

        Returns the label of the first forbidden escape pattern found, or
        None if the script is clear to run. Only sandbox-escape primitives
        (process, filesystem, network, dynamic-eval) are inspected; the
        creative Blender API is intentionally never matched.
        """
        for label, pattern in self._forbidden_patterns:
            if pattern.search(script):
                return label
        return None

    def _setup_tools(self):
        @self.register("blender.get_scene_info")
        async def get_scene_info():
            script = """
import bpy, json
scene = bpy.context.scene
objects = []
for obj in bpy.data.objects:
    objects.append({
        "name": obj.name,
        "type": obj.type,
        "location": list(obj.location),
        "vertices": len(obj.data.vertices) if hasattr(obj.data, 'vertices') else 0,
    })
print(json.dumps({"objects": objects, "mode": bpy.context.mode}))
"""
            return await self._run_blender_script(script)

        @self.register("blender.create_object")
        async def create_object(type: str = "cube", location: list = None, name: str = None, size: float = 2.0):
            if location is None:
                location = [0, 0, 0]
            loc_str = json.dumps(location)
            name_str = json.dumps(name) if name else "None"
            script = f"""
import bpy, json
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.object.mode_set(mode='OBJECT')
loc = {loc_str}
if "{type}" == "cube":
    bpy.ops.mesh.primitive_cube_add(size={size}, location=loc)
elif "{type}" == "sphere":
    bpy.ops.mesh.primitive_uv_sphere_add(radius={size/2}, location=loc)
elif "{type}" == "cylinder":
    bpy.ops.mesh.primitive_cylinder_add(radius={size/2}, depth={size}, location=loc)
elif "{type}" == "plane":
    bpy.ops.mesh.primitive_plane_add(size={size}, location=loc)
elif "{type}" == "monkey":
    bpy.ops.mesh.primitive_monkey_add(size={size}, location=loc)
obj = bpy.context.active_object
if {name_str}:
    obj.name = {name_str}
print(json.dumps({{"name": obj.name, "vertices": len(obj.data.vertices)}}))
"""
            return await self._run_blender_script(script)

        @self.register("blender.modify_object")
        async def modify_object(object: str, operation: str, value: list):
            val_str = json.dumps(value)
            script = f"""
import bpy, json
obj = bpy.data.objects.get("{object}")
if not obj:
    print(json.dumps({{"error": "Object not found: {object}"}}))
else:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    if "{operation}" == "extrude":
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={{'value': {val_str}}})
        bpy.ops.object.mode_set(mode='OBJECT')
    elif "{operation}" == "scale":
        bpy.ops.transform.resize(value={val_str})
    elif "{operation}" == "rotate":
        bpy.ops.transform.rotate(value={val_str[2]})
    elif "{operation}" == "translate":
        bpy.ops.transform.translate(value={val_str})
    elif "{operation}" == "delete":
        bpy.ops.object.delete()
    elif "{operation}" == "duplicate":
        bpy.ops.object.duplicate()
    print(json.dumps({{"object": obj.name, "vertices": len(obj.data.vertices) if hasattr(obj.data, 'vertices') else 0}}))
"""
            return await self._run_blender_script(script)

        @self.register("blender.set_material")
        async def set_material(object: str, color: list, material_name: str = None):
            col_str = json.dumps(color)
            mat_str = json.dumps(material_name) if material_name else "None"
            script = f"""
import bpy, json
obj = bpy.data.objects.get("{object}")
if not obj:
    print(json.dumps({{"error": "Object not found"}}))
else:
    mat = bpy.data.materials.new(name={mat_str} or f"mat_{{obj.name}}")
    mat.use_nodes = False
    mat.diffuse_color = {col_str}
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    print(json.dumps({{"material": mat.name, "color": {col_str}}}))
"""
            return await self._run_blender_script(script)

        @self.register("blender.render")
        async def render(output_path: str = "/tmp/render.png", resolution_x: int = 1920, resolution_y: int = 1080):
            script = f"""
import bpy
bpy.context.scene.render.resolution_x = {resolution_x}
bpy.context.scene.render.resolution_y = {resolution_y}
bpy.context.scene.render.filepath = "{output_path}"
bpy.ops.render.render(write_still=True)
print('{{"output": "{output_path}"}}')
"""
            return await self._run_blender_script(script)

        @self.register("blender.get_viewport")
        async def get_viewport():
            script = """
import bpy, base64, tempfile, os
with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
    path = f.name
bpy.context.scene.render.filepath = path
bpy.ops.render.opengl(write_still=True, view_context=True)
with open(path, 'rb') as f:
    data = base64.b64encode(f.read()).decode()
os.unlink(path)
print('{"screenshot": "' + data[:100] + '...", "format": "png"}')
"""
            return await self._run_blender_script(script)

        @self.register("blender.undo")
        async def undo():
            script = """
import bpy
bpy.ops.ed.undo()
print('{"status": "undone"}')
"""
            return await self._run_blender_script(script)

        @self.register("blender.execute_script")
        async def execute_script(script: str):
            # Charter Article 4.3 — inspect the agent's script for sandbox-
            # escape patterns *before* it reaches the Blender process. A
            # rejection is a logged, structured refusal (Article 3.1 witness
            # integrity), never a silent drop and never a crash.
            violation = self._check_script_sandbox(script)
            if violation is not None:
                self.logger.warning(
                    "Charter 4.3 refusal: blender.execute_script blocked "
                    "forbidden pattern %r",
                    violation,
                )
                return {
                    "success": False,
                    "charter_article": "4.3",
                    "forbidden_pattern": violation,
                    "error": (
                        "Script rejected by Charter Article 4.3 sandbox: "
                        f"forbidden pattern '{violation}'. The creative "
                        "Blender API is fully open; only sandbox-escape "
                        "primitives are blocked. For filesystem access, use "
                        "the guarded file.* tools (Article 4.4)."
                    ),
                }
            wrapped = f"""
import json
try:
    {script}
    print('{{"status": "ok"}}')
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
            return await self._run_blender_script(wrapped)

        # ── Plugin integrations ────────────────────────────────
        @self.register("blender.sverchok.generate")
        async def sverchok_generate(tree_name: str, inputs: dict = None):
            inp = json.dumps(inputs or {})
            script = f"""
import bpy, json
try:
    import sverchok
    tree = bpy.data.node_groups.get("{tree_name}")
    if not tree:
        print(json.dumps({{"error": "Sverchok tree not found: {tree_name}"}}))
    else:
        for name, val in {inp}.items():
            if name in tree.nodes:
                n = tree.nodes[name]
                if hasattr(n, 'value'):
                    n.value = val
        sverchok.core.update_system.process_tree(tree)
        print(json.dumps({{"tree": "{tree_name}", "status": "processed"}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
            return await self._run_blender_script(script)

        @self.register("blender.animation_nodes.run")
        async def animation_nodes_run(tree_name: str):
            script = f"""
import bpy, json
try:
    from animation_nodes.id_keys import setup_id_keys
    tree = bpy.data.node_groups.get("{tree_name}")
    if not tree:
        print(json.dumps({{"error": "AN tree not found: {tree_name}"}}))
    else:
        tree.auto_execute = True
        print(json.dumps({{"tree": "{tree_name}", "status": "running"}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
            return await self._run_blender_script(script)

        @self.register("blender.mesh_machine.chamfer")
        async def mesh_machine_chamfer(object: str, distance: float = 0.1, segments: int = 1):
            script = f"""
import bpy, json
try:
    from mesh_machine import main
    obj = bpy.data.objects.get("{object}")
    if not obj:
        print(json.dumps({{"error": "Object not found: {object}"}}))
    else:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mm.chamfer(distance={distance}, segments={segments})
        bpy.ops.object.mode_set(mode='OBJECT')
        print(json.dumps({{"object": obj.name, "chamfer": {distance}}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
            return await self._run_blender_script(script)

        @self.register("blender.mesh_machine.bevel")
        async def mesh_machine_bevel(object: str, width: float = 0.05, segments: int = 2):
            script = f"""
import bpy, json
try:
    from mesh_machine import main
    obj = bpy.data.objects.get("{object}")
    if not obj:
        print(json.dumps({{"error": "Object not found: {object}"}}))
    else:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mm.bevel(width={width}, segments={segments})
        bpy.ops.object.mode_set(mode='OBJECT')
        print(json.dumps({{"object": obj.name, "bevel": {width}}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
            return await self._run_blender_script(script)

        @self.register("blender.booleans.cut")
        async def boxcutter_cut(object: str, tool: str = "cube", operation: str = "DIFFERENCE"):
            script = f"""
import bpy, json
try:
    bpy.context.view_layer.objects.active = bpy.data.objects.get("{object}")
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.mesh.primitive_{tool}_add(size=2, location=(0, 0, 0))
    cutter = bpy.context.active_object
    mod = bpy.data.objects["{object}"].modifiers.new(name="BC", type='BOOLEAN')
    mod.operation = '{operation}'
    mod.object = cutter
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    print(json.dumps({{"object": "{object}", "operation": "{operation}"}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
            return await self._run_blender_script(script)

        @self.register("blender.uv.pack")
        async def uv_pack(object: str):
            script = f"""
import bpy, json
try:
    obj = bpy.data.objects.get("{object}")
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.pack_islands()
    bpy.ops.object.mode_set(mode='OBJECT')
    print(json.dumps({{"object": "{object}", "uv": "packed"}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
            return await self._run_blender_script(script)

        @self.register("blender.geometry_nodes.apply")
        async def geometry_nodes_apply(object: str, modifier_name: str = "Geometry Nodes"):
            script = f"""
import bpy, json
try:
    obj = bpy.data.objects.get("{object}")
    if not obj:
        print(json.dumps({{"error": "Object not found: {object}"}}))
    else:
        bpy.context.view_layer.objects.active = obj
        for mod in obj.modifiers:
            if mod.type == 'NODES' and mod.name == '{modifier_name}':
                bpy.ops.object.modifier_apply(modifier=mod.name)
                print(json.dumps({{"object": obj.name, "modifier": mod.name}}))
                break
        else:
            print(json.dumps({{"error": "No Geometry Nodes modifier found"}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
            return await self._run_blender_script(script)

        # ── Creative addon tools (declarative — see docs/blender-addons.md) ──
        @self.register("blender.landscape.generate")
        async def landscape_generate(subdivisions: int = 128, size: float = 4.0,
                                     height: float = 0.5, seed: int = 0,
                                     noise_type: str = "hetero_terrain"):
            script = f"""
import bpy, json
try:
    import addon_utils
    addon_utils.enable("ant_landscape", default_set=False)
    bpy.ops.mesh.landscape_add(
        subdivision_x={int(subdivisions)}, subdivision_y={int(subdivisions)},
        mesh_size_x={float(size)}, mesh_size_y={float(size)},
        height={float(height)}, random_seed={int(seed)},
        noise_type="{noise_type}",
    )
    obj = bpy.context.active_object
    print(json.dumps({{"object": obj.name, "verts": len(obj.data.vertices)}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
            return await self._run_blender_script(script)

        @self.register("blender.tissue.tessellate")
        async def tissue_tessellate(base_object: str, component_object: str):
            script = f"""
import bpy, json
try:
    import addon_utils
    addon_utils.enable("tissue", default_set=False)
    base = bpy.data.objects.get("{base_object}")
    comp = bpy.data.objects.get("{component_object}")
    if not base or not comp:
        print(json.dumps({{"error": "base or component object not found"}}))
    else:
        bpy.context.view_layer.objects.active = base
        base.select_set(True)
        bpy.ops.object.tissue_tessellate(component="{component_object}", generator="{base_object}")
        print(json.dumps({{"base": "{base_object}", "component": "{component_object}", "status": "tessellated"}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
            return await self._run_blender_script(script)

        @self.register("blender.texture.layer")
        async def texture_layer(object: str, layer_name: str = "Layer",
                                layer_type: str = "COLOR", color: list = None):
            col = json.dumps(color or [0.8, 0.8, 0.8, 1.0])
            script = f"""
import bpy, json
try:
    import addon_utils
    addon_utils.enable("ucupaint", default_set=False)
    obj = bpy.data.objects.get("{object}")
    if not obj:
        print(json.dumps({{"error": "Object not found: {object}"}}))
    else:
        bpy.context.view_layer.objects.active = obj
        try:
            bpy.ops.node.y_new_layer(name="{layer_name}")
            status = "layer added"
        except Exception as inner:
            status = f"ucupaint op unavailable: {{inner}}"
        print(json.dumps({{"object": "{object}", "layer": "{layer_name}", "type": "{layer_type}", "color": {col}, "status": status}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
            return await self._run_blender_script(script)

    async def _run_blender_script(self, script: str) -> dict:
        try:
            proc = await asyncio.create_subprocess_exec(
                self.blender_path, "--background", "--python-expr", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                return {"success": False, "error": stderr.decode()[:500]}
            output = stdout.decode().strip().split("\n")[-1]
            try:
                result = json.loads(output)
                result["success"] = True
                return result
            except json.JSONDecodeError:
                return {"success": True, "raw_output": output[:500]}
        except asyncio.TimeoutError:
            return {"success": False, "error": "Blender timeout (30s)"}
        except FileNotFoundError:
            return {"success": False, "error": "Blender not found. Install or set blender_path."}


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    server = BlenderMCPServer()
    asyncio.run(server.run_stdio())
