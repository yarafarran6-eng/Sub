"""Files, drafts, undo and reset: the «الملف» tab and the bar that is always visible."""
import gradio as gr
from core import manual, textcheck
from ui.common import guard, safe, toast
from .data import need, path_of
from .view import view, empty


def _pv(out, pid, did, pos):
    """Every time the page we look at changes (open, switch draft, undo, reset) its picture appears too, no click needed."""
    return out    # the picture is drawn by a separate step (screen.py), so this answer is instant


@safe
def new_file(file, progress=gr.Progress()):
    guard()
    if not file:
        raise gr.Error("ارفع ملف PDF أولاً", title="ما فيه ملف")
    path = path_of(file)
    if not path.lower().endswith(".pdf"):
        raise gr.Error("الترجمة اليدوية تدعم ملفات PDF فقط", title="صيغة غير مدعومة")
    pid = manual.create(path, lambda i, n: progress(i / max(n, 1), desc=f"يستخرج النص: صفحة {i} من {n}"))
    meta, units = manual.load(pid)
    did = manual.ensure_draft(pid)
    note = f"✅ استُخرج نص {meta['pages']} صفحة في {meta['extract_seconds']} ثانية. أُنشئت «مسودة 1» وتُحفظ تلقائياً."
    if meta["no_text_pages"]:
        note += f" {len(meta['no_text_pages'])} صفحة بدون نص قابل للقراءة."
    bad = textcheck.share([u["text"] for u in units if u.get("translate")])
    if bad > 0.15:
        note += f" ⚠ {round(bad * 100)}% من فقرات الملف نصها غير مقروء (ترميز الخط). اقرأها من صورة الصفحة الأصلية أو بزر «👁 اقرأ من الصورة»."
    return _pv(view(pid, did, 0, 0, note), pid, did, 0)


@safe
def open_sel(sel):
    """One list for everything: manual projects and finished automatic translations."""
    guard()
    if not sel:
        raise gr.Error("اختر ملفاً من القائمة", title="ما اخترت ملفاً")
    kind, _, key = sel.partition(":")
    if kind == "j":
        try:
            pid, n = manual.import_from_job(key)
        except ValueError as e:
            raise gr.Error(str(e), title="تعذّر الفتح")
        did = manual.ensure_draft(pid)
        return _pv(view(pid, did, 0, 0, f"✅ فُتح الملف للتعديل مع {n} فقرة مترجمة آلياً." if n else "📂 فُتح الملف."), pid, did, 0)
    did = manual.ensure_draft(key)
    d = manual.load_draft(key, did)
    return _pv(view(key, did, d.get("page", 0), d.get("grp", 0), "📂 فُتح الملف من آخر مكان وقفت عنده."), key, did, d.get("page", 0))


@safe
def ask_delete_file(pid, sel):
    if not sel or not sel.startswith("p:"):
        raise gr.Error("اختر ملفاً يدوياً من القائمة (الترجمات الآلية تُحذف من تبويب الترجمة الآلية)", title="ما يمكن حذفه من هنا")
    return gr.update(visible=True), "هل تريد حذف هذا الملف بكل مسوداته نهائياً؟ ما يمكن التراجع."


@safe
def delete_file(pid, did, cur, grp, sel):
    guard()
    target = sel.split(":", 1)[1]
    manual.delete(target)
    toast("🗑 حُذف الملف.")
    return empty() if target == pid else view(pid, did, cur, grp)


@safe
def switch_draft(pid, new_did):
    guard()
    need(pid)
    if not new_did:
        raise gr.Error("اختر مسودة", title="ما اخترت مسودة")
    manual.set_last_draft(pid, new_did)
    d = manual.load_draft(pid, new_did)
    return _pv(view(pid, new_did, d.get("page", 0), d.get("grp", 0), f"📝 المسودة: {d['name']}"), pid, new_did, d.get("page", 0))


@safe
def new_draft(pid):
    guard()
    need(pid)
    return _pv(view(pid, manual.create_draft(pid), 0, 0, "✅ مسودة جديدة فاضية. المسودة السابقة محفوظة."), pid, manual.create_draft(pid), 0)


@safe
def copy_draft(pid, did):
    guard()
    need(pid)
    new = manual.create_draft(pid, copy_from=did)
    d = manual.load_draft(pid, new)
    return _pv(view(pid, new, d.get("page", 0), d.get("grp", 0), "✅ نُسخت المسودة الحالية بكل ما فيها."), pid, new, d.get("page", 0))


