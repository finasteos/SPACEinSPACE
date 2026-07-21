#!/usr/bin/env python3
"""Build a 3D Neo-Japanese Minimalist ("Neon Noir") Scene in Blender.

Creates:
  1. Glossy Obsidian Mirror Ground (high reflectivity, dark base)
  2. Minimalist Cyan Wireframe Torii Arch (無 - Mu Nexus)
  3. Floating Cyber Yellow Goal Monoliths (計画 - Keikaku)
  4. Glowing Electric Cyan Memory Pillars (記憶 - Kioku)
  5. Cinematic camera & atmospheric lighting

Usage:
  $ blender --background --python scripts/create_neo_minimal_world.py
"""

import sys

def build_scene():
    try:
        import bpy  # type: ignore
    except ImportError:
        print("❌ Error: 'bpy' not available. Run this script using Blender:")
        print("   blender --background --python scripts/create_neo_minimal_world.py")
        sys.exit(1)

    print("🌟 Constructing 3D Neo-Japanese Minimalist World...")

    # 1. Clear existing scene
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    # 2. World Environment setup (pitch dark)
    world = bpy.context.scene.world
    if not world:
        world = bpy.data.worlds.new("NeoWorld")
        bpy.context.scene.world = world
    world.use_nodes = True
    bg_node = world.node_tree.nodes.get("Background")
    if bg_node:
        bg_node.inputs["Color"].default_value = (0.02, 0.02, 0.03, 1.0)
        bg_node.inputs["Strength"].default_value = 0.5

    # 3. Helper: Create Material
    def create_material(name, color_rgba, roughness=0.1, metallic=0.9, emission_color=None, emission_strength=0.0):
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = color_rgba
            bsdf.inputs["Roughness"].default_value = roughness
            bsdf.inputs["Metallic"].default_value = metallic
            if emission_color and "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = emission_color
                bsdf.inputs["Emission Strength"].default_value = emission_strength
            elif emission_color and "Emission" in bsdf.inputs:
                bsdf.inputs["Emission"].default_value = emission_color
        return mat

    # Materials
    mat_obsidian = create_material("Mat_ObsidianMirror", (0.02, 0.02, 0.03, 1.0), roughness=0.05, metallic=0.95)
    mat_cyan_glow = create_material("Mat_CyanGlow", (0.0, 0.94, 1.0, 1.0), roughness=0.2, metallic=0.0, emission_color=(0.0, 0.94, 1.0, 1.0), emission_strength=8.0)
    mat_yellow_glow = create_material("Mat_YellowGlow", (1.0, 0.9, 0.0, 1.0), roughness=0.2, metallic=0.0, emission_color=(1.0, 0.9, 0.0, 1.0), emission_strength=10.0)

    # 4. Obsidian Mirror Floor (Plane size 100)
    bpy.ops.mesh.primitive_plane_add(size=100, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "Obsidian_Mirror_Floor"
    floor.data.materials.append(mat_obsidian)

    # 5. Abstract Torii Arch (Cyan Wireframe Structure)
    # Left Column
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-4, 0, 4))
    col1 = bpy.context.active_object
    col1.scale = (0.3, 0.3, 8.0)
    col1.data.materials.append(mat_cyan_glow)

    # Right Column
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(4, 0, 4))
    col2 = bpy.context.active_object
    col2.scale = (0.3, 0.3, 8.0)
    col2.data.materials.append(mat_cyan_glow)

    # Top Beam
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 8.2))
    beam = bpy.context.active_object
    beam.scale = (10.0, 0.4, 0.4)
    beam.data.materials.append(mat_cyan_glow)

    # 6. Floating Cyber Yellow Goal Monolith (計画 - Keikaku)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 3, 3))
    monolith = bpy.context.active_object
    monolith.name = "Goal_Monolith_Yellow"
    monolith.scale = (1.2, 1.2, 5.0)
    monolith.rotation_euler = (0, 0, 0.785)  # 45 deg rotation
    monolith.data.materials.append(mat_yellow_glow)

    # 7. Floating Memory Pillars (記憶 - Kioku)
    positions = [(-6, -4, 2.5), (6, -4, 2.5), (-6, 6, 3.5)]
    for i, pos in enumerate(positions):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.4, depth=4.0, location=pos)
        pil = bpy.context.active_object
        pil.name = f"Memory_Pillar_{i+1}"
        pil.data.materials.append(mat_cyan_glow)

    # 8. Camera Setup
    bpy.ops.object.camera_add(location=(14, -16, 9), rotation=(1.1, 0, 0.7))
    cam = bpy.context.active_object
    bpy.context.scene.camera = cam

    # 9. Lighting Point Lights
    bpy.ops.object.light_add(type='POINT', location=(0, 0, 10))
    light = bpy.context.active_object
    light.data.energy = 500
    light.data.color = (0.0, 0.94, 1.0)

    print("✅ Scene generation completed successfully!")

if __name__ == "__main__":
    build_scene()
