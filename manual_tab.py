"""The manual translation tab: drafts, page plan, paragraphs, styles, AI help, preview, undo."""
import os, time
from pathlib import Path
import gradio as gr
from concurrent.futures import ThreadPoolExecutor
from core import builder, jobs, manual, manual_ai, textcheck
from core.pool import NoKeys

SLOTS = 12
HL_DEFAULT = "#fff2a8"
PASTE_JS = (Path(__file__).parent / "core" / "paste.js").read_text(encoding="utf-8")
_guard = lambda: None
GARBLED_MSG = ("⚠ نص هذه الفقرة غير مقروء (ترميز خط الملف الأصلي). اقرأه من «صورة الصفحة الأصلية» تحت، "
               "أو اضغط «👁 اقرأ من الصورة» ليقرأه الذكاء الاصطناعي (تُرسل صورة الفقرة للخدمة).")

BG_PRESETS = {
    "بدون تغيير (الخلفية الأصلية)": ("none", "#ffffff", "#cccccc", "vertical"),
    "أبيض": ("solid", "#ffffff", "#ffffff", "vertical"), "كريمي": ("solid", "#fdf6e3", "#fdf6e3", "vertical"),
    "ورقي قديم": ("solid", "#f4ecd8", "#f4ecd8", "vertical"), "أصفر فاتح": ("solid", "#fff9c4", "#fff9c4", "vertical"),
    "وردي فاتح": ("solid", "#fde2e4", "#fde2e4", "vertical"), "أخضر فاتح": ("solid", "#e3f6e8", "#e3f6e8", "vertical"),
    "أزرق فاتح": ("solid", "#e1effa", "#e1effa", "vertical"), "رمادي فاتح": ("solid", "#eeeeee", "#eeeeee", "vertical"),
    "رمادي داكن": ("solid", "#2b2b2b", "#2b2b2b", "vertical"), "أسود": ("solid", "#000000", "#000000", "vertical"),
    "كحلي": ("solid", "#14213d", "#14213d", "vertical"), "بني": ("solid", "#3e2f23", "#3e2f23", "vertical"),
    "تدرج: غروب": ("gradient", "#ffb88c", "#de6262", "vertical"), "تدرج: محيط": ("gradient", "#2193b0", "#6dd5ed", "vertical"),
    "تدرج: ليلي": ("gradient", "#0f2027", "#2c5364", "vertical"), "تدرج: نعناع": ("gradient", "#d4fc79", "#96e6a1", "vertical"),
    "تدرج: وردي هادئ": ("gradient", "#fbc2eb", "#a6c1ee", "diagonal"), "تدرج: ذهبي": ("gradient", "#f6d365", "#fda085", "diagonal"),
    "تدرج: رمادي": ("gradient", "#bdc3c7", "#2c3e50", "vertical"), "تدرج: كريمي دافئ": ("gradient", "#fdfbfb", "#ebedee", "diagonal"),
}


# ------------------------------------------------------------------ small helpers
ALIGN_CHOICES = [("افتراضي (مثل الأصل)", ""), ("يمين", "right"), ("وسط", "center"), ("يسار", "left"), ("ضبط الجانبين", "justify")]
_DELTA = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}


def _fonts():
    return [("افتراضي", "")] + builder.font_labels()


def _proj_choices():
    return [(f"{m['name']} · {m['pages']} صفحة · {m['drafts']} مسودة [{m['id']}]", m["id"]) for m in manual.list_projects()]


def _draft_choices(pid):
    return [(x["name"], x["id"]) for x in manual.list_drafts(pid)] if pid else []


def _chap_choices(meta):
    return [(f"{c['title']} · صفحة {c['page'] + 1}", str(c["page"] + 1)) for c in (meta or {}).get("chapters", [])]


def _job_choices():
    return [(f"{m['name']} [{m['id']}]", m["id"]) for m in jobs.list_jobs() if m.get("kind") == "pdf" and m.get("status") in ("ready", "partial")]


def _label(e):
    if e["k"] == "o":
        return f"صفحة أصلية {e['p'] + 1}"
    return "مستوردة: " + e.get("label", "") if e["k"] == "e" else "صفحة فارغة"


def _status(e):
    if e["k"] != "o":
        return "تبقى كما هي"
    return "مترجمة (داخل النطاق)" if e.get("tr_on") else "تبقى بالأصل (خارج النطاق)"


def _cur_items(units, d, eff, pos):
    e = eff[pos] if eff and 0 <= pos < len(eff) else None
    if e and e["k"] == "o" and e.get("tr_on"):
        return e, manual.page_items(units, d, e["p"])
    return e, []


def _need(pid):
    if not pid:
        raise gr.Error("افتح ملفاً أولاً")


def _pstyle_vals(d, e):
    ps = d["pstyle"].get(str(e["p"]), {}) if e and e["k"] == "o" else {}
    bg = ps.get("bg") or {}
    return [gr.update(value=ps.get("font", "")), gr.update(value=ps.get("scale", 100)), gr.update(value=bool(ps.get("tcolor"))),
            gr.update(value=ps.get("tcolor") or "#000000"), gr.update(value=bool(ps.get("hl"))), gr.update(value=ps.get("hl") or HL_DEFAULT),
            gr.update(value=bg.get("mode", "none")), gr.update(value=bg.get("c1", "#ffffff")), gr.update(value=bg.get("c2", "#cccccc")),
            gr.update(value=bg.get("dir", "vertical")), gr.update(value=ps.get("align", "")),
            gr.update(value=ps.get("dx", 0) or 0), gr.update(value=ps.get("dy", 0) or 0)]


NOSLOT = [gr.update(visible=False)] + [gr.update()] * 12


def _empty(msg=""):
    return (["", "", 0, 0, 1, msg, "", "افتح ملفاً أو ارفع ملفاً جديداً."] + NOSLOT * SLOTS + [gr.update()] * 13
            + [gr.update()] * 4 + [[], gr.update(choices=_proj_choices(), value=None), gr.update(choices=[], value=None),
                                   gr.update(choices=[], value=None), "", "", "", None, "", None, gr.update(visible=False), ""])


def _orig_png(pid, eff, pos, items_all):
    e = eff[pos] if eff and 0 <= pos < len(eff) else None
    if not e or e["k"] == "b":
        return None
    out = str(manual._dir(pid) / "orig.png")
    try:
        if e["k"] == "o":
            builder.render_original(manual.source_path(pid), e["p"],
                                    [(n + 1, it["bbox"]) for n, it in enumerate(items_all) if not it["custom"]], out)
        else:
            builder.render_original(str(manual._dir(pid) / e["f"]), 0, [], out)
    except Exception:
        return None
    return out


