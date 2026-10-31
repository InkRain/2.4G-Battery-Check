"""从 VGN VHUB 的 app.asar 中提取产品封面图（键盘/鼠标），保存到应用资源目录。"""
import json
import struct
import os

ASAR = r"C:\Program Files\VGN VHUB\resources\app.asar"
OUT_DIR = r"C:\Users\pc\WorkBuddy\2026-10-28-19-57-01\2.4G-Battery-Check\app\resources"

data = open(ASAR, "rb").read()
# asar: [uint32=4][uint32=header_size+8]... header json 在偏移 16 开始
# pickle: 4 个 uint32：4, header_obj_size(+padding), header_obj_size, header_size
h1, h2, h3, h4 = struct.unpack("<IIII", data[:16])
header_json = data[16:16 + h4].decode("utf-8", errors="ignore").rstrip("\x00")
# 容错：截到最后一个 '}'，去掉可能的填充乱码
header_json = header_json[:header_json.rfind("}") + 1]
hdr = json.loads(header_json)
base = 8 + h2  # 文件数据区起点


def walk(node, path=""):
    """遍历 asar 目录树，yield (path, offset, size)。"""
    if "files" in node:
        for name, child in node["files"].items():
            yield from walk(child, f"{path}/{name}" if path else name)
    else:
        yield path, node.get("offset"), node.get("size")


wanted = []
for path, off, size in walk(hdr):
    low = path.lower()
    if any(k in low for k in ("v108", "dragonfly", "f2-white", "mouse-f2")) and \
            low.endswith((".png", ".webp", ".jpg")):
        wanted.append((path, int(off), size))

print(f"candidates: {len(wanted)}")
for path, off, size in wanted:
    blob = data[base + off: base + off + size]
    fname = path.strip("/").replace("/", "_")
    out = os.path.join(OUT_DIR, "vhub_" + fname)
    with open(out, "wb") as f:
        f.write(blob)
    print(f"  {path}  {size}B -> {out}")