@safe
def rename_draft(pid, did, name):
    guard()
    need(pid)
    if not (name or "").strip():
        raise gr.Error("اكتب الاسم الجديد", title="الاسم فارغ")
    manual.rename_draft(pid, did, name)
    d = manual.load_draft(pid, did)
    return view(pid, did, d.get("page", 0), d.get("grp", 0), "✏ تم تغيير الاسم.")


@safe
def ask_delete_draft(pid):
    need(pid)
    return gr.update(visible=True), "هل تريد حذف هذي المسودة نهائياً؟ ما يمكن التراجع."


@safe
def delete_draft(pid, did):
    guard()
    manual.save_draft(pid, manual.load_draft(pid, did))
    new = manual.delete_draft(pid, did) or manual.create_draft(pid)
    d = manual.load_draft(pid, new)
    return _pv(view(pid, new, d.get("page", 0), d.get("grp", 0), "🗑 حُذفت المسودة."), pid, new, d.get("page", 0))


@safe
def undo(pid, did, cur, grp):
    guard()
    need(pid)
    with manual._lock:
        d = manual.load_draft(pid, did)
        label = manual.undo(d)
        manual.save_draft(pid, d)
    return _pv(view(pid, did, cur, grp, f"↩ تراجعت عن: {label}" if label else "⚠ ما فيه شي أتراجع عنه."), pid, did, cur)


@safe
def ask_reset_all(pid):
    need(pid)
    return gr.update(visible=True), "⚠ هل أنت متأكد؟ ستفقد **كل التعديلات التي تمت على الملف**: كل الترجمات والتنسيقات والصفحات اللي نقلتها أو حذفتها أو استبدلتها بصور. المسودة ترجع فاضية مثل أول مرة. تقدر تتراجع بزر «تراجع عن آخر تغيير (أي صفحة)» مباشرة بعد التنفيذ، لكن لا تعتمد عليها بعد ما تكمل شغل."


@safe
def reset_all(pid, did):
    guard()
    with manual._lock:
        d = manual.load_draft(pid, did)
        manual.reset_all(d)
        manual.save_draft(pid, d)
    return _pv(view(pid, did, 0, 0, "⟲ رجعت المسودة إلى البداية. تقدر تتراجع."), pid, did, 0)


# ---- the same two actions for the OPEN page only
def _page_of(pid, did, cur):
    from .data import orig_page
    d = manual.load_draft(pid, did)
    p = orig_page(d, cur)
    if p is None:
        raise gr.Error("هذي صفحة مضافة (صورة أو فارغة) وما لها نص أصلي. استخدم «تراجع عن آخر تغيير» العام.", title="صفحة مضافة")
    return p


@safe
def undo_page(pid, did, cur, grp):
    guard()
    need(pid)
    with manual._lock:
        page = _page_of(pid, did, cur)
        _, units = manual.load(pid)
        d = manual.load_draft(pid, did)
        label = manual.undo_page(d, units, page)
        manual.save_draft(pid, d)
    return _pv(view(pid, did, cur, grp, f"↩ تراجعت عن «{label}» في هذه الصفحة فقط." if label else "⚠ ما فيه تغيير في هذه الصفحة أتراجع عنه."), pid, did, cur)


@safe
def ask_reset_page(pid, did, cur):
    need(pid)
    page = _page_of(pid, did, cur)
    return gr.update(visible=True), f"⚠ هل أنت متأكد؟ ستفقد **كل التعديلات التي تمت على الصفحة {page + 1}**: ترجمتها وتنسيقها والفقرات اللي أضفتها فيها، وترجع مثل الملف الأصلي. باقي الصفحات ما تتأثر. تقدر تتراجع بزر «تراجع عن آخر تغيير (أي صفحة)» مباشرة بعد التنفيذ."


@safe
def reset_page(pid, did, cur, grp):
    guard()
    need(pid)
    with manual._lock:
        page = _page_of(pid, did, cur)
        _, units = manual.load(pid)
        d = manual.load_draft(pid, did)
        changed = manual.reset_page_to_original(d, units, page)
        manual.save_draft(pid, d)
    return _pv(view(pid, did, cur, grp, f"⟲ رجعت الصفحة {page + 1} للأصل. تقدر تتراجع." if changed else "هذي الصفحة أصلاً مثل الملف الأصلي، ما فيها تغييرات."), pid, did, cur)
