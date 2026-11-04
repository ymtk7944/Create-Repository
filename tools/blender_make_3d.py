"""三面図（背景透過済み）から Blender(bpy) で 3D モデル(GLB)を作る。

使い方:
    python3 tools/blender_make_3d.py <透過PNG> <出力GLB> [プレビュー出力ディレクトリ]
    # Blender 本体なら: blender -b -P tools/blender_make_3d.py -- <透過PNG> <出力GLB>

入力は「正面 / 左側面(人物が画面左を向く) / 右側面 / 背面」が横に並んだ
背景透過 PNG（tools/blender_remove_bg.py の出力）を想定。

処理:
  1. 4 体のシルエットを取り出し、身長をそろえる
  2. 正面シルエット(幅) × 側面シルエット(奥行き) から、
     断面を楕円寄りに丸めた立体（ビジュアルハル）をボクセルで作る
  3. マーチングキューブでメッシュ化 → Blender で平滑化・軽量化
  4. 面の向きに応じて 正面/背面/左右側面 の絵を投影して UV を張る
  5. テクスチャを埋め込んだ GLB として書き出す
"""
import math
import os
import sys

import bpy
import numpy as np
from PIL import Image
from scipy import ndimage
from skimage import measure

STEP = 1.5          # ボクセル 1 個 = 正面図の何ピクセルか
ROUND_P = 2.4       # 断面の丸み（2 = 楕円、大きいほど角ばる）
TARGET_TRIS = 60000
HEIGHT_M = 1.65     # 書き出し時の身長(m)


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    if len(argv) < 2:
        sys.exit("usage: blender_make_3d.py <transparent.png> <out.glb> [preview_dir]")
    return [os.path.abspath(a) for a in argv[:3]] + [None] * (3 - len(argv[:3]))


# ---------------------------------------------------------------- 画像解析
class View:
    """1 体分のシルエットと、正面図座標への変換情報。"""

    def __init__(self, alpha, sl, ref_height=None):
        ys, xs = sl
        self.top, self.bottom = ys.start, ys.stop
        self.height = self.bottom - self.top
        self.mask = np.zeros_like(alpha)
        self.mask[ys, xs] = alpha[ys, xs]
        self.scale = (ref_height or self.height) / self.height  # 正面図px / このviewのpx
        # 足元寄り(身長の 70〜82%)の列の平均を体の中心とする
        r0 = self.top + int(self.height * 0.70)
        r1 = self.top + int(self.height * 0.82)
        cols = np.nonzero(self.mask[r0:r1])[1]
        self.center = cols.mean()

    def sample(self, y, h):
        """正面図座標 y(上から), 水平座標 h(このviewの右向きを+) → 前景か。"""
        row = np.round(self.top + y / self.scale).astype(int)
        col = np.round(self.center + h / self.scale).astype(int)
        ok = (row >= 0) & (row < self.mask.shape[0]) & (col >= 0) & (col < self.mask.shape[1])
        out = np.zeros(np.broadcast(row, col).shape, bool)
        rr, cc = np.broadcast_arrays(row, col)
        out[ok] = self.mask[rr[ok], cc[ok]]
        return out

    def to_pixel(self, y, h):
        return self.center + h / self.scale, self.top + y / self.scale


def run_coords(mask2d):
    """各行の前景ランの中での位置を -1..1 で返す（ランの中央が 0）。"""
    out = np.full(mask2d.shape, np.inf, np.float32)
    labels, n = ndimage.label(mask2d, structure=[[0, 0, 0], [1, 1, 1], [0, 0, 0]])
    if n == 0:
        return out
    idx = np.arange(1, n + 1)
    cols = np.broadcast_to(np.arange(mask2d.shape[1]), mask2d.shape)
    lo = ndimage.minimum(cols, labels, idx)
    hi = ndimage.maximum(cols, labels, idx)
    sel = labels > 0
    lab = labels[sel] - 1
    a, b = lo[lab], hi[lab] + 1.0
    c = cols[sel] + 0.5
    out[sel] = (2 * c - a - b) / np.maximum(b - a, 1.0)
    return out


