"""Navigation and the paragraphs: typing, autosave, AI translation, reading from the picture, adding / deleting paragraphs."""
import time
from concurrent.futures import ThreadPoolExecutor
import gradio as gr
from core import builder, editor, manual, manual_ai, priority
from core.pool import NoKeys
from ui.common import guard, safe, toast
from core import textcheck
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


def _routes(model, fb, checker, cfb):
    return (priority.new_route("translate", model or priority.AUTO, bool(fb), max_wait=30),
            priority.new_route("edit", checker or priority.AUTO, bool(cfb), max_wait=30))


def _notice(text, title, secs=7):
    if text:
        gr.Info(text, title=title, duration=secs)


def _ai(pid, did, items, route):
    """Translates the items; the side notice says who works, for about how long, and what is left of its limit."""
    meta, units, d = load_all(pid, did)
    _notice(priority.announce(route, "translate", "يترجم الآن", len(items)), "🤖 الذكاء الاصطناعي يشتغل", 6)
    try:
        res = manual_ai.translate_units([{"uid": i["uid"], "text": i["en"]} for i in items], d.get("ctx", ""), d.get("style", ""), route)
    except NoKeys as e:
        raise gr.Error(str(e), title="ما فيه ذكاء متاح الآن")
    _notice(priority.summary(route, "ترجم"), "✅ انتهت الترجمة", 14)
    return res


def _review(pid, did, pairs, route):
    """pairs: [{"uid","text","tr"}] -> {uid: corrected}. Shows who checks and what is left."""
    meta, units, d = load_all(pid, did)
    _notice(priority.announce(route, "edit", "يدقق الآن", len(pairs)), "🔍 التدقيق يشتغل", 6)
    try:
        fixed = editor.review_units(pairs, "ar", d.get("ctx", ""), d.get("style", ""), route=route)
    except NoKeys as e:
        raise gr.Error(str(e), title="ما فيه مدقق متاح الآن")
    _notice(priority.summary(route, "دقّق") + f"<br>عدّل {len(fixed)} من {len(pairs)} فقرة" if route["calls"] else None, "✅ انتهى التدقيق", 14)
    return fixed


def _names_hint(d, units):
    """What the book already tells us about spelling: the context/glossary of the draft and a little readable text."""
    parts = [(d.get("ctx") or "").strip()[:900]]
    good = [u.get("text", "") for u in units if u.get("kind") == "text" and 40 < len(u.get("text", "")) < 400
            and not textcheck.garbled(u.get("text", ""))][:4]
    if good:
        parts.append("Sample of readable text from the book:\n" + "\n".join(good))
    return "\n\n".join(p for p in parts if p)


def _ocr_items(pid, did, items):
    meta, units, d = load_all(pid, did)
    by = {u["id"]: u for u in units}
    src = manual.source_path(pid)

    hint = _names_hint(d, units)

    def one(it):
        u = by[it["uid"]]
        mask = [v["bbox"] for v in units if v is not u and v.get("page") == u["page"] and v.get("bbox")]
        return it["uid"], manual_ai.read_image(builder.crop_png(src, u["page"], u["bbox"], mask=mask), hint)
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


def _save_tr(pid, did, mapping):
    with manual._lock:
        d = manual.load_draft(pid, did)
        for uid, tr in mapping.items():
            manual.set_text(d, uid, tr)
        manual.save_draft(pid, d)


@safe
def ai_slot(pid, did, cur, grp, i, model, fb, mode, checker, cfb):
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
    rt, re_ = _routes(model, fb, checker, cfb)
    tr, flag = _ai(pid, did, [it], rt).get(it["uid"], ("", ""))
    if not tr:
        raise gr.Error("ما رجعت ترجمة. جرّب مرة ثانية أو راجع المفاتيح.", title="ما رجعت ترجمة")
    if mode == "review":
        tr = _review(pid, did, [{"uid": it["uid"], "text": it["en"], "tr": tr}], re_).get(it["uid"], tr)
    _save_tr(pid, did, {it["uid"]: tr})
    if flag:
        toast(f"ملاحظة على الترجمة: {flag}", warn=True)
    return R(**{f"s{i}_ar": tr})


@safe
def review_slot(pid, did, cur, grp, i, model, fb, mode, checker, cfb):
    """Checks the translation that is already written in this paragraph's box."""
    guard()
    need(pid)
    it = items_now(pid, did, cur, grp)[5][i]
    if not it["ar"].strip():
        raise gr.Error("اكتب ترجمة أو اضغط «ترجم» أولاً، ما فيه شي أدققه", title="الخانة فاضية")
    fixed = _review(pid, did, [{"uid": it["uid"], "text": it["en"], "tr": it["ar"]}], _routes(model, fb, checker, cfb)[1])
    if not fixed:
        toast("المدقق ما لقى شي يحتاج تعديل في هذي الفقرة ✓")
        return R(**{f"s{i}_ar": it["ar"]})
    _save_tr(pid, did, fixed)
    return R(**{f"s{i}_ar": fixed[it["uid"]]})


@safe
def ai_page(pid, did, cur, grp, keep_manual, model, fb, mode, checker, cfb):
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
    rt, re_ = _routes(model, fb, checker, cfb)
    res = _ai(pid, did, todo, rt)
    out = {it["uid"]: res[it["uid"]][0] for it in todo if res.get(it["uid"], ("", ""))[0]}
    if mode == "review" and out:
        src = {it["uid"]: it["en"] for it in todo}
        out.update(_review(pid, did, [{"uid": u, "text": src[u], "tr": t} for u, t in out.items()], re_))
    _save_tr(pid, did, out)
    return view(pid, did, cur, grp, f"🤖 تُرجمت {len(out)} فقرة" + (" وتم تدقيقها" if mode == "review" else "") + ". راجعها وعدّل عليها بيدك.")


@safe
def review_page(pid, did, cur, grp, model, fb, mode, checker, cfb):
    guard()
    need(pid)
    allit = items_now(pid, did, cur, grp)[4]
    pairs = [{"uid": i["uid"], "text": i["en"], "tr": i["ar"]} for i in allit if i["ar"].strip() and not i["custom"] and not i["deleted"]]
    if not pairs:
        return view(pid, did, cur, grp, "ما فيه ترجمات مكتوبة في هذي الصفحة أدققها.")
    fixed = _review(pid, did, pairs, _routes(model, fb, checker, cfb)[1])
    _save_tr(pid, did, fixed)
    return view(pid, did, cur, grp, f"🔍 دُقّقت {len(pairs)} فقرة وعُدّلت {len(fixed)} منها." if fixed else "🔍 المدقق ما لقى شي يحتاج تعديل ✓")


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
