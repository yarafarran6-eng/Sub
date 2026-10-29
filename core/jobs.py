"""Job queue: each uploaded folder/file is a job processed in the background and resumable."""
import queue, shutil, threading, time, traceback, uuid
from pathlib import Path
from . import parser, translator, editor, glossary
from .config import JOBS, LOCK, read_json, write_json

_q = queue.Queue()
_stop = set()
_started = False


def _dir(jid):
    return JOBS / jid


def load(jid):
    d = _dir(jid)
    meta = read_json(d / "meta.json", None)
    units = read_json(d / "units.json", [])
    return meta, units


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
                    "status": "queued", "msg": "", "ctx": "", "created": int(time.time()), "edited": False})
    enqueue(jid)
    return jid


def enqueue(jid):
    _stop.discard(jid)
    set_state(jid, status="queued", stage="في الطابور", msg="")
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


def _process(jid):
    meta, units = load(jid)
    d = _dir(jid)
    stop = lambda: jid in _stop
    try:
        set_state(jid, status="running", stage="قراءة الملف", pct=2)
        if not units:
            kind, units, info = parser.parse_any(str(next(d.glob("source.*"))), str(d / "img"))
            save_units(jid, units)
            note = ""
            if info.get("scanned_pages"):
                note = f"تنبيه: صفحات بدون نص (ممسوحة ضوئياً) ولن تُترجم: {info['scanned_pages'][:10]}"
            set_state(jid, kind=kind, pages=info["pages"], msg=note)
        meta, _ = load(jid)
        if not meta.get("ctx"):
            set_state(jid, stage="بناء بطاقة السياق والمسرد", pct=8)
            ctx = glossary.build_context(units, meta["src"], meta["tgt"], meta["style"])
            set_state(jid, ctx=ctx)
            meta["ctx"] = ctx

        def prog_t(done, total):
            set_state(jid, stage="الترجمة المتوازية", pct=10 + int(70 * done / max(total, 1)))
            if done % 5 == 0:
                save_units(jid, units)

        set_state(jid, stage="الترجمة المتوازية", pct=10)
        left = translator.translate_all(units, meta["src"], meta["tgt"], meta["ctx"], meta["style"],
                                        meta["golden"], prog_t, stop)
        save_units(jid, units)
        if stop():
            set_state(jid, status="stopped", stage="أُوقفت", msg="أُوقفت يدوياً، اضغط استكمال")
            return
        if left:
            set_state(jid, status="partial", stage="ناقصة",
                      msg=f"{left} فقرة لم تُترجم (حد المزودين أو خطأ). اضغط استكمال لاحقاً.")
            return
        if not meta.get("edited"):
            def prog_e(done, total):
                set_state(jid, stage="التدقيق الجراحي", pct=80 + int(18 * done / max(total, 1)))
            set_state(jid, stage="التدقيق الجراحي", pct=80)
            patches = editor.edit_pass(units, meta["src"], meta["tgt"], meta["ctx"], meta["style"],
                                       meta["sensitivity"], prog_e, stop)
            save_units(jid, units)
            write_json(d / "patches.json", patches)
            set_state(jid, edited=True, patches=len(patches))
        set_state(jid, status="ready", stage="جاهزة للمعاينة", pct=100, msg=meta.get("msg", ""))
    except Exception as e:
        traceback.print_exc()
        set_state(jid, status="error", stage="خطأ", msg=str(e)[:300])


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
