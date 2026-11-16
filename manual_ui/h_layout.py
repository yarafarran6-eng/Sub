"""Page layout help: even spacing between the paragraphs (no AI) and «move the paragraphs as I say» (AI picks moves, never text)."""
import gradio as gr
from core import builder, layout, manual, priority
from core.pool import NoKeys, call, use_route
from ui.common import guard, safe, toast
from .data import items_now, need, orig_page
from .h_text import _page_obstacles
from .view import view


def _measure(pid, did, cur):
    """Where every paragraph of this page really sits in the output (a tiny throw-away render)."""
    meta, units, d, eff, allit, _ = items_now(pid, did, cur, 0)
    if not eff:
        raise gr.Error("لا توجد صفحات", title="الملف فاضي")
    report, png = {}, manual._dir(pid) / "measure_tmp.png"
    builder.build_plan_pdf(manual.source_path(pid), eff, manual.merged_units(units, d), "ar", None, d.get("font") or None,
                           d["pstyle"], manual._dir(pid), only_pos=int(cur), png=str(png), dpi=16, report=report)
    try:
        png.unlink()
    except OSError:
        pass
    page = report.pop("_page", [595.0, 842.0])
    rows = [(n, it) for n, it in enumerate(allit, 1) if it["uid"] in report and not it["deleted"]]
    return d, rows, report, page


@safe
def auto(pid, did, cur, grp):
    """Even gaps between the paragraphs of this page: plain geometry, no AI, no change to any word."""
    guard()
    need(pid)
    d, rows, report, page = _measure(pid, did, cur)
    obs = _page_obstacles(pid, orig_page(d, cur)) if orig_page(d, cur) is not None else []
    res = layout.auto_spacing([(it["uid"], report[it["uid"]]) for _, it in rows], page[1], obs)
    if not res:
        toast("المسافات بين فقرات هذي الصفحة متساوية أصلاً (أو ما فيه إلا فقرة وحدة).")
        return view(pid, did, cur, grp)
    with manual._lock:
        d = manual.load_draft(pid, did)
        manual.shift_many(d, {u: (0, dy) for u, dy in res.items()}, label="توزيع المسافات بين الفقرات")
        manual.save_draft(pid, d)
    toast(f"✅ وزّعت المسافات بين الفقرات (حرّكت {len(res)} فقرة، والكلام ما تغيّر). تقدر تتراجع بزر «تراجع».")
    return view(pid, did, cur, grp)


@safe
def ask(pid, did, cur, grp, request, model, fb):
    """«Centre them all except 4, move 3 down a little»: the AI answers with moves from a fixed menu; the numbers are computed here."""
    guard()
    need(pid)
    request = (request or "").strip()
    if not request:
        raise gr.Error("اكتب وش تبغى تسوي بالفقرات، مثل: كل الفقرات بالمنتصف أفقياً ما عدا الرابعة، ونزّل الثالثة شوي", title="الطلب فاضي")
    d, rows, report, page = _measure(pid, did, cur)
    if not rows:
        raise gr.Error("ما فيه فقرات مرسومة في هذي الصفحة أحركها. ترجم الفقرات أولاً.", title="لا يوجد ما يتحرك")
    shown = [{"n": n, "text": (it["ar"] or it["en"]), "rect": report[it["uid"]], "size": it["def_size"]} for n, it in rows]
    route = priority.new_route("translate", model or priority.AUTO, bool(fb), max_wait=30)
    try:
        with use_route(route):
            raw = call([{"role": "user", "content": layout.prompt(request, shown, page)}], role="translate", max_tokens=900, temperature=0, task="layout")
    except NoKeys as e:
        raise gr.Error(str(e), title="ما فيه ذكاء اصطناعي متاح الآن")
    nmax = max(n for n, _ in rows)
    ops, note = layout.parse(raw, nmax)
    ops = [dict(o, who=[n for n in o["who"] if n in report_by_n(rows, report)]) for o in ops]
    ops = [o for o in ops if o["who"]]
    if not ops:
        toast(note or "ما طلع من الذكاء الاصطناعي ترتيب أقدر أنفذه. جرّب تصيغ الطلب بشكل ثاني.", warn=True)
        return view(pid, did, cur, grp)
    rects = report_by_n(rows, report)
    offs = {n: (float(d["ustyle"].get(it["uid"], {}).get("dx", 0) or 0), float(d["ustyle"].get(it["uid"], {}).get("dy", 0) or 0)) for n, it in rows}
    moved, aligns = layout.apply_ops(ops, rects, page, offs)
    uid = {n: it["uid"] for n, it in rows}
    with manual._lock:
        d = manual.load_draft(pid, did)
        manual.shift_many(d, {uid[n]: tuple(m) for n, m in moved.items() if abs(m[0]) > 0.05 or abs(m[1]) > 0.05},
                          {uid[n]: a for n, a in aligns.items()}, label="ترتيب الفقرات بالذكاء الاصطناعي")
        manual.save_draft(pid, d)
    toast("✅ " + (note or "رتّبت الفقرات") + " — الكلام ما تغيّر. تقدر تتراجع بزر «تراجع».")
    return view(pid, did, cur, grp)


def report_by_n(rows, report):
    return {n: list(report[it["uid"]]) for n, it in rows}
