"""Navigation and the paragraphs: typing, autosave, AI translation, reading from the picture, adding / deleting paragraphs."""
import time
from concurrent.futures import ThreadPoolExecutor
import gradio as gr
from core import builder, manual, manual_ai
from core.pool import NoKeys
from ui.common import guard, safe, toast
from .consts import SLOTS
from .data import autosave, cur_items, items_now, load_all, need, orig_page
from .reg import R
from .view import view


@safe
def nav(pid, did, cur, grp, target, how, *ars):
    guard()
    need(pid)
    autosave(pid, did, cur, grp, ars)
    meta, units, d = load_all(pid, did)
    eff = manual.effective_plan(d)
    if how == "next":
        pos = int(cur) + 1
    elif how == "prev":
        pos = int(cur) - 1
    elif how == "todo":
        pos = next((p for p in range(int(cur) + 1, len(eff)) if any(not d["tr"].get(i["uid"]) and not i["deleted"] and not i["custom"]
                                                                  for i in cur_items(units, d, eff, p)[1])), int(cur))
        if pos == int(cur):
            toast("ما لقيت صفحة ناقصة بعد هذي الصفحة.", warn=True)
    elif how == "chap":
        pg = int(target) - 1
        pos = next((i for i, e in enumerate(eff) if e["k"] == "o" and e["p"] >= pg), int(cur))
    else:
        pos = int(target or 1) - 1
    out = view(pid, did, pos, 0)
    out.update(auto_preview(pid, did, pos))
    return out


def auto_preview(pid, did, pos):
    """The picture of the page we just moved to, so translating and checking never needs an extra click."""
    from .h_output import preview_png
    try:
        png, _, text = preview_png(pid, did, pos)
        return R(pv_img=png, pv_info=text)
    except Exception as e:
        return R(pv_info=f"تعذرت المعاينة: {e}")


@safe
def group(pid, did, cur, grp, step, *ars):
    guard()
    need(pid)
    autosave(pid, did, cur, grp, ars)
    return view(pid, did, cur, int(grp) + step)


@safe
def save_page(pid, did, cur, grp, *ars):
    need(pid)
    n = autosave(pid, did, cur, grp, ars)
    return R(saved=f"💾 حُفظت الصفحة ({n} تعديل).")


@safe
def blur(pid, did, cur, grp, text, i):
    if not pid:
        return R(saved="")
    n = autosave(pid, did, cur, grp, [None] * i + [text])
    return R(saved=f"💾 حُفظ تلقائياً {time.strftime('%H:%M:%S')}" if n else "")


@safe
def number_lines(pid, did, cur, grp, text, i):
    guard()
    need(pid)
    new = manual_ai.number_lines(text)
    autosave(pid, did, cur, grp, [None] * i + [new])
    toast("🔢 رُقّمت الأسطر.")
    return R(**{f"s{i}_ar": new})


def _ai(pid, did, items):
    meta, units, d = load_all(pid, did)
    try:
        return manual_ai.translate_units([{"uid": i["uid"], "text": i["en"]} for i in items], d.get("ctx", ""), d.get("style", ""))
    except NoKeys as e:
        raise gr.Error(str(e), title="ما فيه مفاتيح تشتغل")


def _ocr_items(pid, did, items):
    meta, units, d = load_all(pid, did)
    by = {u["id"]: u for u in units}
    src = manual.source_path(pid)

    def one(it):
        u = by[it["uid"]]
        return it["uid"], manual_ai.read_image(builder.crop_png(src, u["page"], u["bbox"]))
    try:
        with ThreadPoolExecutor(4) as ex:
            results = list(ex.map(one, [i for i in items if i["uid"] in by]))
    except NoKeys as e:
        raise gr.Error(str(e), title="ما فيه مفتاح يقرأ الصور")
    except Exception as e:
        raise gr.Error(f"تعذرت القراءة من الصورة: {e}", title="فشلت القراءة")
    with manual._lock:
        d = manual.load_draft(pid, did)
        for uid, txt in results:
            manual.set_src(d, uid, txt)
        manual.save_draft(pid, d)
    return len(results)


@safe
def ocr_slot(pid, did, cur, grp, i):
    guard()
    need(pid)
    meta, units, d, eff, allit, items = items_now(pid, did, cur, grp)
    if i >= len(items) or items[i]["custom"]:
        raise gr.Error("هذي الفقرة ما لها نص أصلي", title="لا يمكن")
    _ocr_items(pid, did, [items[i]])
    items = items_now(pid, did, cur, grp)[5]
    toast("👁 قُرئ النص من الصورة. راجعه وتأكد منه.")
    return R(**{f"s{i}_en": items[i]["en"]})


