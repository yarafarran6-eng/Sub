"""Job queue: each uploaded file is a job processed in the background; resumable, with live statistics."""
import queue, shutil, threading, time, traceback, uuid
from pathlib import Path
from . import parser, translator, editor, glossary
from .config import JOBS, LOCK, read_json, write_json
from .pool import POOL, NoKeys

_q = queue.Queue()
_stop = set()
_started = False


def _dir(jid):
    return JOBS / jid


def load(jid):
    d = _dir(jid)
    return read_json(d / "meta.json", None), read_json(d / "units.json", [])


def save_meta(jid, meta):
    write_json(_dir(jid) / "meta.json", meta)


def save_units(jid, units):
    write_json(_dir(jid) / "units.json", units)


def set_state(jid, **kw):
    with LOCK:
        meta = read_json(_dir(jid) / "meta.json", {})
        meta.update(kw)
        meta["updated"] = int(time.time())
        save_meta(jid, meta)


def create(path, src, tgt, style="", golden="", sensitivity="medium"):
    jid = uuid.uuid4().hex[:8]
    d = _dir(jid)
    d.mkdir(parents=True)
    p = Path(path)
    shutil.copy(p, d / ("source" + p.suffix.lower()))
    save_meta(jid, {"id": jid, "name": p.name, "ext": p.suffix.lower(), "src": src, "tgt": tgt, "style": style,
                    "golden": golden, "sensitivity": sensitivity, "stage": "في الطابور", "pct": 0,
                    "status": "queued", "msg": "", "ctx": "", "created": int(time.time()), "edited": False,
                    "live": {"phase": "queued", "label": "ينتظر دوره في الطابور"}})
    enqueue(jid)
    return jid


def enqueue(jid):
    _stop.discard(jid)
    set_state(jid, status="queued", stage="في الطابور", msg="",
              live={"phase": "queued", "label": "ينتظر دوره في الطابور"})
    _q.put(jid)
    ensure_worker()


def cancel(jid):
    _stop.add(jid)


