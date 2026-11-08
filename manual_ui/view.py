"""Everything the editing screen shows for one page, returned as {component name: value}."""
import gradio as gr
from core import builder, manual, priority
from ui.common import toast
from . import panel
from .consts import GARBLED_MSG, SLOTS
from .data import cur_items, label, status
from .reg import R


def file_choices():
    return manual.list_all()


def draft_choices(pid):
    return [(x["name"], x["id"]) for x in manual.list_drafts(pid)] if pid else []


def chap_choices(meta):
    return [(f"{c['title']} · صفحة {c['page'] + 1}", str(c["page"] + 1)) for c in (meta or {}).get("chapters", [])]


def orig_png(pid, eff, pos, items_all):
    e = eff[pos] if eff and 0 <= pos < len(eff) else None
    if not e or e["k"] == "b":
        return None
    out = str(manual._dir(pid) / "orig.png")
    try:
        if e["k"] == "o":
            builder.render_original(manual.source_path(pid), e["p"], [(n + 1, it["bbox"]) for n, it in enumerate(items_all) if not it["custom"]], out)
        else:
            builder.render_original(str(manual._dir(pid) / e["f"]), 0, [], out)
    except Exception:
        return None
    return out


def _say(msg):
    if msg:
        toast(msg, warn=msg.startswith("⚠"))


def empty(msg=""):
    u = gr.update
    out = R(pid="", did="", cur=0, grp=0, page=1, info="", note="افتح ملفاً من تبويب «الملف» أو ارفع ملفاً جديداً.", pager="", last="",
            curbar="<div class='curbar'>لا يوجد ملف مفتوح. ابدأ من تبويب «الملف».</div>", plan=[], pg_target=1,
            files_sel=u(choices=file_choices(), value=None), dsel=u(choices=[], value=None), chap=u(choices=[], value=None),
            ctx="", style="", font="", orig=None, ai_model=u(choices=priority.choices("translate")), ai_checker=u(choices=priority.choices("edit")))
    for i in range(SLOTS):
        out.update(R(**{f"s{i}_g": u(visible=False)}))
    _say(msg)
    return out


def view(pid, did, pos, grp, msg=""):
    if not pid:
        return empty(msg)
    meta, units = manual.load(pid)
    d = manual.load_draft(pid, did)
    eff = manual.effective_plan(d)
    pos = max(0, min(int(pos or 0), len(eff) - 1)) if eff else 0
    e, items_all = cur_items(units, d, eff, pos)
    ngrp = max(1, -(-len(items_all) // SLOTS))
    grp = max(0, min(int(grp or 0), ngrp - 1))
    items = items_all[grp * SLOTS:(grp + 1) * SLOTS]
    if d.get("page") != pos or d.get("grp") != grp:
        d["page"], d["grp"] = pos, grp
        manual.save_draft(pid, d)
    done, total = manual.stats(units, d)
    info = (f"**الصفحة {pos + 1} من {len(eff)}** · {label(e)} · المترجم في الملف {done} من {total} فقرة") if e else "لا توجد صفحات في الملف."
    note = ""
    if e and not items_all:
        note = ("هذي صفحة مستوردة أو فارغة، تبقى كما هي." if e["k"] != "o" else
                "هذي الصفحة خارج نطاق الترجمة: تبقى بالأصل أو تُحذف حسب اختيارك." if not e.get("tr_on") else
                "لا يوجد نص قابل للقراءة في هذه الصفحة (صورة أو فراغ).")
    pager = f"الفقرات {grp * SLOTS + 1}–{min((grp + 1) * SLOTS, len(items_all))} من {len(items_all)} · مجموعة {grp + 1} من {ngrp}" if ngrp > 1 else ""
    u = gr.update
    last = manual.last_label(d)
    out = R(pid=pid, did=did, cur=pos, grp=grp, page=pos + 1, info=info, note=note, pager=pager, pg_target=pos + 1,
            last=f"آخر تغيير: {last}" if last else "لا توجد تغييرات للتراجع عنها",
            curbar=f"<div class='curbar'><b>الملف:</b> {meta['name']} · <b>المسودة:</b> {d['name']} · <b>الصفحة:</b> {pos + 1} من {len(eff)}</div>",
            b_grp_prev=u(visible=ngrp > 1), b_grp_next=u(visible=ngrp > 1))
    for i in range(SLOTS):
        if i >= len(items):
            out.update(R(**{f"s{i}_g": u(visible=False)}))
            continue
        it, gi = items[i], grp * SLOTS + i + 1
        shown = "(فقرة أضفتها أنت، لا يوجد نص أصلي)" if it["custom"] else (GARBLED_MSG if it["garbled"] else it["en"])
        out.update(R(**{
            f"s{i}_g": u(visible=True), f"s{i}_head": f"<b>الفقرة {gi}</b> <span class='mini'>· حجم الخط الأصلي {it['def_size']}"
                                                  + (" · مقروءة من الصورة" if it["has_src"] else "") + (" · 🗑 ستُحذف من الملف النهائي" if it["deleted"] else "") + "</span>",
            f"s{i}_en": u(value=shown), f"s{i}_ar": u(value=it["ar"], interactive=not it["deleted"]),
            f"s{i}_del": u(value="↩ استعادة الفقرة" if it["deleted"] else ("🗑 حذف الفقرة المضافة" if it["custom"] else "🗑 حذف الفقرة"))}))
    out.update(panel.values(d, items_all, e, panel.PAGE, 1, "p_"))
    for i in range(len(items)):
        out.update(panel.values(d, items_all, e, panel.PARA, grp * SLOTS + i + 1, f"s{i}_"))
    r = d["range"]
    out.update(R(r_on=u(value=r["on"]), r_a=u(value=r["a"]), r_b=u(value=r["b"]), r_out=u(value=r["outside"]),
                 plan=[[i + 1, label(x), status(x)] for i, x in enumerate(eff)],
                 files_sel=u(choices=file_choices(), value="p:" + pid), dsel=u(choices=draft_choices(pid), value=did),
                 chap=u(choices=chap_choices(meta), value=None), ctx=d.get("ctx", ""), style=d.get("style", ""), font=u(value=d.get("font", "")),
                 orig=orig_png(pid, eff, pos, items_all),
                 ai_model=u(choices=priority.choices("translate")), ai_checker=u(choices=priority.choices("edit"))))
    _say(msg)
    return out
