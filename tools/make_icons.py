"""从 HUB 截图裁剪 V108/Dragonfly 产品图，去除深色背景生成透明 PNG 图标。"""
from PIL import Image

SRC = r"C:\Users\pc\.workbuddy\clipboard-images\clipboard-2026-10-28T14-02-23-359Z-5d3fc8d5.png"
OUT_KBD = r"C:\Users\pc\WorkBuddy\2026-10-28-19-57-01\2.4G-Battery-Check\app\resources\icon_v108.png"
OUT_MOUSE = r"C:\Users\pc\WorkBuddy\2026-10-28-19-57-01\2.4G-Battery-Check\app\resources\icon_dragonfly.png"

img = Image.open(SRC).convert("RGBA")
print("src size:", img.size)


def extract(box, out, pad=6):
    crop = img.crop(box)
    px = crop.load()
    w, h = crop.size
    # 深色背景 -> 透明；保留主体（浅色产品）
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            # 背景近黑或深灰渐变
            if lum < 62:
                px[x, y] = (r, g, b, 0)
            elif lum < 92:
                # 过渡带：按亮度渐变 alpha，软化边缘
                alpha = int((lum - 62) / 30 * 255)
                px[x, y] = (r, g, b, alpha)
    # 裁掉全透明边缘
    bbox = crop.getbbox()
    if bbox:
        l, t, rr, btm = bbox
        l = max(0, l - pad); t = max(0, t - pad)
        rr = min(w, rr + pad); btm = min(h, btm + pad)
        crop = crop.crop((l, t, rr, btm))
    crop.save(out)
    print("saved", out, crop.size)


def trim_bottom(path, bottom):
    im = Image.open(path)
    im.crop((0, 0, im.width, bottom)).save(path)
    print("trimmed", path, im.size)


# 原图 1252x380，按比例定位产品区域（宽裁剪 + alpha 自动去边）
extract((100, 40, 660, 290), OUT_KBD, pad=8)
extract((810, 60, 990, 300), OUT_MOUSE, pad=8)
# 裁掉底部混入的文字/卡片边
trim_bottom(OUT_KBD, 152)
trim_bottom(OUT_MOUSE, 176)
