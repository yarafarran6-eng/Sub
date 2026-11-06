"""Preview of one page and the final PDF."""
import os, time
import gradio as gr
from core import builder, manual
from ui.common import guard, safe
from .data import autosave, label, load_all, need
from .reg import R


def preview_png(pid, did, pos):
    """The page at this position of the OUTPUT file, drawn exactly as the final file will have it. -> (png path, position, text)."""
    meta, units, d = load_all(pid, did)
    eff = manual.effective_plan(d)
    if not eff:
        raise gr.Error("لا توجد صفحات", title="الملف فاضي")
    pos = max(0, min(int(pos), len(eff) - 1))
    out = str(manual._dir(pid) / f"preview_{int(time.time() * 1000) % 100000}.png")   # new name each time so the browser never shows an old picture
    for f in manual._dir(pid).glob("preview_*.png"):
        try:
            f.unlink()
        except OSError:
            pass
    t0 = time.time()
    builder.build_plan_pdf(manual.source_path(pid), eff, manual.merged_units(units, d), "ar", None, d.get("font") or None,
                           d["pstyle"], manual._dir(pid), only_pos=pos, png=out, dpi=100)
    return out, pos, f"معاينة الصفحة {pos + 1} من {len(eff)} ({label(eff[pos])}) · {time.time() - t0:.1f} ثانية"


@safe
def default_font(pid, did, font):
    if not pid:
        return R(saved="")
    with manual._lock:
        d = manual.load_draft(pid, did)
        d["font"] = font or ""
        manual.save_draft(pid, d)
    return R(saved="💾 حُفظ الخط الافتراضي.")


@safe
def preview(pid, did, cur, grp, pv, how, *ars):
    guard()
    need(pid)
    autosave(pid, did, cur, grp, ars)
    base = int(cur) if pv is None or int(pv) < 0 or how == "cur" else int(pv)
    png, pos, text = preview_png(pid, did, base + {"prev": -1, "next": 1}.get(how, 0))
    return R(pv_img=png, pv=pos, pv_info=text)


@safe
def build(pid, did, cur, grp, *ars):
    guard()
    need(pid)
    autosave(pid, did, cur, grp, ars)
    meta, units, d = load_all(pid, did)
    eff = manual.effective_plan(d)
    mu = manual.merged_units(units, d)
    if not any(u.get("tr") or u.get("remove") for u in mu) and eff == manual.effective_plan(manual.new_draft_dict("x", meta["pages"])):
        raise gr.Error("ما غيّرت أي شي بعد. ترجم فقرة واحدة على الأقل أو غيّر الصفحات.", title="ما فيه تغيير")
    out = manual._dir(pid) / "out"
    out.mkdir(exist_ok=True)
    dst = str(out / f"{os.path.splitext(meta['name'])[0]}_{d['name']}_ar.pdf".replace("/", "-"))
    t0 = time.time()
    info = builder.build_plan_pdf(manual.source_path(pid), eff, mu, "ar", dst, d.get("font") or None, d["pstyle"], manual._dir(pid))
    on_pages = {e["p"] for e in eff if e["k"] == "o" and e.get("tr_on")}
    left = sum(1 for u in units if u.get("translate") and u["page"] in on_pages and not d["tr"].get(u["id"]) and not d["deleted"].get(u["id"]))
    gr.Info(f"✅ بُني الملف ({info['pages']} صفحة) خلال {time.time() - t0:.0f} ثانية.")
    if left:
        gr.Warning(f"بقيت {left} فقرة داخل نطاق الترجمة بالإنجليزي لأنك ما ترجمتها.")
    return R(out=dst)