def _view(pid, did, pos, grp, msg=""):
    """Everything the screen shows, in the order of VIEW (see build())."""
    if not pid:
        return _empty(msg)
    meta, units = manual.load(pid)
    d = manual.load_draft(pid, did)
    eff = manual.effective_plan(d)
    pos = max(0, min(int(pos or 0), len(eff) - 1)) if eff else 0
    e, items_all = _cur_items(units, d, eff, pos)
    ngrp = max(1, -(-len(items_all) // SLOTS))
    grp = max(0, min(int(grp or 0), ngrp - 1))
    items = items_all[grp * SLOTS:(grp + 1) * SLOTS]
    if d.get("page") != pos or d.get("grp") != grp:
        d["page"], d["grp"] = pos, grp
        manual.save_draft(pid, d)
    done, total = manual.stats(units, d)
    info = (f"**الصفحة {pos + 1} من {len(eff)}** · {_label(e)} · المترجم في الملف {done} من {total} فقرة") if e else "لا توجد صفحات في الملف."
    note = ""
    if e and not items_all:
        note = ("هذي صفحة مستوردة أو فارغة، تبقى كما هي." if e["k"] != "o" else
                "هذي الصفحة خارج نطاق الترجمة: تبقى بالأصل أو تُحذف حسب اختيارك." if not e.get("tr_on") else
                "لا يوجد نص قابل للقراءة في هذه الصفحة (صورة أو فراغ).")
    pager = f"الفقرات {grp * SLOTS + 1}–{min((grp + 1) * SLOTS, len(items_all))} من {len(items_all)} · مجموعة {grp + 1} من {ngrp}" if ngrp > 1 else ""
    out = [pid, did, pos, grp, pos + 1, msg, info, note]
    for i in range(SLOTS):
        if i >= len(items):
            out += NOSLOT
            continue
        it, gi = items[i], grp * SLOTS + i + 1
        shown = "(فقرة أضفتها أنت، لا يوجد نص أصلي)" if it["custom"] else (GARBLED_MSG if it["garbled"] else it["en"])
        out += [gr.update(visible=True),
                gr.update(value=shown, label=f"النص الأصلي · فقرة {gi} · حجم الخط الأصلي {it['def_size']}"
                                             + (" · مقروء من الصورة" if it["has_src"] else "")),
                gr.update(value=it["ar"], interactive=not it["deleted"],
                          label=f"الترجمة العربية · فقرة {gi}" + (" · 🗑 ستُحذف من الملف" if it["deleted"] else "")),
                gr.update(value="↩ استعادة" if it["deleted"] else ("🗑 حذف الفقرة المضافة" if it["custom"] else "🗑 حذف الفقرة")),
                gr.update(value=it["font"] or ""), gr.update(value=it["size"] or 0), gr.update(value=bool(it["tcolor"])),
                gr.update(value=it["tcolor"] or it["def_color"]), gr.update(value=bool(it["hl"])), gr.update(value=it["hl"] or HL_DEFAULT),
                gr.update(value=it["dx"] or 0), gr.update(value=it["dy"] or 0), gr.update(value=it["align"] or "")]
    out += _pstyle_vals(d, e)
    r = d["range"]
    out += [gr.update(value=r["on"]), gr.update(value=r["a"]), gr.update(value=r["b"]), gr.update(value=r["outside"])]
    out += [[[i + 1, _label(x), _status(x)] for i, x in enumerate(eff)],
            gr.update(choices=_proj_choices(), value=pid), gr.update(choices=_draft_choices(pid), value=did),
            gr.update(choices=_chap_choices(meta), value=None), d.get("ctx", ""), d.get("style", ""), gr.update(value=d.get("font", "")),
            _orig_png(pid, eff, pos, items_all), pager, None, gr.update(visible=False), ""]
    return out


def _with_confirm(view, pending, question):
    view[-3], view[-2], view[-1] = pending, gr.update(visible=True), question
    return view


def _load_all(pid, did):
    meta, units = manual.load(pid)
    return meta, units, manual.load_draft(pid, did)


def _items_now(pid, did, cur, grp):
    meta, units, d = _load_all(pid, did)
    eff = manual.effective_plan(d)
    e, items_all = _cur_items(units, d, eff, int(cur or 0))
    return meta, units, d, eff, items_all, items_all[int(grp or 0) * SLOTS:(int(grp or 0) + 1) * SLOTS]


def _autosave(pid, did, cur, grp, ars):
    with manual._lock:
        meta, units, d, eff, allit, items = _items_now(pid, did, cur, grp)
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


def _orig_page(d, cur):
    eff = manual.effective_plan(d)
    e = eff[int(cur)] if eff and 0 <= int(cur) < len(eff) else None
    return e["p"] if e and e["k"] == "o" else None


def _path_of(f):
    return f if isinstance(f, str) else getattr(f, "name", None)


# ------------------------------------------------------------------ open / projects / drafts
def h_new(file, progress=gr.Progress()):
    _guard()
    if not file:
        raise gr.Error("ارفع ملف PDF أولاً")
    path = _path_of(file)
    if not path.lower().endswith(".pdf"):
        raise gr.Error("الترجمة اليدوية تدعم ملفات PDF فقط")
    pid = manual.create(path, lambda i, n: progress(i / max(n, 1), desc=f"يستخرج النص: صفحة {i} من {n}"))
    meta, units = manual.load(pid)
    did = manual.ensure_draft(pid)
    note = f"✅ استُخرج نص {meta['pages']} صفحة في {meta['extract_seconds']} ثانية. أُنشئت «مسودة 1» وتُحفظ تلقائياً."
    if meta["no_text_pages"]:
        note += f" {len(meta['no_text_pages'])} صفحة بدون نص قابل للقراءة."
    bad = textcheck.share([u["text"] for u in units if u.get("translate")])
    if bad > 0.15:
        note += (f" ⚠ {round(bad * 100)}% من فقرات الملف نصها غير مقروء (ترميز خط الملف). تقدر تقرأها من صورة الصفحة "
                 "الأصلية، أو بزر «👁 اقرأ من الصورة» (بالذكاء الاصطناعي).")
    return _view(pid, did, 0, 0, note)


def h_open(sel):
    _guard()
    if not sel:
        raise gr.Error("اختر مشروعاً من القائمة")
    did = manual.ensure_draft(sel)
    d = manual.load_draft(sel, did)
    return _view(sel, did, d.get("page", 0), d.get("grp", 0), "📂 فُتح المشروع من آخر مكان وقفت عنده.")


def h_from_job(job_id):
    _guard()
    if not job_id:
        raise gr.Error("اختر ملفاً من الترجمة الآلية")
    try:
        pid, n = manual.import_from_job(job_id)
    except ValueError as e:
        raise gr.Error(str(e))
    did = manual.ensure_draft(pid)
    return _view(pid, did, 0, 0, f"✅ فُتح الملف في المحرر اليدوي، واستُوردت {n} فقرة مترجمة آلياً. عدّل عليها كما تشاء.")


def h_dswitch(pid, new_did):
    _guard()
    _need(pid)
    if not new_did:
        raise gr.Error("اختر مسودة")
    manual.set_last_draft(pid, new_did)
    d = manual.load_draft(pid, new_did)
    return _view(pid, new_did, d.get("page", 0), d.get("grp", 0), f"📝 المسودة: {d['name']}")


def h_dnew(pid):
    _guard()
    _need(pid)
    did = manual.create_draft(pid)
    return _view(pid, did, 0, 0, "✅ مسودة جديدة فاضية. المسودة السابقة محفوظة.")


def h_dcopy(pid, did):
    _guard()
    _need(pid)
    new = manual.create_draft(pid, copy_from=did)
    d = manual.load_draft(pid, new)
    return _view(pid, new, d.get("page", 0), d.get("grp", 0), "✅ نسخت المسودة الحالية بكل ما فيها.")


def h_drename(pid, did, name):
    _guard()
    _need(pid)
    if not (name or "").strip():
        raise gr.Error("اكتب الاسم الجديد")
    manual.rename_draft(pid, did, name)
    d = manual.load_draft(pid, did)
    return _view(pid, did, d.get("page", 0), d.get("grp", 0), "✏ تم تغيير الاسم.")


def _req_view(pid, did, cur, grp, pending, question):
    return _with_confirm(_view(pid, did, cur, grp), pending, question)


def h_req_del_draft(pid, did, cur, grp):
    _guard()
    _need(pid)
    return _req_view(pid, did, cur, grp, {"kind": "del_draft", "did": did}, "هل تريد حذف هذي المسودة نهائياً؟ هذا الحذف ما يمكن التراجع عنه.")


def h_req_del_project(pid, did, cur, grp, sel):
    _guard()
    if not sel:
        raise gr.Error("اختر مشروعاً من القائمة")
    return _req_view(pid, did, cur, grp, {"kind": "del_project", "pid": sel}, "هل تريد حذف المشروع كله بكل مسوداته نهائياً؟ هذا الحذف ما يمكن التراجع عنه.")


def h_req_reset(pid, did, cur, grp):
    _guard()
    _need(pid)
    return _req_view(pid, did, cur, grp, {"kind": "reset_all"}, "هل تريد إعادة المسودة كلها إلى البداية (بدون ترجمات ولا تنسيقات ولا تغييرات صفحات)؟ تقدر تتراجع بزر «تراجع».")


def h_req_del_page(pid, did, cur, grp):
    _guard()
    _need(pid)
    d = manual.load_draft(pid, did)
    eff = manual.effective_plan(d)
    if not eff:
        raise gr.Error("لا توجد صفحات")
    return _req_view(pid, did, cur, grp, {"kind": "del_page", "pos": int(cur)}, f"هل تريد حذف الصفحة {int(cur) + 1} ({_label(eff[int(cur)])}) من الملف النهائي؟")


def h_yes(pid, did, cur, grp, pending):
    _guard()
    if not pending:
        return _view(pid, did, cur, grp)
    k = pending["kind"]
    if k == "del_project":
        manual.delete(pending["pid"])
        return _view(None, "", 0, 0, "🗑 حُذف المشروع.") if pending["pid"] == pid else _view(pid, did, cur, grp, "🗑 حُذف المشروع.")
    with manual._lock:
        d = manual.load_draft(pid, did)
        msg = ""
        if k == "del_page":
            manual.plan_delete(d, pending["pos"])
            cur, msg = min(pending["pos"], max(len(manual.effective_plan(d)) - 1, 0)), "🗑 حُذفت الصفحة. تقدر تتراجع."
        elif k == "replace":
            manual.plan_insert(d, pending["pos"], pending["entry"], replace=True)
            msg = "🔁 استُبدلت الصفحة بالصفحة المستوردة. تقدر تتراجع."
        elif k == "reset_all":
            manual.reset_all(d)
            cur, grp, msg = 0, 0, "⟲ رجعت المسودة إلى البداية. تقدر تتراجع."
        elif k == "del_draft":
            manual.save_draft(pid, d)
            new = manual.delete_draft(pid, pending["did"])
            if not new:
                new = manual.create_draft(pid)
            d = manual.load_draft(pid, new)
            return _view(pid, new, d.get("page", 0), d.get("grp", 0), "🗑 حُذفت المسودة.")
        manual.save_draft(pid, d)
    return _view(pid, did, cur, grp, msg)


def h_no(pid, did, cur, grp):
    return _view(pid, did, cur, grp, "تم الإلغاء.")


def h_undo(pid, did, cur, grp):
    _guard()
    _need(pid)
    with manual._lock:
        d = manual.load_draft(pid, did)
        label = manual.undo(d)
        manual.save_draft(pid, d)
    return _view(pid, did, cur, grp, f"↩ تراجعت عن: {label}" if label else "ما فيه شي أتراجع عنه.")


# ------------------------------------------------------------------ navigation
def h_nav(pid, did, cur, grp, target, how, *ars):
    _guard()
    _need(pid)
    _autosave(pid, did, cur, grp, ars)
    meta, units, d = _load_all(pid, did)
    eff = manual.effective_plan(d)
    if how == "next":
        pos = int(cur) + 1
    elif how == "prev":
        pos = int(cur) - 1
    elif how == "todo":
        pos = next((p for p in range(int(cur) + 1, len(eff)) if any(not d["tr"].get(i["uid"]) and not i["deleted"] and not i["custom"]
                                                                  for i in _cur_items(units, d, eff, p)[1])), int(cur))
    elif how == "chap":
        pg = int(target) - 1
        pos = next((i for i, e in enumerate(eff) if e["k"] == "o" and e["p"] >= pg), int(cur))
    else:
        pos = int(target or 1) - 1
    return _view(pid, did, pos, 0)


def h_grp(pid, did, cur, grp, step, *ars):
    _guard()
    _need(pid)
    _autosave(pid, did, cur, grp, ars)
    return _view(pid, did, cur, int(grp) + step)


def h_save_page(pid, did, cur, grp, *ars):
    _guard()
    _need(pid)
    n = _autosave(pid, did, cur, grp, ars)
    return f"💾 حُفظت الصفحة ({n} تعديل)."


# ------------------------------------------------------------------ paragraph text / AI / numbers
def h_blur(pid, did, cur, grp, text, i):
    if not pid:
        return ""
    n = _autosave(pid, did, cur, grp, [None] * i + [text])
    return f"💾 حُفظ تلقائياً {time.strftime('%H:%M:%S')}" if n else ""


def h_num(pid, did, cur, grp, text, i):
    _guard()
    _need(pid)
    new = manual_ai.number_lines(text)
    _autosave(pid, did, cur, grp, [None] * i + [new])
    return gr.update(value=new), "🔢 رُقّمت الأسطر."


def _ai(pid, did, items):
    meta, units, d = _load_all(pid, did)
    try:
        return manual_ai.translate_units([{"uid": i["uid"], "text": i["en"]} for i in items], d.get("ctx", ""), d.get("style", ""))
    except NoKeys as e:
        raise gr.Error(str(e))


def _ocr_items(pid, did, items):
    """Reads the text of the given paragraphs from their pictures (4 at a time) and stores it in the draft."""
    meta, units, d = _load_all(pid, did)
    by = {u["id"]: u for u in units}
    src = manual.source_path(pid)

    def one(it):
        u = by[it["uid"]]
        return it["uid"], manual_ai.read_image(builder.crop_png(src, u["page"], u["bbox"]))

    try:
        with ThreadPoolExecutor(4) as ex:
            results = list(ex.map(one, [i for i in items if i["uid"] in by]))
    except NoKeys as e:
        raise gr.Error(str(e))
    except Exception as e:
        raise gr.Error(f"تعذرت القراءة من الصورة: {e}")
    with manual._lock:
        d = manual.load_draft(pid, did)
        for uid, txt in results:
            manual.set_src(d, uid, txt)
        manual.save_draft(pid, d)
    return len(results)


def h_ocr_slot(pid, did, cur, grp, i):
    _guard()
    _need(pid)
    meta, units, d, eff, allit, items = _items_now(pid, did, cur, grp)
    if i >= len(items) or items[i]["custom"]:
        raise gr.Error("هذي الفقرة ما لها نص أصلي")
    _ocr_items(pid, did, [items[i]])
    meta, units, d, eff, allit, items = _items_now(pid, did, cur, grp)
    return gr.update(value=items[i]["en"], label=f"النص الأصلي · فقرة {grp * SLOTS + i + 1} · مقروء من الصورة"), "👁 قُرئ النص من الصورة. راجعه وتأكد منه."


def h_ocr_page(pid, did, cur, grp):
    _guard()
    _need(pid)
    meta, units, d, eff, allit, items = _items_now(pid, did, cur, grp)
    bad = [x for x in allit if x["garbled"] and not x["custom"] and not x["deleted"]]
    if not bad:
        return _view(pid, did, cur, grp, "ما فيه فقرات غير مقروءة في هذي الصفحة.")
    n = _ocr_items(pid, did, bad)
    return _view(pid, did, cur, grp, f"👁 قُرئت {n} فقرة من الصورة. راجع النصوص قبل الترجمة.")


def h_ai_slot(pid, did, cur, grp, i):
    _guard()
    _need(pid)
    meta, units, d, eff, allit, items = _items_now(pid, did, cur, grp)
    if i >= len(items):
        raise gr.Error("لا توجد فقرة")
    it = items[i]
    if it["custom"]:
        raise gr.Error("الفقرة المضافة ما لها نص أصلي تترجمه")
    if it["garbled"]:                      # unreadable text: read it from the picture first
        _ocr_items(pid, did, [it])
        meta, units, d, eff, allit, items = _items_now(pid, did, cur, grp)
        it = items[i]
    res = _ai(pid, did, [it])
    tr, flag = res.get(it["uid"], ("", ""))
    if not tr:
        raise gr.Error("ما رجعت ترجمة. جرّب مرة ثانية أو راجع المفاتيح.")
    with manual._lock:
        d = manual.load_draft(pid, did)
        manual.set_text(d, it["uid"], tr)
        manual.save_draft(pid, d)
    return gr.update(value=tr), "🤖 تمت ترجمة الفقرة" + (f" (ملاحظة: {flag})" if flag else "") + ". عدّل عليها بيدك لو تبي."


def h_ai_page(pid, did, cur, grp, keep_manual):
    _guard()
    _need(pid)
    meta, units, d, eff, allit, items = _items_now(pid, did, cur, grp)
    bad = [x for x in allit if x["garbled"] and not x["custom"] and not x["deleted"]]
    if bad:
        _ocr_items(pid, did, bad)
        meta, units, d, eff, allit, items = _items_now(pid, did, cur, grp)
    todo = [i for i in allit if not i["custom"] and not i["deleted"] and (not keep_manual or not i["ar"].strip())]
    if not todo:
        return _view(pid, did, cur, grp, "ما فيه فقرات تحتاج ترجمة في هذي الصفحة.")
    res = _ai(pid, did, todo)
    with manual._lock:
        d = manual.load_draft(pid, did)
        n = 0
        for it in todo:
            tr, flag = res.get(it["uid"], ("", ""))
            if tr:
                manual.set_text(d, it["uid"], tr)
                n += 1
        manual.save_draft(pid, d)
    return _view(pid, did, cur, grp, f"🤖 تُرجمت {n} فقرة بالذكاء الاصطناعي. راجعها وعدّل عليها بيدك.")


def h_ai_cfg(pid, did, ctx, style):
    if not pid:
        return ""
    with manual._lock:
        d = manual.load_draft(pid, did)
        d["ctx"], d["style"] = ctx or "", style or ""
        manual.save_draft(pid, d)
    return "💾 حُفظت تعليمات الذكاء."


def h_ai_ctx(pid, did):
    _guard()
    _need(pid)
    meta, units, d = _load_all(pid, did)
    texts = [u["text"] for u in units if u.get("translate")]
    try:
        ctx = manual_ai.build_context(texts, d.get("style", ""))
    except NoKeys as e:
        raise gr.Error(str(e))
    if not ctx:
        raise gr.Error("ما قدر البرنامج يبني المسرد. تأكد من المفاتيح.")
    h_ai_cfg(pid, did, ctx, d.get("style", ""))
    return gr.update(value=ctx), "✅ بُني المسرد من نص الملف. تقدر تعدله."


# ------------------------------------------------------------------ paragraph add / delete / style
def h_slot_del(pid, did, cur, grp, i):
    _guard()
    _need(pid)
    with manual._lock:
        meta, units, d, eff, allit, items = _items_now(pid, did, cur, grp)
        if i >= len(items):
            raise gr.Error("لا توجد فقرة")
        it = items[i]
        if it["custom"]:
            manual.delete_extra(d, it["uid"])
            msg = "🗑 حُذفت الفقرة المضافة. تقدر تتراجع."
        else:
            _, now = manual.toggle_deleted(d, it["uid"])
            msg = "🗑 ستُحذف الفقرة من الملف النهائي. تقدر تتراجع." if now else "↩ استُعيدت الفقرة."
        manual.save_draft(pid, d)
    return _view(pid, did, cur, grp, msg)


def h_add_para(pid, did, cur, grp, after_n):
    _guard()
    _need(pid)
    with manual._lock:
        meta, units, d, eff, allit, items = _items_now(pid, did, cur, grp)
        p = _orig_page(d, cur)
        if p is None:
            raise gr.Error("الإضافة ممكنة فقط في الصفحات الأصلية داخل نطاق الترجمة")
        n = int(after_n or 0)
        after = allit[n - 1]["uid"] if 1 <= n <= len(allit) else ""
        manual.new_extra(d, units, p, after)
        manual.save_draft(pid, d)
    return _view(pid, did, cur, grp, "➕ أُضيفت فقرة جديدة. اكتب نصها، وتقدر تحرّك مكانها من «تنسيق الفقرة».")


def h_slot_style(pid, did, cur, grp, i, font, size, tOn, tc, hOn, hc, dx, dy, align):
    if not pid:
        return ""
    with manual._lock:
        meta, units, d, eff, allit, items = _items_now(pid, did, cur, grp)
        if i >= len(items):
            return ""
        manual.set_ustyle(d, items[i]["uid"], font=font or None, size=float(size or 0), tcolor=tc if tOn else None,
                          hl=hc if hOn else None, dx=float(dx or 0), dy=float(dy or 0), align=align or None)
        manual.save_draft(pid, d)
    return f"🎨 حُفظ التنسيق {time.strftime('%H:%M:%S')}"


_KEYMAP = {"font": ["font"], "size": ["size"], "tcolor": ["tcolor"], "hl": ["hl"], "pos": ["dx", "dy"], "align": ["align"]}


def h_slot_reset(pid, did, cur, grp, i, which):
    _guard()
    _need(pid)
    with manual._lock:
        meta, units, d, eff, allit, items = _items_now(pid, did, cur, grp)
        it = items[i]
        manual.reset_ustyle(d, it["uid"], manual.STYLE_KEYS if which == "all" else _KEYMAP[which])
        manual.save_draft(pid, d)
    u = gr.update
    ch = lambda k: which in ("all", k)
    return [u(value="") if ch("font") else u(), u(value=0) if ch("size") else u(),
            u(value=False) if ch("tcolor") else u(), u(value=it["def_color"]) if ch("tcolor") else u(),
            u(value=False) if ch("hl") else u(), u(value=HL_DEFAULT) if ch("hl") else u(),
            u(value=0) if ch("pos") else u(), u(value=0) if ch("pos") else u(), u(value="") if ch("align") else u(), "↺ رجع للافتراضي."]


def h_slot_move(pid, did, cur, grp, i, dirn, step):
    """Arrow buttons: shift the paragraph by `step` points left / right / up / down."""
    _guard()
    _need(pid)
    st = float(step or 5)
    with manual._lock:
        meta, units, d, eff, allit, items = _items_now(pid, did, cur, grp)
        uid = items[i]["uid"]
        us = d["ustyle"].get(uid, {})
        dx = round(float(us.get("dx", 0) or 0) + _DELTA[dirn][0] * st, 2)
        dy = round(float(us.get("dy", 0) or 0) + _DELTA[dirn][1] * st, 2)
        manual.set_ustyle(d, uid, dx=dx, dy=dy)
        manual.save_draft(pid, d)
    return gr.update(value=dx), gr.update(value=dy), f"⬌ الإزاحة الآن: أفقي {dx} ورأسي {dy} نقطة."


# ------------------------------------------------------------------ page style / range / plan
def h_page_style(pid, did, cur, font, scale, tOn, tc, hOn, hc, bgm, bgc1, bgc2, bgdir, align, dx, dy):
    if not pid:
        return ""
    with manual._lock:
        d = manual.load_draft(pid, did)
        p = _orig_page(d, cur)
        if p is None:
            return ""
        bg = {"mode": bgm, "c1": bgc1, "c2": bgc2, "dir": bgdir} if bgm and bgm != "none" else None
        manual.set_pstyle(d, p, font=font or None, scale=(float(scale) if scale and float(scale) != 100 else None),
                          tcolor=tc if tOn else None, hl=hc if hOn else None, bg=bg,
                          align=align or None, dx=float(dx or 0), dy=float(dy or 0))
        manual.save_draft(pid, d)
    return f"🎨 حُفظ تنسيق الصفحة {time.strftime('%H:%M:%S')}"


def h_bg_preset(pid, did, cur, name):
    _guard()
    _need(pid)
    mode, c1, c2, dr = BG_PRESETS[name]
    with manual._lock:
        d = manual.load_draft(pid, did)
        p = _orig_page(d, cur)
        if p is None:
            raise gr.Error("الخلفية متاحة للصفحات الأصلية فقط")
        manual.set_pstyle(d, p, bg={"mode": mode, "c1": c1, "c2": c2, "dir": dr} if mode != "none" else None)
        manual.save_draft(pid, d)
    u = gr.update
    return [u(value=mode), u(value=c1), u(value=c2), u(value=dr), "🎨 طُبقت الخلفية."]


_PKEYS = {"font": ["font"], "scale": ["scale"], "tcolor": ["tcolor"], "hl": ["hl"], "bg": ["bg"], "align": ["align"], "pos": ["dx", "dy"]}


def h_page_reset(pid, did, cur, which):
    _guard()
    _need(pid)
    with manual._lock:
        d = manual.load_draft(pid, did)
        p = _orig_page(d, cur)
        if p is None:
            raise gr.Error("هذي ليست صفحة أصلية")
        tx = manual.Tx(d, "إعادة تعيين خيار الصفحة")
        for k in _PKEYS[which]:
            tx.set("pstyle", str(p), k, value=manual.MISSING)
        tx.commit()
        manual.save_draft(pid, d)
    u = gr.update
    ch = lambda k: which == k
    return [u(value="") if ch("font") else u(), u(value=100) if ch("scale") else u(), u(value=False) if ch("tcolor") else u(),
            u(value="#000000") if ch("tcolor") else u(), u(value=False) if ch("hl") else u(), u(value=HL_DEFAULT) if ch("hl") else u(),
            u(value="none") if ch("bg") else u(), u(value="#ffffff") if ch("bg") else u(), u(value="#cccccc") if ch("bg") else u(),
            u(value="vertical") if ch("bg") else u(), u(value="") if ch("align") else u(),
            u(value=0) if ch("pos") else u(), u(value=0) if ch("pos") else u(), "↺ رجع للافتراضي."]


def h_page_move(pid, did, cur, dirn, step):
    """Arrow buttons for the whole page: shift every paragraph of the page."""
    _guard()
    _need(pid)
    st = float(step or 5)
    with manual._lock:
        d = manual.load_draft(pid, did)
        p = _orig_page(d, cur)
        if p is None:
            raise gr.Error("التحريك متاح للصفحات الأصلية فقط")
        ps = d["pstyle"].get(str(p), {})
        dx = round(float(ps.get("dx", 0) or 0) + _DELTA[dirn][0] * st, 2)
        dy = round(float(ps.get("dy", 0) or 0) + _DELTA[dirn][1] * st, 2)
        manual.set_pstyle(d, p, dx=dx, dy=dy)
        manual.save_draft(pid, d)
    return gr.update(value=dx), gr.update(value=dy), f"⬌ إزاحة الصفحة كلها الآن: أفقي {dx} ورأسي {dy} نقطة."


def h_page_reset_all(pid, did, cur, grp):
    _guard()
    _need(pid)
    with manual._lock:
        meta, units, d = _load_all(pid, did)
        p = _orig_page(d, cur)
        if p is None:
            raise gr.Error("هذي ليست صفحة أصلية")
        manual.reset_page(d, p, units)
        manual.save_draft(pid, d)
    return _view(pid, did, cur, grp, "↺ رجعت الصفحة كلها (خطوط وأحجام وألوان وتحديد وخلفية ومواضع) إلى الافتراضي.")


def h_range(pid, did, cur, grp, on, a, b, outside):
    _guard()
    _need(pid)
    meta, units, d = _load_all(pid, did)
    a, b = int(a or 1), int(b or 1)
    if on and not (1 <= a <= b <= meta["pages"]):
        raise gr.Error(f"النطاق لازم يكون بين 1 و {meta['pages']} وبداية النطاق قبل نهايته")
    with manual._lock:
        d = manual.load_draft(pid, did)
        manual.set_range(d, on, a, b, outside)
        manual.save_draft(pid, d)
    return _view(pid, did, cur, grp, "✅ حُفظ نطاق الترجمة." if on else "✅ أُلغي النطاق: كل الصفحات تُترجم.")


def h_move(pid, did, cur, grp, to):
    _guard()
    _need(pid)
    with manual._lock:
        d = manual.load_draft(pid, did)
        to = int(to or 1) - 1
        if not manual.plan_move(d, int(cur), to):
            raise gr.Error("اكتب موضعاً مختلفاً داخل أرقام الصفحات")
        manual.save_draft(pid, d)
    return _view(pid, did, max(0, min(to, len(manual.effective_plan(d)) - 1)), 0, f"↕ نُقلت الصفحة إلى الموضع {to + 1}.")


def h_swap(pid, did, cur, grp, other):
    _guard()
    _need(pid)
    with manual._lock:
        d = manual.load_draft(pid, did)
        if not manual.plan_swap(d, int(cur), int(other or 1) - 1):
            raise gr.Error("اكتب رقم صفحة مختلفاً داخل الملف")
        manual.save_draft(pid, d)
    return _view(pid, did, int(cur), 0, f"⇄ بُدّلت الصفحة {int(cur) + 1} مع الصفحة {int(other)}.")


WHERE = ["بعد الصفحة الحالية", "قبل الصفحة الحالية", "استبدال الصفحة الحالية (تُحذف القديمة)"]


def h_insert(pid, did, cur, grp, file, fpage, where, blank):
    _guard()
    _need(pid)
    if not blank and not file:
        raise gr.Error("ارفع ملف PDF أو صورة، أو اختر «صفحة فارغة»")
    entry = {"k": "b"} if blank else None
    try:
        if entry is None:
            entry = manual.import_page(pid, _path_of(file), fpage)
    except Exception as e:
        raise gr.Error(str(e))
    if where.startswith("استبدال"):
        return _req_view(pid, did, cur, grp, {"kind": "replace", "pos": int(cur), "entry": entry},
                         f"استبدال الصفحة {int(cur) + 1} سيحذفها من الملف النهائي. هل أنت متأكد؟")
    with manual._lock:
        d = manual.load_draft(pid, did)
        manual.plan_insert(d, int(cur), entry, "before" if where.startswith("قبل") else "after")
        manual.save_draft(pid, d)
    pos = int(cur) if where.startswith("قبل") else int(cur) + 1
    return _view(pid, did, pos, 0, "➕ أُضيفت الصفحة. تقدر تتراجع.")


# ------------------------------------------------------------------ preview / final file
def h_font(pid, did, font):
    if not pid:
        return ""
    with manual._lock:
        d = manual.load_draft(pid, did)
        d["font"] = font or ""
        manual.save_draft(pid, d)
    return "💾 حُفظ الخط الافتراضي."


def h_preview(pid, did, cur, grp, pv, how, *ars):
    _guard()
    _need(pid)
    _autosave(pid, did, cur, grp, ars)
    meta, units, d = _load_all(pid, did)
    eff = manual.effective_plan(d)
    if not eff:
        raise gr.Error("لا توجد صفحات")
    base = int(cur) if pv is None or int(pv) < 0 or how == "cur" else int(pv)
    pos = max(0, min(base + {"prev": -1, "next": 1}.get(how, 0), len(eff) - 1))
    out = str(manual._dir(pid) / "preview.png")
    t0 = time.time()
    builder.build_plan_pdf(manual.source_path(pid), eff, manual.merged_units(units, d), "ar", None, d.get("font") or None,
                           d["pstyle"], manual._dir(pid), only_pos=pos, png=out, dpi=100)
    return out, pos, f"معاينة الصفحة {pos + 1} من {len(eff)} ({_label(eff[pos])}) · {time.time() - t0:.1f} ثانية", f"👁 معاينة الصفحة {pos + 1}"


def h_pv_edit(pid, did, cur, grp, pv):
    _guard()
    _need(pid)
    return _view(pid, did, int(pv) if pv is not None and int(pv) >= 0 else int(cur), 0, "✍ انتقلت لتحرير الصفحة المعروضة في المعاينة.")


def h_build(pid, did, cur, grp, *ars):
    _guard()
    _need(pid)
    _autosave(pid, did, cur, grp, ars)
    meta, units, d = _load_all(pid, did)
    eff = manual.effective_plan(d)
    mu = manual.merged_units(units, d)
    if not any(u.get("tr") or u.get("remove") for u in mu) and eff == manual.effective_plan(manual.new_draft_dict("x", meta["pages"])):
        raise gr.Error("ما غيّرت أي شي بعد")
    out = manual._dir(pid) / "out"
    out.mkdir(exist_ok=True)
    dst = str(out / f"{os.path.splitext(meta['name'])[0]}_{d['name']}_ar.pdf".replace("/", "-"))
    t0 = time.time()
    info = builder.build_plan_pdf(manual.source_path(pid), eff, mu, "ar", dst, d.get("font") or None, d["pstyle"], manual._dir(pid))
    on_pages = {e["p"] for e in eff if e["k"] == "o" and e.get("tr_on")}
    left = sum(1 for u in units if u.get("translate") and u["page"] in on_pages and not d["tr"].get(u["id"]) and not d["deleted"].get(u["id"]))
    return dst, (f"✅ بُني الملف ({info['pages']} صفحة) خلال {time.time() - t0:.0f} ثانية. "
                 + (f"بقيت {left} فقرة داخل نطاق الترجمة بالإنجليزي لأنك ما ترجمتها." if left else "كل الفقرات داخل النطاق مترجمة."))


# ------------------------------------------------------------------ the screen
def build(guard, opt, step):
    global _guard
    _guard = guard
    m_pid, m_did, m_cur, m_grp, m_pv, m_pending = gr.State(""), gr.State(""), gr.State(0), gr.State(0), gr.State(-1), gr.State(None)
    step("أ", "افتح ملفاً", "ما يحتاج أي مفتاح: يستخرج الموقع النص فقط وأنت تترجم بيدك. كل شي يُحفظ تلقائياً.")
    opt("رفع ملف PDF", "يستخرج النص من كل صفحة مرتباً بالفقرات.", "تترجم بيدك وتدرج الترجمة في الملف بنفس الموضع.",
        "ارفع الملف واضغط «استخراج النص». أي ملف جديد ينفتح على «مسودة 1» وتُحفظ تلقائياً.")
    m_file = gr.File(show_label=False, file_types=[".pdf"])
    b_new = gr.Button("استخراج النص وفتح الملف", variant="primary")
    opt("مشاريعي السابقة", "كل ملف بدأت فيه تقدر ترجع له وتكمل أو تعدل، ولا يُحذف إلا لو حذفته أنت وأكدت.",
        "ما تضيع شغلك لو سكرت الصفحة أو البرنامج.", "اختر مشروعاً ثم «فتح». ومن «حذف المشروع» يطلع لك سؤال تأكيد.")
    m_sel = gr.Dropdown(_proj_choices(), show_label=False, value=None, interactive=True)
    with gr.Row():
        b_open = gr.Button("فتح")
        b_delp = gr.Button("حذف المشروع")
    opt("فتح ملف ترجمته آلياً", "يفتح ملفاً تُرجم من تبويب «الترجمة» داخل المحرر اليدوي مع ترجمته.",
        "تراجع الترجمة الآلية وتعدل عليها بيدك وتنسق وتبدل الصفحات.", "اختر الملف واضغط الزر.")
    m_job = gr.Dropdown(_job_choices(), show_label=False, value=None, interactive=True)
    b_job = gr.Button("فتح في المحرر اليدوي")
    m_msg = gr.Markdown()
    with gr.Group(visible=False) as m_confirm:
        m_cq = gr.Markdown()
        with gr.Row():
            b_yes = gr.Button("نعم", variant="stop")
            b_no = gr.Button("لا")
    step("ب", "المسودات والتراجع")
    opt("المسودات", "نسخ مستقلة من ترجمتك للملف نفسه: تقدر تعمل أكثر من مسودة (نسخة تجريبية، نسخة بخط ثاني...).",
        "كل مسودة تُحفظ تلقائياً مع آخر صفحة وقفت عندها.", "اختر مسودة من القائمة، أو «جديدة» لمسودة فاضية، أو «نسخ» لتكرار الحالية. الحذف يطلب تأكيداً.")
    with gr.Row():
        m_dsel = gr.Dropdown([], show_label=False, value=None, interactive=True, scale=3)
        b_dnew, b_dcopy, b_ddel = gr.Button("جديدة"), gr.Button("نسخ"), gr.Button("حذف")
    with gr.Row():
        m_dname = gr.Textbox(show_label=False, placeholder="اسم جديد للمسودة", scale=3)
        b_dren = gr.Button("تغيير الاسم", scale=1)
    opt("تراجع وإعادة التعيين", "«تراجع» يلغي آخر تعديل فقط (نص، تنسيق، حذف، إضافة، تبديل صفحات...). «إعادة تعيين الكل» يرجع المسودة للبداية.",
        "أي حذف أو تبديل أو تعديل تقدر ترجع عنه.", "اضغط «تراجع» عدة مرات للرجوع خطوة خطوة.")
    with gr.Row():
        b_undo = gr.Button("↩ تراجع")
        b_reset = gr.Button("⟲ إعادة تعيين الكل (من البداية)")
    m_save = gr.Markdown()
    step("ج", "نطاق الترجمة وإدارة الصفحات")
    with gr.Accordion("نطاق الترجمة: جزء من الملف فقط", open=False):
        opt("النطاق", "تحدد من أي صفحة إلى أي صفحة تترجم (مثلاً من 20 إلى 40).",
            "باقي الصفحات إما تبقى بالأصل أو تُحذف من الملف النهائي.", "علّم «تحديد نطاق»، اكتب البداية والنهاية (حسب أرقام الصفحات الأصلية)، واختر مصير الباقي.")
        with gr.Row():
            r_on = gr.Checkbox(False, label="تحديد نطاق")
            r_a = gr.Number(1, label="من صفحة", precision=0, minimum=1)
            r_b = gr.Number(1, label="إلى صفحة", precision=0, minimum=1)
            r_out = gr.Radio([("تبقى بالأصل (بدون ترجمة)", "keep"), ("تُحذف من الملف النهائي", "delete")], value="keep", label="باقي الصفحات")
        b_range = gr.Button("تطبيق النطاق")
    with gr.Accordion("إدارة الصفحات: حذف، إدراج، استبدال، ترتيب", open=False):
        opt("ترتيب الملف النهائي", "الجدول يعرض صفحات الملف النهائي بترتيبها الحالي.", "تشوف أثر الحذف والنقل والإدراج مباشرة.", "الصفحة الحالية هي اللي تفتحها في المحرر.")
        m_plan = gr.Dataframe(headers=["#", "الصفحة", "الحالة"], interactive=False, wrap=True, max_height=260, value=[])
        opt("حذف الصفحة الحالية", "يحذفها من الملف النهائي.", "تتخلص من صفحات ما تبيها.", "اضغط الزر وأكّد بـ «نعم». تقدر تتراجع بعدها.")
        b_delpage = gr.Button("🗑 حذف الصفحة الحالية")
        opt("نقل أو تبديل", "نقل الصفحة الحالية إلى موضع ثاني، أو تبديلها مع صفحة أخرى.", "تغير ترتيب الصفحات بدون إعادة الملف.", "اكتب رقم الموضع ثم اضغط الزر.")
        with gr.Row():
            mv_to = gr.Number(1, label="رقم الموضع الجديد", precision=0, minimum=1)
            b_move = gr.Button("↕ نقل الصفحة الحالية")
            sw_with = gr.Number(1, label="تبديل مع الصفحة رقم", precision=0, minimum=1)
            b_swap = gr.Button("⇄ تبديل")
        opt("إدراج أو استبدال صفحة من جهازك", "تضيف صفحة من ملف PDF أو صورة، أو صفحة فارغة، في المكان اللي تختاره، أو تستبدل بها الصفحة الحالية.",
            "تصلّح صفحة أو تضيف صفحة بدون إعادة بناء الملف.", "ارفع الملف، واختر رقم الصفحة منه، واختر المكان. الاستبدال يطلب تأكيداً لأنه يحذف القديمة. الصفحات المستوردة تبقى كما هي.")
        ins_file = gr.File(show_label=False, file_types=[".pdf", ".png", ".jpg", ".jpeg", ".webp"])
        with gr.Row():
            ins_page = gr.Number(1, label="رقم الصفحة من الملف المرفوع", precision=0, minimum=1)
            ins_where = gr.Dropdown(WHERE, value=WHERE[0], label="المكان")
        with gr.Row():
            b_ins = gr.Button("➕ إدراج الصفحة")
            b_blank = gr.Button("➕ صفحة فارغة")
    step("د", "الصفحة")
    with gr.Row():
        m_chap = gr.Dropdown([], value=None, label="الفصول (اختر فصلاً)", interactive=True, scale=2)
        b_prev = gr.Button("◀ السابقة", scale=1)
        m_page = gr.Number(1, label="رقم الصفحة", precision=0, minimum=1, scale=1)
        b_go = gr.Button("اذهب", scale=1)
        b_next = gr.Button("التالية ▶", scale=1)
        b_todo = gr.Button("أقرب صفحة ناقصة", scale=1)
    m_info, m_note, m_pager = gr.Markdown(), gr.Markdown(), gr.Markdown()
    with gr.Accordion("🖼 صورة الصفحة الأصلية (اقرأ منها لو النص غير مقروء)", open=False):
        opt("صورة الصفحة الأصلية", "تعرض الصفحة الأصلية كصورة، وحول كل فقرة مربع أحمر برقمها (نفس رقم الفقرة في الخانات).",
            "لو نص الملف تالف أو بلغة غير الإنجليزية وطلع رموزاً، تقرأ منها وتترجم بيدك.", "قارن أرقام المربعات بأرقام الفقرات تحت.")
        m_orig = gr.Image(show_label=False, type="filepath", interactive=False)
    with gr.Accordion("🎨 تنسيق الصفحة كلها (خط، حجم، لون، تحديد، خلفية)", open=False):
        opt("تنسيق الصفحة", "يغيّر كل فقرات الصفحة دفعة واحدة. وتقدر بعدها تغيّر فقرة لوحدها وهي تغلب تنسيق الصفحة.",
            "تتحكم بالصفحة كلها بخطوة وحدة، ولكل خيار زر ↺ يرجعه للافتراضي.", "غيّر القيمة وتُحفظ لحظياً. الحجم نسبة مئوية من الحجم الأصلي (100 = كما هو).")
        with gr.Row():
            p_font = gr.Dropdown(_fonts(), value="", label="الخط", scale=3)
            p_font_r = gr.Button("↺", scale=1)
            p_scale = gr.Slider(40, 250, value=100, step=5, label="الحجم %", scale=3)
            p_scale_r = gr.Button("↺", scale=1)
        with gr.Row():
            p_tOn = gr.Checkbox(False, label="تغيير لون النص")
            p_tc = gr.ColorPicker("#000000", label="لون النص")
            p_tc_r = gr.Button("↺")
            p_hOn = gr.Checkbox(False, label="تحديد يحيط بالكلام")
            p_hc = gr.ColorPicker(HL_DEFAULT, label="لون التحديد")
            p_hc_r = gr.Button("↺")
        opt("خلفية الصفحة", "لون ثابت أو تدرج خلف الصفحة.", "تغيّر شكل الصفحة بسهولة، وتقدر ترجعها للأصل.",
            "اختر قالباً جاهزاً من القائمة، أو اختر النوع والألوان بيدك. الخلفية تظهر خلف النص الأصلي، فلو كانت الصفحة صورة كاملة فقد لا تظهر.")
        bg_preset = gr.Dropdown(list(BG_PRESETS), value=None, label="قوالب جاهزة (ألوان وتدرجات)")
        with gr.Row():
            bg_mode = gr.Radio([("الأصلية", "none"), ("لون ثابت", "solid"), ("تدرج", "gradient")], value="none", label="النوع")
            bg_c1 = gr.ColorPicker("#ffffff", label="اللون الأول")
            bg_c2 = gr.ColorPicker("#cccccc", label="اللون الثاني (للتدرج)")
            bg_dir = gr.Dropdown([("عمودي", "vertical"), ("أفقي", "horizontal"), ("قطري", "diagonal")], value="vertical", label="اتجاه التدرج")
            bg_r = gr.Button("↺ الخلفية الأصلية")
        opt("محاذاة وموضع الصفحة", "محاذاة النص (يمين، وسط، يسار، ضبط الجانبين) وتحريك كل فقرات الصفحة معاً بالأسهم أو بالأرقام.",
            "تعدّل مكان النص كله بخطوة وحدة. وتقدر بعدها تحرك فقرة لوحدها.", "الإزاحة بالنقطة (72 نقطة = بوصة). الأسهم تحرك بمقدار «خطوة السهم»، أو اكتب الرقم مباشرة (أفقي: موجب = يمين، رأسي: موجب = تحت).")
        with gr.Row():
            p_align = gr.Dropdown(ALIGN_CHOICES, value="", label="محاذاة النص", scale=3)
            p_align_r = gr.Button("↺", scale=1)
        with gr.Row():
            p_dx = gr.Number(0, label="إزاحة أفقية للصفحة (نقطة)")
            p_dy = gr.Number(0, label="إزاحة رأسية للصفحة (نقطة)")
            p_step = gr.Number(5, label="خطوة السهم")
            p_pos_r = gr.Button("↺ المكان")
        with gr.Row():
            p_left, p_right, p_up, p_down = gr.Button("◀ يسار"), gr.Button("يمين ▶"), gr.Button("▲ فوق"), gr.Button("▼ تحت")
        b_page_all = gr.Button("⟲ إعادة تعيين كل تنسيق الصفحة (الصفحة + فقراتها + الخلفية)")
        opt("إضافة فقرة", "تضيف فقرة جديدة في الصفحة تحت الفقرة اللي تختار رقمها.", "تكتب نصاً ما كان موجوداً في الأصل.", "اكتب رقم الفقرة اللي بعدها (0 = بالأعلى) واضغط «إضافة». بعدها تحرك مكانها من تنسيق الفقرة.")
        with gr.Row():
            add_after = gr.Number(0, label="أضف بعد الفقرة رقم", precision=0, minimum=0)
            b_add = gr.Button("➕ إضافة فقرة")
    with gr.Accordion("🤖 الذكاء الاصطناعي: المسرد والتعليمات", open=False):
        opt("تعليمات الذكاء لهذي المسودة", "بطاقة السياق (أسماء ومصطلحات) ووصف الأسلوب اللي يستخدمها الذكاء عند ترجمة فقرة أو صفحة.",
            "تثبت الأسماء والأسلوب بين الفقرات.", "اكتب وصف الأسلوب، واضغط «بناء المسرد من النص» ليستخرج الأسماء، وعدّله لو بغيت.")
        m_style = gr.Textbox(show_label=False, lines=2, placeholder="وصف الأسلوب: مثال: سرد أدبي فصيح")
        m_ctx = gr.Textbox(show_label=False, lines=6, elem_classes="ltr", placeholder="بطاقة السياق (JSON)")
        b_ctx = gr.Button("بناء المسرد من النص")
    opt("تنسيق وحذف الفقرات", "كل فقرة بجانبها: «🤖» يترجمها الذكاء، و«🔢» يرقّم أسطرها، و«🗑» يحذفها من الملف النهائي. وداخل «🎨 تنسيق الفقرة»: الخط والحجم واللون والتحديد وإزاحة المكان، ولكل خيار زر ↺ يرجعه للافتراضي.",
        "تتحكم بكل فقرة لوحدها وتقدر ترجع عن أي شي.", "ما تغيّره يُحفظ لحظياً. الحجم 0 = الحجم الأصلي.")
    ars, ens, slot_outs, slot_w = [], [], [], []
    for i in range(SLOTS):
        with gr.Group(visible=False) as g:
            with gr.Row():
                ar = gr.Textbox(label="الترجمة العربية", lines=3, max_lines=14, interactive=True, elem_classes="arbox", rtl=True, scale=3)
                en = gr.Textbox(label="النص الأصلي", lines=3, max_lines=14, interactive=False, elem_classes="enbox", scale=3)
            with gr.Row():
                ai_b, ocr_b, num_b, del_b = (gr.Button("🤖 ترجم بالذكاء"), gr.Button("👁 اقرأ من الصورة"),
                                             gr.Button("🔢 ترقيم الأسطر"), gr.Button("🗑 حذف الفقرة"))
            with gr.Accordion("🎨 تنسيق وموضع هذي الفقرة", open=False):
                with gr.Row():
                    f_font = gr.Dropdown(_fonts(), value="", label="الخط والأسلوب", scale=3)
                    f_font_r = gr.Button("↺", scale=1)
                    f_size = gr.Number(0, label="الحجم بالنقطة (0 = الأصلي)", scale=3)
                    f_size_r = gr.Button("↺", scale=1)
                with gr.Row():
                    f_align = gr.Dropdown(ALIGN_CHOICES, value="", label="محاذاة النص", scale=3)
                    f_align_r = gr.Button("↺", scale=1)
                with gr.Row():
                    f_tOn = gr.Checkbox(False, label="تغيير لون النص")
                    f_tc = gr.ColorPicker("#000000", label="لون النص")
                    f_tc_r = gr.Button("↺")
                    f_hOn = gr.Checkbox(False, label="تحديد يحيط بالكلام")
                    f_hc = gr.ColorPicker(HL_DEFAULT, label="لون التحديد")
                    f_hc_r = gr.Button("↺")
                with gr.Row():
                    f_dx = gr.Number(0, label="إزاحة أفقية (نقطة)")
                    f_dy = gr.Number(0, label="إزاحة رأسية (نقطة)")
                    f_step = gr.Number(5, label="خطوة السهم")
                with gr.Row():
                    f_left, f_right, f_up, f_down = gr.Button("◀ يسار"), gr.Button("يمين ▶"), gr.Button("▲ فوق"), gr.Button("▼ تحت")
                    f_pos_r = gr.Button("↺ المكان")
                    f_all_r = gr.Button("⟲ إعادة تعيين كل تنسيق الفقرة")
        ars.append(ar)
        ens.append(en)
        slot_outs += [g, en, ar, del_b, f_font, f_size, f_tOn, f_tc, f_hOn, f_hc, f_dx, f_dy, f_align]
        slot_w.append(dict(ai=ai_b, ocr=ocr_b, num=num_b, de=del_b, font=f_font, size=f_size, tOn=f_tOn, tc=f_tc, hOn=f_hOn, hc=f_hc,
                           dx=f_dx, dy=f_dy, align=f_align, step=f_step, r_font=f_font_r, r_size=f_size_r, r_align=f_align_r,
                           r_tc=f_tc_r, r_hc=f_hc_r, r_pos=f_pos_r, r_all=f_all_r, left=f_left, right=f_right, up=f_up, down=f_down))
    with gr.Row():
        b_save = gr.Button("💾 حفظ هذي الصفحة")
        b_grp_prev, b_grp_next = gr.Button("◀ الفقرات السابقة"), gr.Button("الفقرات التالية ▶")
        ai_keep = gr.Checkbox(True, label="لا تستبدل الفقرات اللي كتبتها")
        b_ai_page = gr.Button("🤖 ترجم كل فقرات الصفحة بالذكاء")
        b_ocr_page = gr.Button("👁 اقرأ النصوص غير المقروءة بالذكاء")
    step("هـ", "المعاينة والملف النهائي")
    opt("الخط الافتراضي للملف", "الخط العربي اللي يُستخدم لكل الفقرات إلا لو غيّرت خط صفحة أو فقرة.",
        "الحروف العربية تحتاج خطاً عربياً، وهذا يحدد شكله.", "اختر الخط. تقدر تضيف خطوطك بوضع ملف ttf في مجلد fonts باسم «Name-Regular.ttf» و«Name-Bold.ttf».")
    m_font = gr.Dropdown(_fonts(), value="", show_label=False)
    opt("المعاينة", "تعرض أي صفحة كما ستظهر في الملف النهائي بترجمتك وتنسيقك، وتتنقل بين المعاينات بسرعة.",
        "تتأكد من الخط والمكان والألوان قبل إدراج الكل.", "اضغط «معاينة الصفحة الحالية»، ثم تنقل بأزرار السابقة والتالية.")
    with gr.Row():
        b_pv_prev, b_pv_cur, b_pv_next = gr.Button("◀ معاينة السابقة"), gr.Button("👁 معاينة الصفحة الحالية", variant="primary"), gr.Button("معاينة التالية ▶")
        b_pv_edit = gr.Button("✍ حرّر الصفحة المعروضة")
    m_pvinfo = gr.Markdown()
    m_img = gr.Image(show_label=False, type="filepath", interactive=False)
    opt("إدراج الترجمة في الملف", "يبني ملف PDF جديد: يحذف النص الإنجليزي من الفقرات المترجمة ويكتب ترجمتك مكانه بنفس الموضع، ويطبق الصفحات والتنسيقات والحذف.",
        "الفقرات اللي ما ترجمتها تبقى بالإنجليزي، فتقدر تسلّم على دفعات.", "اضغط الزر ثم نزّل الملف.")
    b_build = gr.Button("✅ تأكيد وإدراج الترجمة في الملف", variant="primary")
    m_out = gr.File(show_label=False)

    OUTS = ([m_pid, m_did, m_cur, m_grp, m_page, m_msg, m_info, m_note] + slot_outs
            + [p_font, p_scale, p_tOn, p_tc, p_hOn, p_hc, bg_mode, bg_c1, bg_c2, bg_dir, p_align, p_dx, p_dy, r_on, r_a, r_b, r_out]
            + [m_plan, m_sel, m_dsel, m_chap, m_ctx, m_style, m_font, m_orig, m_pager, m_pending, m_confirm, m_cq])
    S = [m_pid, m_did, m_cur, m_grp]
    NAV_IN = S + [m_page]
    # open / projects / drafts
    b_new.click(h_new, m_file, OUTS)
    b_open.click(h_open, m_sel, OUTS)
    b_job.click(h_from_job, m_job, OUTS)
    b_delp.click(h_req_del_project, S + [m_sel], OUTS)
    m_dsel.input(h_dswitch, [m_pid, m_dsel], OUTS)
    b_dnew.click(h_dnew, m_pid, OUTS)
    b_dcopy.click(h_dcopy, [m_pid, m_did], OUTS)
    b_ddel.click(h_req_del_draft, S, OUTS)
    b_dren.click(h_drename, [m_pid, m_did, m_dname], OUTS)
    b_undo.click(h_undo, S, OUTS)
    b_reset.click(h_req_reset, S, OUTS)
    b_yes.click(h_yes, S + [m_pending], OUTS)
    b_no.click(h_no, S, OUTS)
    # navigation
    b_prev.click(lambda *a: h_nav(*a[:5], "prev", *a[5:]), NAV_IN + ars, OUTS)
    b_next.click(lambda *a: h_nav(*a[:5], "next", *a[5:]), NAV_IN + ars, OUTS)
    b_go.click(lambda *a: h_nav(*a[:5], "go", *a[5:]), NAV_IN + ars, OUTS)
    b_todo.click(lambda *a: h_nav(*a[:5], "todo", *a[5:]), NAV_IN + ars, OUTS)
    m_chap.input(lambda pid, did, cur, grp, ch, *a: h_nav(pid, did, cur, grp, ch, "chap", *a), S + [m_chap] + ars, OUTS)
    b_grp_prev.click(lambda pid, did, cur, grp, *a: h_grp(pid, did, cur, grp, -1, *a), S + ars, OUTS)
    b_grp_next.click(lambda pid, did, cur, grp, *a: h_grp(pid, did, cur, grp, 1, *a), S + ars, OUTS)
    b_save.click(h_save_page, S + ars, m_save)
    # range / plan
    b_range.click(h_range, S + [r_on, r_a, r_b, r_out], OUTS)
    b_delpage.click(h_req_del_page, S, OUTS)
    b_move.click(h_move, S + [mv_to], OUTS)
    b_swap.click(h_swap, S + [sw_with], OUTS)
    b_ins.click(lambda pid, did, cur, grp, f, p, w: h_insert(pid, did, cur, grp, f, p, w, False), S + [ins_file, ins_page, ins_where], OUTS)
    b_blank.click(lambda pid, did, cur, grp, w: h_insert(pid, did, cur, grp, None, 1, w, True), S + [ins_where], OUTS)
    # page style
    pst = [p_font, p_scale, p_tOn, p_tc, p_hOn, p_hc, bg_mode, bg_c1, bg_c2, bg_dir, p_align, p_dx, p_dy]
    for c in pst:
        c.input(h_page_style, [m_pid, m_did, m_cur] + pst, m_save)
    bg_preset.input(h_bg_preset, [m_pid, m_did, m_cur, bg_preset], [bg_mode, bg_c1, bg_c2, bg_dir, m_save])
    for btn, w in ((p_font_r, "font"), (p_scale_r, "scale"), (p_tc_r, "tcolor"), (p_hc_r, "hl"), (bg_r, "bg"), (p_align_r, "align"), (p_pos_r, "pos")):
        btn.click(lambda pid, did, cur, w=w: h_page_reset(pid, did, cur, w), [m_pid, m_did, m_cur], pst + [m_save])
    for btn, dirn in ((p_left, "left"), (p_right, "right"), (p_up, "up"), (p_down, "down")):
        btn.click(lambda pid, did, cur, step, dirn=dirn: h_page_move(pid, did, cur, dirn, step), [m_pid, m_did, m_cur, p_step], [p_dx, p_dy, m_save])
    b_page_all.click(h_page_reset_all, S, OUTS)
    b_add.click(h_add_para, S + [add_after], OUTS)
    # AI + defaults
    b_ai_page.click(h_ai_page, S + [ai_keep], OUTS)
    b_ocr_page.click(h_ocr_page, S, OUTS)
    m_style.blur(h_ai_cfg, [m_pid, m_did, m_ctx, m_style], m_save)
    m_ctx.blur(h_ai_cfg, [m_pid, m_did, m_ctx, m_style], m_save)
    b_ctx.click(h_ai_ctx, [m_pid, m_did], [m_ctx, m_save])
    m_font.input(h_font, [m_pid, m_did, m_font], m_save)
    # slots
    for i, w in enumerate(slot_w):
        ar = ars[i]
        ar.blur(lambda pid, did, cur, grp, t, i=i: h_blur(pid, did, cur, grp, t, i), S + [ar], m_save)
        w["ai"].click(lambda pid, did, cur, grp, i=i: h_ai_slot(pid, did, cur, grp, i), S, [ar, m_save])
        w["ocr"].click(lambda pid, did, cur, grp, i=i: h_ocr_slot(pid, did, cur, grp, i), S, [ens[i], m_save])
        w["num"].click(lambda pid, did, cur, grp, t, i=i: h_num(pid, did, cur, grp, t, i), S + [ar], [ar, m_save])
        w["de"].click(lambda pid, did, cur, grp, i=i: h_slot_del(pid, did, cur, grp, i), S, OUTS)
        ctr = [w[k] for k in ("font", "size", "tOn", "tc", "hOn", "hc", "dx", "dy", "align")]
        for c in ctr:
            c.input(lambda pid, did, cur, grp, *v, i=i: h_slot_style(pid, did, cur, grp, i, *v), S + ctr, m_save)
        for key, which in (("r_font", "font"), ("r_size", "size"), ("r_align", "align"), ("r_tc", "tcolor"), ("r_hc", "hl"), ("r_pos", "pos"), ("r_all", "all")):
            w[key].click(lambda pid, did, cur, grp, i=i, which=which: h_slot_reset(pid, did, cur, grp, i, which), S, ctr + [m_save])
        for key in ("left", "right", "up", "down"):
            w[key].click(lambda pid, did, cur, grp, step, i=i, key=key: h_slot_move(pid, did, cur, grp, i, key, step), S + [w["step"]], [w["dx"], w["dy"], m_save])
    # preview + final file
    PV = S + [m_pv]
    b_pv_cur.click(lambda pid, did, cur, grp, pv, *a: h_preview(pid, did, cur, grp, pv, "cur", *a), PV + ars, [m_img, m_pv, m_pvinfo, m_save])
    b_pv_prev.click(lambda pid, did, cur, grp, pv, *a: h_preview(pid, did, cur, grp, pv, "prev", *a), PV + ars, [m_img, m_pv, m_pvinfo, m_save])
    b_pv_next.click(lambda pid, did, cur, grp, pv, *a: h_preview(pid, did, cur, grp, pv, "next", *a), PV + ars, [m_img, m_pv, m_pvinfo, m_save])
    b_pv_edit.click(h_pv_edit, PV, OUTS)
    b_build.click(h_build, S + ars, [m_out, m_save])
    return {"project_choices": _proj_choices, "job_choices": _job_choices, "sel": m_sel, "job": m_job}
