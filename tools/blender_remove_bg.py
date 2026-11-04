"""Blender (bpy) で三面図画像の背景を透過する。

使い方:
    blender -b -P tools/blender_remove_bg.py -- <入力画像> <出力ディレクトリ>
    # または bpy モジュール (pip install bpy) で
    python3 tools/blender_remove_bg.py <入力画像> <出力ディレクトリ>

処理:
  1. Blender で画像を読み込み、ピクセルを取得
  2. 画像の縁から連結する白/薄グレーの背景領域を塗りつぶしで判定
     (キャラクター内部の白いハイライトは残る)
  3. タイトル・ラベル文字など小さな塊を除去し、人物だけを残す
  4. 輪郭をアンチエイリアスして RGBA PNG として Blender から保存
  5. 正面/左側面/右側面/背面 を個別にトリミングして保存
"""
import os
import sys

import bpy
import numpy as np
from scipy import ndimage


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    if len(argv) < 2:
        sys.exit("usage: blender_remove_bg.py <input> <output_dir>")
    return os.path.abspath(argv[0]), os.path.abspath(argv[1])


def load_pixels(path):
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    # Blender は左下原点なので上下反転して扱う
    px = px.reshape(h, w, 4)[::-1]
    bpy.data.images.remove(img)
    return px


def save_rgba(rgba, path):
    h, w = rgba.shape[:2]
    img = bpy.data.images.new(os.path.basename(path), w, h, alpha=True)
    img.alpha_mode = "STRAIGHT"
    img.pixels.foreach_set(np.ascontiguousarray(rgba[::-1]).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def build_alpha(rgb):
    # sRGB 値 (0-1) で判定
    mx, mn = rgb.max(2), rgb.min(2)
    bright = rgb.mean(2)
    bg_like = (bright > 0.80) & ((mx - mn) < 0.08)

    # 縁から連結している背景らしい画素だけを背景とする
    labels, _ = ndimage.label(bg_like)
    edge_ids = np.unique(np.concatenate(
        [labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    edge_ids = edge_ids[edge_ids > 0]
    bg = np.isin(labels, edge_ids)

    # 前景のうち大きな塊(人物)だけを残し、文字などを消す
    fg = ~bg
    flabels, n = ndimage.label(fg)
    sizes = ndimage.sum(fg, flabels, range(1, n + 1))
    keep = np.isin(flabels, 1 + np.where(sizes > 5000)[0])

    # 輪郭のアンチエイリアス: 境界1pxは背景色からの距離でアルファを決める
    alpha = keep.astype(np.float32)
    border = keep & ~ndimage.binary_erosion(keep)
    dist = (1.0 - bright) / 0.25
    alpha[border] = np.clip(dist[border], 0.35, 1.0)
    return alpha


def main():
    src, out_dir = parse_args()
    os.makedirs(out_dir, exist_ok=True)
    px = load_pixels(src)
    rgb = px[..., :3]
    alpha = build_alpha(rgb)
    rgba = np.dstack([rgb, alpha]).astype(np.float32)

    save_rgba(rgba, os.path.join(out_dir, "miyazawa_kenji_transparent.png"))

    # 人物ごとに切り出し
    labels, n = ndimage.label(alpha > 0)
    names = ["front", "left", "right", "back"]
    objs = sorted(ndimage.find_objects(labels), key=lambda s: s[1].start)
    for name, sl in zip(names, objs):
        ys, xs = sl
        pad = 8
        y0, y1 = max(ys.start - pad, 0), min(ys.stop + pad, rgba.shape[0])
        x0, x1 = max(xs.start - pad, 0), min(xs.stop + pad, rgba.shape[1])
        save_rgba(rgba[y0:y1, x0:x1],
                  os.path.join(out_dir, f"miyazawa_kenji_{name}.png"))
    print(f"done: {n} figures -> {out_dir}")


if __name__ == "__main__":
    main()