def list_jobs():
    out = []
    for d in sorted(JOBS.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        m = read_json(d / "meta.json", None)
        if m:
            out.append(m)
    return out


def delete(jid):
    shutil.rmtree(_dir(jid), ignore_errors=True)


def recover():
    """Jobs that were running when the program was closed are marked stopped so they can be resumed."""
    for m in list_jobs():
        if m.get("status") in ("running", "queued"):
            set_state(m["id"], status="stopped", stage="توقفت",
                      msg="توقفت لأن البرنامج أُغلق. اضغط استكمال لتكمل من حيث وقفت.",
                      live={"phase": "stopped", "label": "متوقفة"})


def page_stats(units):
    pages = {}
    for u in units:
        if u.get("translate"):
            t = pages.setdefault(u["page"], [0, 0])
            t[0] += 1
            t[1] += 1 if u.get("tr") else 0
    return len(pages), sum(1 for t, d in pages.values() if d >= t)


def _process(jid):
    meta, units = load(jid)
    d = _dir(jid)
    stop = lambda: jid in _stop
    last_push = [0.0]

    def push(force=False, **kw):
        if force or time.time() - last_push[0] > 0.8:
            last_push[0] = time.time()
            set_state(jid, **kw)

    try:
        POOL.log(f"▶ بدأت معالجة «{meta['name']}»")
        live = {"phase": "parse", "label": "يقرأ الملف ويستخرج الفقرات", "phase_start": time.time()}
        set_state(jid, status="running", stage="قراءة الملف", pct=1, live=live, msg="")
        if not units:
            def on_page(i, n):
                live.update(label=f"يقرأ الملف: الصفحة {i} من {n}", p_done=i, p_total=n)
                push(stage="قراءة الملف", pct=1 + int(4 * i / max(n, 1)), live=live)
            kind, units, info = parser.parse_any(str(next(d.glob("source.*"))), str(d / "img"), on_page)
            save_units(jid, units)
            note = ""
            if info.get("scanned_pages"):
                note = f"تنبيه: صفحات بدون نص (ممسوحة ضوئياً) ولن تُترجم: {info['scanned_pages'][:10]}"
            set_state(jid, kind=kind, pages=info["pages"], msg=note)
        meta, _ = load(jid)
        kind_word = "صفحة" if meta.get("kind") == "pdf" else "فصل"
        u_total = sum(1 for u in units if u.get("translate"))

        if not meta.get("ctx"):
            live = {"phase": "context", "phase_start": time.time(),
                    "label": "يرسل عينات من النص لنموذج الذكاء لاستخراج أسماء الشخصيات وجنسها والمصطلحات والنبرة"}
            set_state(jid, stage="بناء بطاقة السياق", pct=6, live=live)
            ctx = glossary.build_context(units, meta["src"], meta["tgt"], meta["style"])
            set_state(jid, ctx=ctx)
            meta["ctx"] = ctx

        u_done0 = sum(1 for u in units if u.get("translate") and u.get("tr"))
        p_total, p_done = page_stats(units)
        resumed = u_done0 > 0
        live = {"phase": "translate", "phase_start": time.time(), "u_total": u_total, "u_done": u_done0,
                "u_done0": u_done0, "p_total": p_total, "p_done": p_done, "word": kind_word,
                "label": ("استكمال الترجمة: تمت سابقاً ترجمة " + f"{u_done0} من {u_total} فقرة" if resumed
                          else "يقسّم النص إلى أجزاء ويترجمها بالتوازي على كل المفاتيح"),
                "chunk_done": 0, "chunk_total": 0}
        pct = 10 + int(70 * u_done0 / max(u_total, 1))
        set_state(jid, stage="الترجمة المتوازية", pct=pct, live=live)

        def prog_t(n_new, c_done, c_total):
            live["u_done"] += n_new
            live["chunk_done"], live["chunk_total"] = c_done, c_total
            live["p_total"], live["p_done"] = page_stats(units)
            live["label"] = f"يترجم الأجزاء بالتوازي: انتهى {c_done} من {c_total} جزء في هذه الجولة"
            if c_done % 3 == 0:
                save_units(jid, units)
            push(stage="الترجمة المتوازية", pct=10 + int(70 * live["u_done"] / max(u_total, 1)), live=live)

        left = translator.translate_all(units, meta["src"], meta["tgt"], meta["ctx"], meta["style"],
                                        meta["golden"], prog_t, stop)
        save_units(jid, units)
        live["p_total"], live["p_done"] = page_stats(units)
        if stop():
            set_state(jid, status="stopped", stage="أُوقفت", live={**live, "label": "أوقفتها يدوياً"},
                      msg="أُوقفت يدوياً. اضغط استكمال لتكمل من حيث وقفت.")
            POOL.log("⏹ أُوقفت المهمة يدوياً")
            return
        if left:
            err = next((u.get("error") for u in units if u.get("translate") and not u.get("tr") and u.get("error")), "")
            set_state(jid, status="partial", stage="ناقصة", live={**live, "label": "توقفت قبل الاكتمال"},
                      msg=f"بقي {left} فقرة بدون ترجمة بسبب خطأ غير حدّ الاستخدام: {err or 'غير معروف'}. اضغط استكمال لإعادة المحاولة.")
            POOL.log(f"⚠ بقي {left} فقرة بدون ترجمة: {err[:100]}", "warn")
            return
        if not meta.get("edited"):
            live = {"phase": "edit", "phase_start": time.time(), "b_done": 0, "b_total": 0,
                    "u_total": u_total, "u_done": u_total, "p_total": p_total, "p_done": p_total, "word": kind_word,
                    "label": "المدقق يقرأ الأصل مع الترجمة ويصحح الفقرات الضعيفة فقط"}
            set_state(jid, stage="التدقيق الجراحي", pct=80, live=live)

            def prog_e(done, total):
                live.update(b_done=done, b_total=total,
                            label=f"المدقق راجع {done} من {total} دفعة")
                push(stage="التدقيق الجراحي", pct=80 + int(18 * done / max(total, 1)), live=live)

            patches = editor.edit_pass(units, meta["src"], meta["tgt"], meta["ctx"], meta["style"],
                                       meta["sensitivity"], prog_e, stop)
            save_units(jid, units)
            write_json(d / "patches.json", patches)
            set_state(jid, edited=True, patches=len(patches))
            if stop():
                set_state(jid, status="stopped", stage="أُوقفت", msg="أُوقفت أثناء التدقيق. اضغط استكمال.")
                return
        live = {"phase": "done", "label": "انتهت الترجمة والتدقيق", "u_total": u_total, "u_done": u_total,
                "p_total": p_total, "p_done": p_total, "word": kind_word}
        set_state(jid, status="ready", stage="جاهزة للمعاينة", pct=100, live=live, msg=meta.get("msg", ""))
        POOL.log(f"✅ انتهت «{meta['name']}»، جاهزة للمعاينة والتصدير")
    except NoKeys as e:
        set_state(jid, status="partial", stage="توقفت: لا مفاتيح صالحة", msg=str(e),
                  live={"phase": "stopped", "label": "لا يوجد مفتاح صالح"})
        POOL.log(f"❌ {e}", "error")
    except Exception as e:
        traceback.print_exc()
        set_state(jid, status="error", stage="خطأ", msg=str(e)[:300], live={"phase": "error", "label": "حدث خطأ"})
        POOL.log(f"❌ خطأ في المعالجة: {str(e)[:150]}", "error")


def _worker():
    while True:
        jid = _q.get()
        if _dir(jid).exists():
            _process(jid)


def ensure_worker():
    global _started
    if not _started:
        _started = True
        threading.Thread(target=_worker, daemon=True).start()