@safe
def ocr_page(pid, did, cur, grp):
    guard()
    need(pid)
    allit = items_now(pid, did, cur, grp)[4]
    bad = [x for x in allit if x["garbled"] and not x["custom"] and not x["deleted"]]
    if not bad:
        return view(pid, did, cur, grp, "ما فيه فقرات غير مقروءة في هذي الصفحة.")
    n = _ocr_items(pid, did, bad)
    return view(pid, did, cur, grp, f"👁 قُرئت {n} فقرة من الصورة. راجع النصوص قبل الترجمة.")


@safe
def ai_slot(pid, did, cur, grp, i):
    guard()
    need(pid)
    allit, items = items_now(pid, did, cur, grp)[4:6]
    if i >= len(items):
        raise gr.Error("لا توجد فقرة", title="لا يمكن")
    it = items[i]
    if it["custom"]:
        raise gr.Error("الفقرة المضافة ما لها نص أصلي تترجمه", title="لا يمكن")
    if it["garbled"]:
        _ocr_items(pid, did, [it])
        it = items_now(pid, did, cur, grp)[5][i]
    tr, flag = _ai(pid, did, [it]).get(it["uid"], ("", ""))
    if not tr:
        raise gr.Error("ما رجعت ترجمة. جرّب مرة ثانية أو راجع المفاتيح.", title="ما رجعت ترجمة")
    with manual._lock:
        d = manual.load_draft(pid, did)
        manual.set_text(d, it["uid"], tr)
        manual.save_draft(pid, d)
    toast("🤖 تمت ترجمة الفقرة" + (f" (ملاحظة: {flag})" if flag else "") + ". عدّل عليها بيدك لو تبي.", warn=bool(flag))
    return R(**{f"s{i}_ar": tr})


@safe
def ai_page(pid, did, cur, grp, keep_manual):
    guard()
    need(pid)
    allit = items_now(pid, did, cur, grp)[4]
    bad = [x for x in allit if x["garbled"] and not x["custom"] and not x["deleted"]]
    if bad:
        _ocr_items(pid, did, bad)
        allit = items_now(pid, did, cur, grp)[4]
    todo = [i for i in allit if not i["custom"] and not i["deleted"] and (not keep_manual or not i["ar"].strip())]
    if not todo:
        return view(pid, did, cur, grp, "ما فيه فقرات تحتاج ترجمة في هذي الصفحة.")
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
    return view(pid, did, cur, grp, f"🤖 تُرجمت {n} فقرة بالذكاء الاصطناعي. راجعها وعدّل عليها بيدك.")


@safe
def ai_cfg(pid, did, ctx, style):
    if not pid:
        return R(saved="")
    with manual._lock:
        d = manual.load_draft(pid, did)
        d["ctx"], d["style"] = ctx or "", style or ""
        manual.save_draft(pid, d)
    return R(saved="💾 حُفظت تعليمات الذكاء.")


@safe
def ai_ctx(pid, did):
    guard()
    need(pid)
    meta, units, d = load_all(pid, did)
    try:
        ctx = manual_ai.build_context([u["text"] for u in units if u.get("translate")], d.get("style", ""))
    except NoKeys as e:
        raise gr.Error(str(e), title="ما فيه مفاتيح تشتغل")
    if not ctx:
        raise gr.Error("ما قدر البرنامج يبني المسرد. تأكد من المفاتيح.", title="فشل بناء المسرد")
    ai_cfg(pid, did, ctx, d.get("style", ""))
    toast("✅ بُني المسرد من نص الملف. تقدر تعدله.")
    return R(ctx=ctx)


@safe
def slot_delete(pid, did, cur, grp, i):
    guard()
    need(pid)
    with manual._lock:
        allit, items = items_now(pid, did, cur, grp)[4:6]
        d = manual.load_draft(pid, did)
        if i >= len(items):
            raise gr.Error("لا توجد فقرة", title="لا يمكن")
        it = items[i]
        if it["custom"]:
            manual.delete_extra(d, it["uid"])
            msg = "🗑 حُذفت الفقرة المضافة. تقدر تتراجع."
        else:
            _, now = manual.toggle_deleted(d, it["uid"])
            msg = "🗑 ستُحذف الفقرة من الملف النهائي. تقدر تتراجع." if now else "↩ استُعيدت الفقرة."
        manual.save_draft(pid, d)
    return view(pid, did, cur, grp, msg)


@safe
def add_para(pid, did, cur, grp, after_n):
    guard()
    need(pid)
    with manual._lock:
        meta, units, d, eff, allit, items = items_now(pid, did, cur, grp)
        p = orig_page(d, cur)
        if p is None:
            raise gr.Error("الإضافة ممكنة فقط في الصفحات الأصلية داخل نطاق الترجمة", title="لا يمكن")
        n = int(after_n or 0)
        manual.new_extra(d, units, p, allit[n - 1]["uid"] if 1 <= n <= len(allit) else "")
        manual.save_draft(pid, d)
    return view(pid, did, cur, grp, "➕ أُضيفت فقرة جديدة. اكتب نصها، وحرّك مكانها من اللوحة الجانبية.")
