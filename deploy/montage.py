# 本地工具：把下载的候选图拼成带标签的看板，便于批量视觉校验
# 用法: py -X utf8 montage.py <源目录> <输出png> [每行个数]
import os
import sys
from PIL import Image, ImageDraw

SRC = sys.argv[1]
OUT = sys.argv[2]
COLS = int(sys.argv[3]) if len(sys.argv) > 3 else 4
CELL_W, CELL_H = 260, 150
PAD = 8

files = sorted(f for f in os.listdir(SRC)
               if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".svg")))
rows = (len(files) + COLS - 1) // COLS
W = COLS * CELL_W + (COLS + 1) * PAD
H = rows * CELL_H + (rows + 1) * PAD
sheet = Image.new("RGB", (W, H), (240, 240, 240))
draw = ImageDraw.Draw(sheet)

for i, f in enumerate(files):
    r, c = divmod(i, COLS)
    x, y = PAD + c * (CELL_W + PAD), PAD + r * (CELL_H + PAD)
    try:
        im = Image.open(os.path.join(SRC, f))
        if im.mode == "P":
            im = im.convert("RGBA" if "transparency" in im.info else "RGB")
        elif im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        # 缩放到格子，白底衬透明图
        bg = Image.new("RGB", (CELL_W, CELL_H), (255, 255, 255))
        im.thumbnail((CELL_W - 16, CELL_H - 34))
        if im.mode == "RGBA":
            bg.paste(im, ((CELL_W - im.width) // 2, (CELL_H - 34 - im.height) // 2), im)
        else:
            bg.paste(im, ((CELL_W - im.width) // 2, (CELL_H - 34 - im.height) // 2))
        sheet.paste(bg, (x, y))
    except Exception as ex:
        draw.text((x + 5, y + 5), f"ERR {ex}", fill=(255, 0, 0))
    draw.text((x + 4, y + CELL_H - 28), f, fill=(0, 0, 0))

sheet.save(OUT)
print("saved", OUT, sheet.size, f"{len(files)} files")
