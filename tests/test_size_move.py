"""A paragraph whose size you raised keeps that size, and one you moved is not squeezed by what was under its old place."""
import sys, warnings, tempfile, os
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fitz
from pathlib import Path
from core import builder

tmp = Path(tempfile.mkdtemp())
doc = fitz.open(); p = doc.new_page(width=420, height=600)
p.insert_textbox(fitz.Rect(30, 40, 390, 80), "Alice walked slowly down the old road thinking about what her brother had said.", fontsize=10)
p.insert_textbox(fitz.Rect(30, 90, 390, 130), "Second paragraph that sits just below the first one on the page.", fontsize=10)
doc.save(tmp / "s.pdf")
AR = "مشت أليس ببطء على الطريق القديم وهي تفكر فيما قاله أخوها لها في الليلة الماضية وكيف تغير كل شيء."
def units(**kw):
    a = {"id": "a", "page": 0, "kind": "text", "translate": True, "text": "x", "bbox": [30, 40, 390, 62], "size": 10, "color": 0, "align": "left", "tr": AR * 3, **kw}
    b = {"id": "b", "page": 0, "kind": "text", "translate": True, "text": "y", "bbox": [30, 90, 390, 112], "size": 10, "color": 0, "align": "left", "tr": AR}
    return [a, b]
def sizes(us):
    out = tmp / "o.pdf"
    builder.build_plan_pdf(str(tmp / "s.pdf"), [{"k": "o", "p": 0, "tr_on": True}], us, "ar", str(out), None, {}, tmp)
    page = fitz.open(out)[0]
    return [round(s["size"], 1) for b in page.get_text("dict")["blocks"] if b["type"] == 0 for l in b["lines"] for s in l["spans"]]
base = sizes(units())
big = sizes(units(size_delta=8))
assert max(big) >= 17, (base, big)               # 10.4 + 8 = 18.4: the size you asked for is the size you get
moved = sizes(units(dy=60))
assert min(moved) >= 10, moved                    # moved down over the second paragraph's gap: still full size
print("SIZE/MOVE OK", base[:2], big[:2], moved[:2])
