"""Coloured boxes (highlights, label boxes) that belong to the ORIGINAL page: list them, recolour, move, resize, remove."""
import time
import gradio as gr
from core import builder, manual
from ui.common import guard, safe
from .data import load_all, need, orig_page
from .h_pages import _show
from .reg import R


def _hex(c):
    return "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in c)


def _opage(pid, did, cur):
    meta, units, d = load_all(pid, did)
    p = orig_page(d, cur)
    if p is None:
        raise gr.Error("هذي صفحة مضافة أو فاضية، ما فيها صناديق من الملف الأصلي", title="لا توجد صناديق")
    return d, p


def _pick(pick):
    if pick in (None, ""):
        raise gr.Error("اضغط «أظهر الصناديق» ثم اختر رقم الصندوق", title="ما اخترت صندوق")
    return int(pick)


@safe
def show(pid, did, cur):
    guard()
    need(pid)
    d, p = _opage(pid, did, cur)
    import fitz
    src = manual.source_path(pid)
    out = str(manual._dir(pid) / f"boxes_{int(time.time() * 1000) % 100000}.png")
    for f in manual._dir(pid).glob("boxes_*.png"):
        try:
            f.unlink()
        except OSError:
            pass
    n = builder.render_boxes(src, p, out)
    doc = fitz.open(src)
    boxes = builder.page_boxes(doc[p])
    doc.close()
    edits = d["pstyle"].get(str(p), {}).get("boxes", {})
    ch = []
    for i, (r, f) in enumerate(boxes):
        mark = " ✎" if str(i) in edits else ""
        ch.append((f"صندوق {i + 1} · {_hex(f)} · {int(r.width)}×{int(r.height)}{mark}", str(i)))
    info = (f"في هذي الصفحة **{n}** صندوق ملوّن. الأرقام الزرقاء في الصورة هي أرقام الصناديق." if n
            else "ما لقيت صناديق ملوّنة مرسومة في هذي الصفحة. ممكن التحديد جزء من صورة، وهذا ما أقدر أعدّل عليه.")
    return R(bx_img=out if n else None, bx_pick=gr.update(choices=ch, value=ch[0][1] if ch else None), bx_info=info)


def _go(pid, did, cur, msg, **kw):
    out = _show(pid, did, int(cur or 0), msg)
    return out


@safe
def apply(pid, did, cur, pick, c_on, color, dx, dy, dw, dh):
    guard()
    need(pid)
    i = _pick(pick)
    with manual._lock:
        d, p = _opage(pid, did, cur)
        old = d["pstyle"].get(str(p), {}).get("boxes", {}).get(str(i), {})
        manual.set_box(d, p, i, c=color if c_on else None, dx=float(dx or 0), dy=float(dy or 0), dw=float(dw or 0), dh=float(dh or 0))
        manual.save_draft(pid, d)
    return _go(pid, did, cur, f"✅ عُدّل الصندوق {i + 1}. شوف المعاينة تحت. تقدر تتراجع.")


@safe
def remove(pid, did, cur, pick):
    guard()
    need(pid)
    i = _pick(pick)
    with manual._lock:
        d, p = _opage(pid, did, cur)
        manual.Tx(d, "حذف صندوق ملوّن").set("pstyle", str(p), "boxes", str(i), value={"del": True}).commit()
        manual.save_draft(pid, d)
    return _go(pid, did, cur, f"🗑 حُذف الصندوق {i + 1} من الصفحة. تقدر تتراجع.")


@safe
def restore(pid, did, cur, pick):
    guard()
    need(pid)
    i = _pick(pick)
    with manual._lock:
        d, p = _opage(pid, did, cur)
        manual.set_box(d, p, i)
        manual.save_draft(pid, d)
    return _go(pid, did, cur, f"↺ رجع الصندوق {i + 1} مثل الملف الأصلي.")
