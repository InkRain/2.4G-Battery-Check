"""把产品图白底抠成透明 PNG（边角 flood fill，保留产品内部的白色）。

用法: python make_transparent_icons.py
输入: app/resources/icon_v108.png / icon_dragonfly.png
输出: 同名覆盖（透明 PNG，裁掉多余空白边）
"""
import os
import sys
from collections import deque

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "app", "resources")

THRESH = 242          # RGB 全部 >= 该值视为"接近白"
TOLERANCE = 18        # 与相邻背景色的容差


def remove_white_bg(im: Image.Image) -> Image.Image:
    im = im.convert("RGBA")
    a = np.array(im).astype(np.int16)
    h, w = a.shape[:2]
    near_white = (a[..., 0] >= THRESH) & (a[..., 1] >= THRESH) & (a[..., 2] >= THRESH)
    # 从四角扩散的 flood fill（只在近白像素间传播，保护产品内部白色）
    bg = np.zeros((h, w), bool)
    dq = deque()
    for x in range(w):
        for y in (0, h - 1):
            if near_white[y, x] and not bg[y, x]:
                bg[y, x] = True
                dq.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if near_white[y, x] and not bg[y, x]:
                bg[y, x] = True
                dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        for ny, nx in ((y-1, x), (y+1, x), (y, x-1), (y, x+1)):
            if 0 <= ny < h and 0 <= nx < w and not bg[ny, nx] and near_white[ny, nx]:
                bg[ny, nx] = True
                dq.append((ny, nx))
    # alpha: 背景置 0；产品边缘 2px 渐变（减少白晕）
    alpha = np.where(bg, 0, 255).astype(np.uint8)
    eroded = bg.copy()
    for _ in range(2):
        e = eroded.copy()
        e[1:, :] &= eroded[:-1, :]
        e[:-1, :] &= eroded[1:, :]
        e[:, 1:] &= eroded[:, :-1]
        e[:, :-1] &= eroded[:, 1:]
        eroded = e
    edge = (~bg) & (~eroded)          # 产品靠背景的 1~2px 边缘
    alpha[edge] = 120
    a[..., 3] = alpha
    out = Image.fromarray(a.astype(np.uint8), "RGBA")
    # 裁剪到非透明区域 + 少量 padding
    ys, xs = np.where(alpha > 0)
    if len(xs):
        pad = 8
        box = (max(0, xs.min() - pad), max(0, ys.min() - pad),
               min(w, xs.max() + pad), min(h, ys.max() + pad))
        out = out.crop(box)
    return out


def main():
    for fname in ("icon_v108.png", "icon_dragonfly.png"):
        path = os.path.join(RES, fname)
        im = Image.open(path)
        has_alpha = im.mode == "RGBA" and np.array(im)[..., 3].min() < 250
        print(f"{fname}: mode={im.mode} size={im.size} already_alpha={bool(has_alpha)}")
        if has_alpha:
            print("  skip (已透明)")
            continue
        out = remove_white_bg(im)
        out.save(path)
        print(f"  -> {out.size} transparent PNG saved")


if __name__ == "__main__":
    sys.exit(main())
