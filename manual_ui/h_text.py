"""Navigation and the paragraphs: typing, autosave, AI translation, reading from the picture, adding / deleting paragraphs."""
import re
import time
from concurrent.futures import ThreadPoolExecutor
import gradio as gr
from core import ocr_local
from core import builder, editor, manual, manual_ai, priority
from core.pool import NoKeys
from ui.common import guard, safe, toast
from core import textcheck
from .consts import SLOTS
from .data import autosave, cur_items, items_now, load_all, need, orig_page
from .reg import R
from .view import _say, view


def _target(pid, did, cur, target, how):
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
    return max(0, min(pos, len(eff) - 1)) if eff else 0


@safe
def nav(pid, did, cur, grp, target, how, *ars):
    guard()
    need(pid)
    autosave(pid, did, cur, grp, ars)
    return view(pid, did, _target(pid, did, cur, target, how), 0)


@safe
def flip(pid, did, cur, grp, target, how, *ars):
    """Step 1 of a page change: save what was typed, pick the page and draw its picture. Only three small answers, so it is instant;
    the paragraphs follow in step 2 (show)."""
    guard()
    need(pid)
    autosave(pid, did, cur, grp, ars)
    pos = _target(pid, did, cur, target, how)
    png, text = pv_now(pid, did, pos)
    return pos, png, text


@safe
def style_slot(pid, did, cur, grp, i):
    """«🎨 نسّق هذي الفقرة»: the shared paragraph panel opens on paragraph number grp*SLOTS+i+1."""
    need(pid)
    from . import panel
    from .consts import SLOTS
    d, allit, e = panel._now(pid, did, cur, grp, panel.PARA, 1)
    n = int(grp) * SLOTS + i + 1
    out = R(q_n=n, q_acc=gr.update(open=True))
    out.update(panel.values(d, allit, e, panel.PARA, n, "q_"))
    return out


@safe
def style_load(pid, did, cur, grp, n):
    """The number in the panel changed: show that paragraph's style."""
    need(pid)
    from . import panel
    d, allit, e = panel._now(pid, did, cur, grp, panel.PARA, n)
    return panel.values(d, allit, e, panel.PARA, int(n or 1), "q_")


_NUM = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_HEAD = re.compile(r"^\s*[=\-#*\s]*(?:صفحة|الصفحة|page)\s*([0-9٠-٩]+)\s*[=\-#*\s]*$", re.I)
_ITEM = re.compile(r"^\s*[\[(]?([0-9٠-٩]+)[\])]?\s*[\).:\-–،]\s*(.*)$")


def parse_pasted(text):
    """«=== صفحة 5 ===» lines (optional) and numbered paragraphs «1) ...» → {page or None: {number: text}}."""
    out, page, num = {}, None, None
    for ln in (text or "").splitlines():
        h = _HEAD.match(ln)
        if h:
            page, num = int(h.group(1).translate(_NUM)), None
            continue
        m = _ITEM.match(ln)
        if m:
            num = int(m.group(1).translate(_NUM))
            out.setdefault(page, {})[num] = "" if "لا يوجد نص" in m.group(2) and len(m.group(2)) < 20 else m.group(2).strip()
        elif ln.strip() and num is not None:
            out[page][num] = (out[page][num] + " " + ln.strip()).strip()
    return out


def read_txt(path):
    """Text of a .txt file in whatever encoding it was saved (UTF-8 with/without BOM, UTF-16, Windows Arabic)."""
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp1256"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", "replace")


@safe
def load_txt(file):
    """A .txt file with the numbered translation: its text goes into the paste box (so it can be checked before pasting)."""
    from .data import path_of
    path = path_of(file)
    if not path:
        return gr.update()
    text = read_txt(path)
    n = len(parse_pasted(text).get(None, {})) + sum(len(v) for k, v in parse_pasted(text).items() if k is not None)
    if not n:
        toast("قرأت الملف لكن ما لقيت فيه فقرات مرقّمة بالشكل 1) النص.", warn=True)
    else:
        toast(f"📄 قرأت الملف: {n} فقرة. راجعها ثم اضغط «ألصق الترجمة في الفقرات».")
    return text


def _page_obstacles(pid, p):
    """Pictures/ornaments of the original page (they stay), so pasted text is laid around them."""
    try:
        import fitz
        with fitz.open(manual.source_path(pid)) as doc:
            return [tuple(i["bbox"]) for i in doc[p].get_image_info()]
    except Exception:
        return []


