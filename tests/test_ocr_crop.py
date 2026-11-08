"""The picture sent for reading must not contain the neighbouring paragraph."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fitz
from core import builder

doc = fitz.open(); p = doc.new_page(width=300, height=200)
p.insert_text((20, 50), "UPPER LINE", fontsize=12)
p.insert_text((20, 64), "lower line", fontsize=12)          # tight: the crop of one reaches into the other
f = Path(tempfile.mkdtemp()) / "s.pdf"; doc.save(f)
up = list(p.search_for("UPPER LINE")[0]); lo = list(p.search_for("lower line")[0])
def dark(png, rect):
    pm = fitz.Pixmap(png); n = 0
    for y in range(pm.height):
        for x in range(pm.width):
            if sum(pm.pixel(x, y)[:3]) < 300: n += 1
    return n
plain = builder.crop_png(str(f), 0, up, dpi=100, margin=6)
masked = builder.crop_png(str(f), 0, up, dpi=100, margin=6, mask=[lo])
assert dark(masked, None) < dark(plain, None), "neighbour text still in the crop"
print("ok")
