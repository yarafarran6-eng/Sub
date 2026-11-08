"""A line inside a coloured label box: erasing it must keep the box coloured, and the translation must stay on ONE line."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fitz
from core import builder

RED = (0.75, 0.35, 0.33)


def make(tmp):
    doc = fitz.open()
    p = doc.new_page(width=420, height=300)
    p.draw_rect(fitz.Rect(120, 104, 300, 122), color=None, fill=RED)      # the label box is SMALLER than the text's own box
    p.insert_text((150, 117), "Inside the capital Byron", fontsize=10)
    f = tmp / "src.pdf"
    doc.save(f)
    return f, fitz.Rect(p.search_for("Inside the capital Byron")[0])


def lines_of(page, rect):
    words = [w for w in page.get_text("words", clip=rect)]
    return sorted({round(w[1] / 4) for w in words})


def run(dy):
    tmp = Path(tempfile.mkdtemp())
    src, r = make(tmp)
    u = {"page": 0, "kind": "text", "translate": True, "tr": "داخل العاصمة بيرون الكبرى", "bbox": list(r),
         "size": 11, "color": 0, "align": "center", "dy": dy}
    out = tmp / "out.pdf"
    builder.build_pdf(str(src), [u], "ar", str(out))
    d = fitz.open(out)
    return d[0]


def test_box_keeps_its_colour_and_text_stays_one_line():
    for dy in (0, -6):
        page = run(dy)
        # sample a spot inside the box where the text is NOT (left end of the box)
        pm = page.get_pixmap(clip=fitz.Rect(124, 108, 140, 118), dpi=72)
        c = tuple(v / 255 for v in pm.pixel(5, 5)[:3])
        assert all(abs(a - b) < 0.03 for a, b in zip(c, RED)), (dy, c)
        # one line only: all words start at about the same height
        words = page.get_text("words", clip=fitz.Rect(0, 90, 420, 160))
        assert words and max(w[1] for w in words) - min(w[1] for w in words) < 6, (dy, [w[:5] for w in words])


if __name__ == "__main__":
    test_box_keeps_its_colour_and_text_stays_one_line()
    print("ok")
