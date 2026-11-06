"""Headless Blender: render a rounded "product box" turntable to PNG frames / MP4.

  blender -b -P scripts/blender_turntable.py -- --label "FFmpeg" --out out/blender/ --frames 72

Then drop the result into HyperFrames/Remotion as a <video>, or composite with FFmpeg.
For interactive, prompt-driven modelling, use mcp-for-blender instead (see .mcp.json).
"""
import argparse
import math
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--label", default="VIDEO STUDIO")
ap.add_argument("--out", default="out/blender/")
ap.add_argument("--frames", type=int, default=72)
ap.add_argument("--engine", default="BLENDER_EEVEE_NEXT", help="BLENDER_EEVEE_NEXT / CYCLES")
args = ap.parse_args(argv)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
try:
    scene.render.engine = args.engine
except TypeError:
    scene.render.engine = "CYCLES"
scene.render.resolution_x, scene.render.resolution_y = 1080, 1080
scene.frame_start, scene.frame_end = 1, args.frames
scene.render.filepath = args.out
scene.render.image_settings.file_format = "PNG"

# box
bpy.ops.mesh.primitive_cube_add(size=2)
box = bpy.context.active_object
box.scale = (1.2, 0.5, 1.0)
bev = box.modifiers.new("bevel", "BEVEL")
bev.width, bev.segments = 0.12, 6
mat = bpy.data.materials.new("box")
mat.use_nodes = True
mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.85, 0.35, 0.22, 1)
box.data.materials.append(mat)

# label
bpy.ops.object.text_add(location=(0, -0.52, 0.0), rotation=(math.radians(90), 0, 0))
txt = bpy.context.active_object
txt.data.body = args.label
txt.data.align_x = "CENTER"
txt.data.size = 0.32
txt.data.extrude = 0.01
txt.parent = box

# turntable
box.rotation_euler = (0, 0, 0)
box.keyframe_insert("rotation_euler", frame=1)
box.rotation_euler = (0, 0, math.radians(360))
box.keyframe_insert("rotation_euler", frame=args.frames + 1)
for fc in box.animation_data.action.fcurves if hasattr(box.animation_data.action, "fcurves") else []:
    for kp in fc.keyframe_points:
        kp.interpolation = "LINEAR"

# camera + lights + world
bpy.ops.object.camera_add(location=(0, -6.5, 1.6), rotation=(math.radians(80), 0, 0))
scene.camera = bpy.context.active_object
bpy.ops.object.light_add(type="AREA", location=(3, -3, 4))
bpy.context.active_object.data.energy = 800
bpy.ops.object.light_add(type="AREA", location=(-3, -2, 2))
bpy.context.active_object.data.energy = 300
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.03, 0.04, 0.05, 1)
scene.world = world

bpy.ops.render.render(animation=True)
print(f"frames -> {args.out}  (ffmpeg -framerate 24 -i {args.out}%04d.png -pix_fmt yuv420p turntable.mp4)")