def build_volume(front, side):
    """正面(幅 x) × 側面(奥行き z) の丸めたビジュアルハル。side は +x 側から見た図。"""
    H = front.height
    ys = np.arange(-2, H + 2, STEP)
    x_half = (np.ptp(front.mask.any(0).nonzero()[0]) / 2 + 10)
    z_half = (np.ptp(side.mask.any(0).nonzero()[0]) * side.scale + 10)
    xs = np.arange(-x_half, x_half, STEP)
    zs = np.arange(-z_half, z_half, STEP)

    fsil = front.sample(ys[:, None], xs[None, :])          # (Y, X)
    # +x 側から見た図は画面左 = 正面(+z) なので h = -z
    ssil = side.sample(ys[:, None], -zs[None, :])          # (Y, Z)
    fsil = ndimage.binary_closing(fsil, iterations=1)
    ssil = ndimage.binary_closing(ssil, iterations=1)
    nx = np.abs(run_coords(fsil)) ** ROUND_P               # (Y, X)
    nz = np.abs(run_coords(ssil)) ** ROUND_P               # (Y, Z)
    vol = (nx[:, :, None] + nz[:, None, :]) <= 1.0         # (Y, X, Z)
    vol = ndimage.binary_opening(vol, iterations=1)
    return vol, ys, xs, zs


