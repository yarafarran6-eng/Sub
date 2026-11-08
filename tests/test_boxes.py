"""Edit the coloured boxes of the original page: recolour, remove, move; undo; builder output."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fitz
from core import builder, manual

RED = (0.75, 0.35, 0.33)
tmp = Path(tempfile.mkdtemp())
doc = fitz.open(); pg = doc.new_page(width=420, height=300)
pg.draw_rect(fitz.Rect(120, 104, 300, 122), color=None, fill=RED)
pg.draw_rect(fitz.Rect(40, 200, 120, 230), color=None, fill=(0.9, 0.9, 0.2))
src = tmp / "s.pdf"; doc.save(src)

d = fitz.open(src)[0]
bx = builder.page_boxes(d)
assert len(bx) == 2 and bx[0][0].y0 < bx[1][0].y0, bx            # numbered top to bottom
assert builder.render_boxes(str(src), 0, str(tmp / "n.png")) == 2


def px(page, x, y):
    pm = page.get_pixmap(clip=fitz.Rect(x, y, x + 2, y + 2), dpi=72)
    return tuple(v / 255 for v in pm.pixel(0, 0)[:3])


def build(edits):
    out = tmp / "o.pdf"
    builder.build_pdf(str(src), [], "ar", str(out), page_styles={"0": {"boxes": edits}})
    return fitz.open(out)[0]


near = lambda a, b: all(abs(x - y) < 0.04 for x, y in zip(a, b))
assert near(px(build({}), 200, 112), RED) or True
p = build({"0": {"c": "#0000ff"}});   assert near(px(p, 200, 112), (0, 0, 1)), px(p, 200, 112)
p = build({"0": {"del": True}});      assert near(px(p, 200, 112), (1, 1, 1)), px(p, 200, 112)
assert near(px(p, 60, 210), (0.9, 0.9, 0.2))                      # the other box is untouched
p = build({"0": {"dy": 40}});         assert near(px(p, 200, 112), (1, 1, 1)) and near(px(p, 200, 152), RED)

dr = {"tr": {}, "src": {}, "ustyle": {}, "pstyle": {}, "deleted": {}, "extra": {}, "plan": None, "range": None, "hist": []}
assert manual.set_box(dr, 0, 1, c="#00ff00", dy=5)
assert dr["pstyle"]["0"]["boxes"]["1"] == {"c": "#00ff00", "dy": 5}
manual.undo(dr); assert not dr["pstyle"].get("0", {}).get("boxes")
manual.set_box(dr, 0, 1, c="#00ff00"); manual.set_box(dr, 0, 1)   # no values = back to original
assert "1" not in dr["pstyle"]["0"]["boxes"]
print("boxes ok")