def _page_ink(pid, p, units):
    """{unit id: (left, top, right, bottom)} of the real ink of each original line (the text layer's boxes can be wider than what is seen)."""
    out = {}
    try:
        import fitz
        import numpy as np
        with fitz.open(manual.source_path(pid)) as doc:
            pg = doc[p]
            sc = 2.0
            pm = pg.get_pixmap(matrix=fitz.Matrix(sc, sc), colorspace=fitz.csGRAY)
            a = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width)
            bg = int(np.median(a))
            dark = a < max(40, bg - 70)
            for u in units:
                if u["page"] != p:
                    continue
                x0, y0, x1, y1 = u["bbox"]
                l, t, r, b = max(int((x0 - 2) * sc), 0), max(int((y0 - 1) * sc), 0), min(int((x1 + 2) * sc), pm.width), min(int((y1 + 1) * sc), pm.height)
                sub = dark[t:b, l:r]
                cols, rows = np.where(sub.any(0))[0], np.where(sub.any(1))[0]
                if len(cols) and len(rows):
                    out[u["id"]] = (l / sc + cols[0] / sc, t / sc + rows[0] / sc, l / sc + (cols[-1] + 1) / sc, t / sc + (rows[-1] + 1) / sc)
    except Exception:
        return {}
    return out


_scale_cache = {}


def _book_scale(pid, units, font):
    """How big the book's own type is compared with what its text layer says (measured once per book from a spread of its pages)."""
    key = (pid, font)
    if key not in _scale_cache:
        try:
            pages = sorted({u["page"] for u in units if len(u["text"]) > 100})
            pick = [pages[int(i * (len(pages) - 1) / 9)] for i in range(10)] if len(pages) > 10 else pages
            cases = []
            for p in dict.fromkeys(pick):
                cases += manual.calib_cases(units, p, _page_ink(pid, p, units))
            _scale_cache[key] = manual.calib_ratio(cases, font)
        except Exception:
            _scale_cache[key] = None
    return _scale_cache[key]


def _page_font(pid, p):
    """The page's own font, when it is one of the fonts the site has (the book here is set in Amiri)."""
    try:
        import fitz
        from core import builder
        names = {k.replace(" ", "").lower(): k for k in builder.font_families()}
        with fitz.open(manual.source_path(pid)) as doc:
            for f in doc[p].get_fonts():
                base = f[3].split("+")[-1].split("-")[0].replace(" ", "").lower()
                if base in names:
                    return names[base]
    except Exception:
        pass
    return ""


def apply_parsed(pid, did, cur, parsed, label, how="file"):
    """Writes parsed {page or None: {number: text}} into the paragraphs in ONE undo step. -> (paragraphs written, what was not found, pages touched)."""
    done, missing, touched = 0, [], set()
    with manual._lock:
        meta, units, d = load_all(pid, did)
        eff = manual.effective_plan(d)
        from core.manual import Tx
        tx = Tx(d, label)
        for page, paras in parsed.items():
            pos = int(cur) if page is None else next((i for i, e in enumerate(eff) if e["k"] == "o" and e["p"] == page - 1), None)
            if pos is None:
                missing.append(f"صفحة {page}")
                continue
            e = eff[pos]
            if e["k"] == "o" and how != "page" and any(x["page"] == e["p"] and x.get("repl") for x in d["extra"].values()):
                how_p = "page"                                 # this page already got a whole-page paste: the new one replaces it (not mixed into it)
            else:
                how_p = how
            if how_p == "page":                                # the whole page's text is replaced and laid out again
                k = manual.replace_page_text(d, units, e["p"], [t for _, t in sorted(paras.items())], _page_obstacles(pid, e["p"]), _page_font(pid, e["p"]), _page_ink(pid, e["p"], units), _book_scale(pid, units, _page_font(pid, e["p"]))) if e["k"] == "o" else 0
                if k:
                    done += k
                    touched.add(pos)
                else:
                    missing.append(f"صفحة {page or pos + 1} (ما فيها نص أصلي)")
                continue
            items = cur_items(units, d, eff, pos)[1]
            for n, t in paras.items():
                if 1 <= n <= len(items) and not items[n - 1]["deleted"] and t:
                    tx.set("tr", items[n - 1]["uid"], value=t)
                    done += 1
                    touched.add(pos)
                elif t:
                    missing.append(f"فقرة {n}" + (f" بصفحة {page}" if page else ""))
        tx.commit()
        manual.save_draft(pid, d)
    return done, missing, touched


