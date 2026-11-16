"""Reading the project / draft from disk and small shared helpers (no screen code here)."""
import gradio as gr
from core import manual
from .consts import SLOTS


def need(pid):
    if not pid:
        raise gr.Error("افتح ملفاً أولاً من تبويب «الملف»", title="ما فيه ملف مفتوح")


def path_of(f):
    return f if isinstance(f, str) else getattr(f, "name", None)


def label(e):
    if e["k"] == "o":
        return f"صفحة أصلية {e['p'] + 1}"
    if e["k"] == "t":
        return "صفحة نصية (ترجمة ملصوقة)"
    return "مستوردة: " + e.get("label", "") if e["k"] == "e" else "صفحة فارغة"


def status(e):
    if e["k"] != "o":
        return "تبقى كما هي"
    return "مترجمة (داخل النطاق)" if e.get("tr_on") else "تبقى بالأصل (خارج النطاق)"


def cur_items(units, d, eff, pos):
    e = eff[pos] if eff and 0 <= pos < len(eff) else None
    if e and e["k"] == "o" and e.get("tr_on"):
        return e, manual.page_items(units, d, e["p"])
    return e, []


def load_all(pid, did):
    meta, units = manual.load(pid)
    return meta, units, manual.load_draft(pid, did)


def items_now(pid, did, cur, grp):
    meta, units, d = load_all(pid, did)
    eff = manual.effective_plan(d)
    e, items_all = cur_items(units, d, eff, int(cur or 0))
    g = int(grp or 0)
    return meta, units, d, eff, items_all, items_all[g * SLOTS:(g + 1) * SLOTS]


def orig_page(d, cur):
    eff = manual.effective_plan(d)
    e = eff[int(cur)] if eff and 0 <= int(cur) < len(eff) else None
    return e["p"] if e and e["k"] == "o" else None


def token(pid, did, pos, grp):
    """Says which page/group the Arabic boxes on screen were drawn for. It travels with the boxes (same answer), so a box can never be saved into another page."""
    return f"tok|{pid}|{did}|{int(pos)}|{int(grp)}"


def autosave(pid, did, cur, grp, ars):
    """Saves the Arabic boxes of the group of paragraphs they were DRAWN for. Returns how many changed.
    ars[0] may be that page's token (see token()): the boxes then go to the page in the token, whatever page the screen says now
    (page number and boxes arrive in two steps when flipping, so for a moment they disagree)."""
    ars = list(ars)
    if ars and isinstance(ars[0], str) and ars[0].startswith("tok|"):
        parts = ars.pop(0).split("|")
        if len(parts) != 5 or parts[1] != (pid or "") or parts[2] != (did or ""):
            return 0                                   # boxes of another file/draft: never write them here
        cur, grp = int(parts[3]), int(parts[4])
    with manual._lock:
        meta, units, d, eff, allit, items = items_now(pid, did, cur, grp)
        n = 0
        for i, it in enumerate(items):
            if i < len(ars) and ars[i] is not None and not it["deleted"]:
                new = (ars[i] or "").strip()
                if new != d["tr"].get(it["uid"], ""):
                    manual.set_text(d, it["uid"], new)
                    n += 1
        if n:
            manual.save_draft(pid, d)
    return n