# ---------------------------------------------------------------- Blender
def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_mesh(vol, ys, xs, zs, unit):
    pad = np.pad(vol, 1).astype(np.float32)
    pad = ndimage.gaussian_filter(pad, 1.3)
    verts, faces, _, _ = measure.marching_cubes(pad, 0.5)
    verts -= 1
    y = ys[0] + verts[:, 0] * STEP
    x = xs[0] + verts[:, 1] * STEP
    z = zs[0] + verts[:, 2] * STEP
    # 正面図座標(px) → Blender 座標(m): X=右, Y=-奥行き(正面が -Y), Z=上
    H = ys[-1]
    co = np.stack([x * unit, -z * unit, (H - y) * unit], 1)
    mesh = bpy.data.meshes.new("kenji")
    mesh.from_pydata(co.tolist(), [], faces[:, ::-1].tolist())
    mesh.validate()
    obj = bpy.data.objects.new("MiyazawaKenji", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    sm = obj.modifiers.new("smooth", "CORRECTIVE_SMOOTH")
    sm.iterations = 20
    sm.smooth_type = "LENGTH_WEIGHTED"
    sm.use_only_smooth = True
    bpy.ops.object.modifier_apply(modifier=sm.name)
    tris = sum(len(p.vertices) - 2 for p in mesh.polygons)
    if tris > TARGET_TRIS:
        dec = obj.modifiers.new("decimate", "DECIMATE")
        dec.ratio = TARGET_TRIS / tris
        bpy.ops.object.modifier_apply(modifier=dec.name)
    for p in mesh.polygons:
        p.use_smooth = True
    return obj, H


def assign_uvs(obj, views, unit, H, img_w, img_h):
    front, left, right, back = views
    mesh = obj.data
    uv = mesh.uv_layers.new(name="UVMap")
    n = len(mesh.polygons)
    normals = np.empty(n * 3, np.float32)
    mesh.polygons.foreach_get("normal", normals)
    normals = normals.reshape(n, 3)
    nx, nz_fwd = normals[:, 0], -normals[:, 1]   # nz_fwd: 正面方向(+)
    # 面ごとにどの図を投影するか: 0 正面, 1 +x側(左側面図), 2 -x側(右側面図), 3 背面
    # 正面・背面を少し優先して継ぎ目を体の横に寄せる
    choice = np.where(np.abs(nz_fwd) * 1.15 >= np.abs(nx),
                      np.where(nz_fwd >= 0, 0, 3),
                      np.where(nx >= 0, 1, 2))

    co = np.empty(len(mesh.vertices) * 3, np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3) / unit
    px_x, px_z, px_y = co[:, 0], -co[:, 1], H - co[:, 2]

    loop_v = np.empty(len(mesh.loops), np.int32)
    mesh.loops.foreach_get("vertex_index", loop_v)
    loop_poly = np.empty(len(mesh.loops), np.int32)
    starts = np.empty(n, np.int32)
    totals = np.empty(n, np.int32)
    mesh.polygons.foreach_get("loop_start", starts)
    mesh.polygons.foreach_get("loop_total", totals)
    loop_poly = np.repeat(np.arange(n), totals)
    c = choice[loop_poly]
    xv, yv, zv = px_x[loop_v], px_y[loop_v], px_z[loop_v]

    col = np.empty(len(loop_v), np.float32)
    row = np.empty(len(loop_v), np.float32)
    for k, (view, h) in enumerate([(front, xv), (left, -zv), (right, zv), (back, -xv)]):
        m = c == k
        col[m], row[m] = view.to_pixel(yv[m], h[m])
    uvs = np.stack([col / img_w, 1.0 - row / img_h], 1).astype(np.float32)
    uv.data.foreach_set("uv", uvs.ravel())


def make_texture(rgba_path, out_png):
    """透明部分に周囲の色をにじませた不透明テクスチャを作る（継ぎ目の白フチ防止）。"""
    im = np.asarray(Image.open(rgba_path).convert("RGBA"))
    fg = im[..., 3] > 0
    fg = ndimage.binary_erosion(fg, iterations=1)
    _, (ri, ci) = ndimage.distance_transform_edt(~fg, return_indices=True)
    rgb = im[..., :3][ri, ci]
    Image.fromarray(rgb).save(out_png)
    return im.shape[1], im.shape[0]


def make_material(obj, tex_path):
    mat = bpy.data.materials.new("KenjiMaterial")
    mat.use_nodes = True
    nt = mat.node_tree
    # 絵に陰影が描き込まれているので、ライトの影響を受けない unlit にする
    # (Background シェーダー → glTF の KHR_materials_unlit として書き出される)
    out = nt.nodes["Material Output"]
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    bg = nt.nodes.new("ShaderNodeBackground")
    tex = nt.nodes.new("ShaderNodeTexImage")
    img = bpy.data.images.load(tex_path)
    img.pack()
    tex.image = img
    nt.links.new(tex.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    obj.data.materials.append(mat)


def render_previews(obj, out_dir):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"   # GPU 不要で描画できる
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    world = bpy.data.worlds.new("world")
    world.color = (1, 1, 1)
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 2.0
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    scene.collection.objects.link(sun)
    scene.render.resolution_x, scene.render.resolution_y = 480, 640
    scene.render.film_transparent = True
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = HEIGHT_M * 1.15
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    for name, ang in [("front", 0), ("quarter", 40), ("side", 90), ("back", 180), ("rear_quarter", 225)]:
        a = math.radians(ang)
        cam.location = (5 * math.sin(a), -5 * math.cos(a), HEIGHT_M / 2)
        cam.rotation_euler = (math.radians(90), 0, a)
        scene.render.filepath = os.path.join(out_dir, f"preview_{name}.png")
        bpy.ops.render.render(write_still=True)


def main():
    src, out_glb, preview_dir = parse_args()
    rgba = np.asarray(Image.open(src).convert("RGBA"))
    alpha = rgba[..., 3] > 0
    labels, _ = ndimage.label(alpha)
    slices = sorted(ndimage.find_objects(labels), key=lambda s: s[1].start)
    slices = sorted(slices, key=lambda s: -(s[0].stop - s[0].start) * (s[1].stop - s[1].start))[:4]
    slices = sorted(slices, key=lambda s: s[1].start)
    ref = slices[0][0].stop - slices[0][0].start
    views = [View(alpha, s, ref) for s in slices]   # 正面, 左側面, 右側面, 背面

    vol, ys, xs, zs = build_volume(views[0], views[1])
    unit = HEIGHT_M / views[0].height

    clear_scene()
    obj, H = make_mesh(vol, ys, xs, zs, unit)
    tex_path = os.path.splitext(out_glb)[0] + "_texture.png"
    w, h = make_texture(src, tex_path)
    assign_uvs(obj, views, unit, H, w, h)
    make_material(obj, tex_path)
    # 足元を原点に
    zmin = min(v.co.z for v in obj.data.vertices)
    for v in obj.data.vertices:
        v.co.z -= zmin

    bpy.ops.export_scene.gltf(filepath=out_glb, export_format="GLB",
                              use_selection=False, export_apply=True)
    print("tris:", sum(len(p.vertices) - 2 for p in obj.data.polygons))
    if preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
        render_previews(obj, preview_dir)
    print("done:", out_glb)


if __name__ == "__main__":
    main()
