"""The «الصفحات» tab: range, delete, move, swap, add or replace a page. Every operation names the page NUMBER explicitly."""
import gradio as gr
from core import manual
from ui.common import guard, safe
from .data import label, need, path_of
from .h_output import preview_png
from .reg import R
from .view import view

OPS = [("أضيفها بعد الصفحة رقم", "after"), ("أضيفها قبل الصفحة رقم", "before"), ("أستبدل بها الصفحة رقم (القديمة تُحذف)", "replace")]


def _n(d, target):
    eff = manual.effective_plan(d)
    t = int(target or 0)
    if not 1 <= t <= len(eff):
        raise gr.Error(f"اكتب رقم صفحة بين 1 و {len(eff)} (الأرقام كما في الجدول)", title="رقم الصفحة غير صحيح")
    return t - 1, eff


def _show(pid, did, pos, msg):
    """The editor view at `pos` + a fresh picture of that page, so the change is visible at once."""
    out = view(pid, did, pos, 0, msg)
    try:
        png, _, text = preview_png(pid, did, pos)
        out.update(R(pg_prev=png, pg_prev_info=text))
    except Exception:
        pass
    return out


@safe
def set_range(pid, did, cur, grp, on, a, b, outside):
    guard()
    need(pid)
    meta, units = manual.load(pid)
    a, b = int(a or 1), int(b or 1)
    if on and not (1 <= a <= b <= meta["pages"]):
        raise gr.Error(f"النطاق لازم يكون بين 1 و {meta['pages']} وبداية النطاق قبل نهايته", title="نطاق غير صحيح")
    with manual._lock:
        d = manual.load_draft(pid, did)
        manual.set_range(d, on, a, b, outside)
        manual.save_draft(pid, d)
    return view(pid, did, cur, grp, "✅ حُفظ نطاق الترجمة." if on else "✅ أُلغي النطاق: كل الصفحات تُترجم.")


@safe
def ask_delete(pid, did, target):
    need(pid)
    d = manual.load_draft(pid, did)
    i, eff = _n(d, target)
    return gr.update(visible=True), f"هل تريد حذف الصفحة {i + 1} ({label(eff[i])}) من الملف النهائي؟ تقدر تتراجع بعدها."


@safe
def delete(pid, did, target):
    guard()
    with manual._lock:
        d = manual.load_draft(pid, did)
        i, eff = _n(d, target)
        manual.plan_delete(d, i)
        manual.save_draft(pid, d)
    return view(pid, did, min(i, max(len(manual.effective_plan(d)) - 1, 0)), 0, f"🗑 حُذفت الصفحة {i + 1}. تقدر تتراجع.")


@safe
def move(pid, did, target, to):
    guard()
    need(pid)
    with manual._lock:
        d = manual.load_draft(pid, did)
        i, eff = _n(d, target)
        j, _ = _n(d, to)
        if not manual.plan_move(d, i, j):
            raise gr.Error("اكتب موضعاً مختلفاً عن مكان الصفحة الحالي", title="نفس الموضع")
        manual.save_draft(pid, d)
    return _show(pid, did, j, f"↕ نُقلت الصفحة {i + 1} إلى الموضع {j + 1}.")


@safe
def swap(pid, did, target, other):
    guard()
    need(pid)
    with manual._lock:
        d = manual.load_draft(pid, did)
        i, eff = _n(d, target)
        j, _ = _n(d, other)
        if not manual.plan_swap(d, i, j):
            raise gr.Error("اكتب رقم صفحة مختلفاً", title="نفس الصفحة")
        manual.save_draft(pid, d)
    return _show(pid, did, i, f"⇄ بُدّلت الصفحة {i + 1} مع الصفحة {j + 1}.")


@safe
def insert(pid, did, op, target, file, fpage, sure, blank):
    guard()
    need(pid)
    if not blank and not file:
        raise gr.Error("ارفع صورة أو ملف PDF من الخطوة ٢، أو اضغط «صفحة فارغة»", title="ما رفعت ملفاً")
    if op == "replace" and not sure:
        raise gr.Error("الاستبدال يحذف الصفحة القديمة. علّم خانة «أؤكد حذف الصفحة القديمة» ثم اضغط من جديد.", title="أكّد الاستبدال")
    with manual._lock:
        d = manual.load_draft(pid, did)
        i, eff = _n(d, target)
        entry = {"k": "b"}
        if not blank:
            entry = manual.import_page(pid, path_of(file), fpage, manual.page_size(pid, d, i))
        manual.plan_insert(d, i, entry, "before" if op == "before" else "after", replace=(op == "replace"))
        manual.save_draft(pid, d)
    pos = i if op in ("before", "replace") else i + 1
    what = {"before": "أُضيفت قبل", "after": "أُضيفت بعد", "replace": "استُبدلت بها"}[op]
    return _show(pid, did, pos, f"✅ {what} الصفحة {i + 1}. هذي الصفحة الجديدة (رقم {pos + 1}). تقدر تتراجع.")


@safe
def peek(pid, did, target):
    need(pid)
    d = manual.load_draft(pid, did)
    i, _ = _n(d, target)
    png, _, text = preview_png(pid, did, i)
    return R(pg_prev=png, pg_prev_info=text)