@safe
def import_book(pid, did, cur, grp, kind, a, b, how, text):
    """Tab «لصق ترجمة جاهزة»: the whole file's translation (pages marked «=== صفحة N ===»), or only pages a..b of it."""
    guard()
    need(pid)
    parsed = parse_pasted(text)
    if not parsed:
        raise gr.Error("ما لقيت فقرات مرقّمة. كل فقرة بسطر يبدأ برقمها: 1) النص", title="لصق ترجمة")
    if None in parsed:
        raise gr.Error("لازم تفصل الصفحات بسطر مثل «=== صفحة 5 ===» قبل فقراتها، عشان أعرف أي صفحة تروح لها كل فقرة.", title="ما فيه أرقام صفحات")
    skipped = 0
    if kind == "range":
        lo, hi = sorted((int(a or 1), int(b or 1)))
        skipped = sum(1 for k in parsed if not lo <= k <= hi)
        parsed = {k: v for k, v in parsed.items() if lo <= k <= hi}
        if not parsed:
            raise gr.Error(f"ما فيه في النص أي صفحة بين {lo} و{hi}.", title="النطاق فاضي")
    done, missing, touched = apply_parsed(pid, did, cur, parsed, "لصق ترجمة جاهزة", "page" if how == "page" else "file")
    msg = f"✅ لصقت **{done}** فقرة في **{len(touched)}** صفحة." + (f" (تجاهلت {skipped} صفحة خارج النطاق)" if skipped else "")
    if missing:
        msg += "\n\n⚠ ما لقيت مكان لـ: " + "، ".join(missing[:30]) + (" …" if len(missing) > 30 else "")
    toast(f"✅ لصقت {done} فقرة في {len(touched)} صفحة.", warn=False)
    out = view(pid, did, cur, 0)
    out.update(R(ib_msg=msg))
    return out


@safe
def import_text(pid, did, cur, grp, mode, text, *ars):
    """Puts a ready translation (numbered paragraphs, from a chat) into the paragraphs: each number = the paragraph with that number on the page."""
    guard()
    need(pid)
    parsed = parse_pasted(text)
    if not parsed:
        raise gr.Error("ما لقيت فقرات مرقّمة. اكتب كل فقرة بسطر يبدأ برقمها مثل: 1) النص ... ويمكن تفصل الصفحات بسطر «=== صفحة 5 ===».", title="لصق ترجمة")
    if mode == "blank":                       # no link with the file: the paragraphs go to a NEW white page after this one
        paras = [t for page in parsed.values() for _, t in sorted(page.items()) if t]
        with manual._lock:
            d = manual.load_draft(pid, did)
            manual.plan_insert(d, int(cur), {"k": "t", "paras": paras}, "after")
            manual.save_draft(pid, d)
        toast(f"✅ أضفت صفحة بيضاء بعد هذي الصفحة فيها {len(paras)} فقرة.")
        return view(pid, did, int(cur) + 1, 0)
    autosave(pid, did, cur, grp, ars)
    done, missing, _ = apply_parsed(pid, did, cur, parsed, "لصق ترجمة جاهزة", "page" if mode == "page" else "file")
    toast(f"✅ لصقت {done} فقرة." + (f" ما لقيت: {'، '.join(missing[:8])}" if missing else ""), warn=bool(missing))
    return view(pid, did, cur, 0)


def _same(ars, cur):
    """True when the boxes on screen are the ones of page `cur` (so no page change is half way)."""
    t = ars[0] if ars and isinstance(ars[0], str) else ""
    return t.startswith("tok|") and t.split("|")[3:4] == [str(int(cur))]


@safe
def show(pid, did, cur, grp, *ars):
    """Step 2: the paragraphs and panels of the page we moved to (or the page we are on, after a long job). What is typed in the boxes now is saved
    first, to the page those boxes belong to, so redrawing can never throw a typed word away."""
    if pid and ars:
        autosave(pid, did, cur, grp, ars)
    return view(pid, did, cur, grp if ars and _same(ars, cur) else 0)


def auto_preview(pid, did, pos):
    """The picture of the page we just moved to, so translating and checking never needs an extra click."""
    from .h_output import preview_png
    try:
        png, _, text = preview_png(pid, did, pos)
        return R(pv_img=png, pv_info=text)
    except Exception as e:
        return R(pv_info=f"تعذرت المعاينة: {e}")


def pv_now(pid, did, cur, grp=0):
    """Second step after any action: draws the page we are on (also pages with no text at all)."""
    if not pid or not did:
        return gr.update(), gr.update()
    try:
        from .h_output import preview_png
        png, _, text = preview_png(pid, did, int(cur or 0))
        return png, text
    except Exception as e:
        return gr.update(), f"تعذرت المعاينة: {e}"


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
def blur(pid, did, cur, grp, tok, text, i):
    if not pid:
        return R(saved="")
    n = autosave(pid, did, cur, grp, [tok] + [None] * i + [text])
    return R(saved=f"💾 حُفظ تلقائياً {time.strftime('%H:%M:%S')}" if n else "")


@safe
def number_lines(pid, did, cur, grp, tok, text, i):
    """Saves the numbered text; the box is redrawn by the step that follows (show), so it can never land on another page."""
    guard()
    need(pid)
    new = manual_ai.number_lines(text)
    autosave(pid, did, cur, grp, [tok] + [None] * i + [new])
    toast("🔢 رُقّمت الأسطر.")


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
        png = builder.crop_png(src, u["page"], u["bbox"], mask=mask)
        if ocr_local.available():                                   # first the local reader: no AI, no invented words
            txt = ocr_local.read_image(png)
            if txt:
                return it["uid"], txt
        return it["uid"], manual_ai.read_image(png, hint)          # nothing installed / nothing recognised: the AI
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
