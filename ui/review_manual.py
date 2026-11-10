"""The review tab for the manual editor's drafts: the same table / replace / export as for automatic jobs, but the data
lives in the draft (so every change here is also an undoable change in the editor)."""
import os
import time
import gradio as gr
from core import builder, editor, manual, quality
from core.manual import MISSING, Tx

PREFIX = "m|"


def choices():
    """[(label, "m|<file id>|<draft id>")] for every draft of every manual file."""
    out = []
    for m in manual.list_projects():
        for dr in manual.list_drafts(m["id"]):
            out.append((f"✍ {m['name']} · مسودة «{dr['name']}»", f"{PREFIX}{m['id']}|{dr['id']}"))
    return out


def parse(sel):
    if isinstance(sel, str) and sel.startswith(PREFIX):
        _, pid, did = sel.split("|", 2)
        return pid, did
    return None


def _load(pid, did):
    meta, units = manual.load(pid)
    return meta, units, manual.load_draft(pid, did)


def load(pid, did, only_flagged=False):
    meta, units, d = _load(pid, did)
    mu = [u for u in manual.merged_units(units, d) if not u.get("remove")]
    rows = []
    for u in mu:
        src = (d.get("src") or {}).get(u["id"]) or u.get("text", "")
        tr = u.get("tr", "") if d["tr"].get(u["id"]) else ""
        if not tr:
            note = "بدون ترجمة"
        else:
            note = "؛ ".join(quality.check(src, tr, "ar"))
        if only_flagged and not note:
            continue
        rows.append([u["id"], u["page"] + 1, src, tr, note])
    rows.sort(key=lambda r: r[1])
    msg = f"تم تحميل **{len(rows)}** فقرة من الملف «{meta['name']}»، مسودة «{d['name']}»." + (" (المشبوهة وغير المترجمة فقط)" if only_flagged else "")
    return rows, d.get("ctx", "") or "", msg, ""


def save(pid, did, rows, ctx):
    n = 0
    with manual._lock:
        meta, units, d = _load(pid, did)
        tx = Tx(d, "تعديل من المراجعة")
        for r in rows.values.tolist() if hasattr(rows, "values") else rows:
            new = (r[3] or "").strip()
            if new != d["tr"].get(r[0], ""):
                tx.set("tr", r[0], value=new if new else MISSING)
                n += 1
        if (ctx or "") != (d.get("ctx") or ""):
            tx.set("ctx", value=ctx or "")
        tx.commit()
        manual.save_draft(pid, d)
    return f"💾 حُفظ {n} تعديل في المسودة"


def _apply(pid, did, merged, label):
    """Writes back the translations that changed in `merged` (copies of the units)."""
    with manual._lock:
        meta, units, d = _load(pid, did)
        tx = Tx(d, label)
        for u in merged:
            if (u.get("tr") or "") != d["tr"].get(u["id"], "") and u.get("tr"):
                tx.set("tr", u["id"], value=u["tr"])
        tx.commit()
        manual.save_draft(pid, d)


def replace(pid, did, find, repl):
    meta, units, d = _load(pid, did)
    mu = [u for u in manual.merged_units(units, d) if u.get("tr")]
    n = editor.find_replace(mu, find, repl)
    _apply(pid, did, mu, "استبدال كلمة (المراجعة)")
    return n


def instruct(pid, did, instruction):
    meta, units, d = _load(pid, did)
    mu = [u for u in manual.merged_units(units, d) if u.get("tr")]
    patches = editor.run_instruction(mu, instruction, meta.get("src", "en"), "ar", d.get("ctx", "") or "", d.get("style", "") or "")
    _apply(pid, did, mu, "أمر ذكي (المراجعة)")
    return patches


def generate(pid, did, want_pdf, want_epub, want_txt):
    meta, units, d = _load(pid, did)
    eff = manual.effective_plan(d)
    mu = manual.merged_units(units, d)
    out = manual._dir(pid) / "review_out"
    out.mkdir(exist_ok=True)
    for f in out.glob("*"):
        try:
            f.unlink()
        except OSError:
            pass
    base = f"{os.path.splitext(meta['name'])[0]}_{d['name']}_ar".replace("/", "-")
    files, notes = [], []
    if want_pdf:
        info = builder.build_plan_pdf(manual.source_path(pid), eff, mu, "ar", str(out / (base + ".pdf")), d.get("font") or None, d["pstyle"], manual._dir(pid))
        files.append(str(out / (base + ".pdf")))
        notes.append(f"PDF: {info['pages']} صفحة")
    if want_epub or want_txt:
        pages = sorted({e["p"] for e in eff if e["k"] == "o"})
        flow = []
        for p in pages:
            for it in manual.page_items(units, d, p):
                if it["deleted"]:
                    continue
                flow.append({"id": it["uid"], "kind": "text", "page": p, "translate": True, "text": it["en"], "tr": it["ar"],
                             "heading": bool(next((u for u in units if u["id"] == it["uid"]), {}).get("heading"))})
        if want_epub and builder.build_epub(flow, "ar", os.path.splitext(meta["name"])[0], str(out / (base + ".epub"))):
            files.append(str(out / (base + ".epub")))
        if want_txt:
            builder.build_txt(flow, str(out / (base + ".txt")))
            files.append(str(out / (base + ".txt")))
    left = sum(1 for u in mu if not u.get("tr") and not u.get("remove"))
    if left:
        notes.append(f"تنبيه: {left} فقرة بدون ترجمة تظهر بلغتها الأصلية")
    return files, "✅ " + ("، ".join(notes) or "تم توليد الملفات")
