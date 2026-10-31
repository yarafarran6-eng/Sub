"""HTML fragments for the live dashboard (job cards, live panel, key states, event log)."""
import html, time
from . import jobs
from .pool import POOL, clock, human, kname
from urllib.parse import urlparse
from .keystore import load_keys, PROVIDERS

STATUS_AR = {"queued": "في الطابور", "running": "يعمل", "ready": "جاهزة", "partial": "ناقصة",
             "stopped": "موقوفة", "error": "خطأ"}


def esc(x):
    return html.escape(str(x))


def bar(pct, cls=""):
    return f"<div class='bar {cls}'><i style='width:{max(0, min(100, pct))}%'></i></div>"


def jobs_html():
    js = jobs.list_jobs()
    if not js:
        return "<div class='empty'>ما فيه ملفات بعد. ارفع أول ملف من الأعلى وبيظهر هنا مع شريط التقدم.</div>"
    out = []
    for m in js:
        st = m.get("status", "")
        lv = m.get("live") or {}
        extra = ""
        if lv.get("u_total"):
            extra = f" · {lv.get('u_done', 0)} من {lv['u_total']} فقرة"
        out.append(
            f"<div class='job'><div class='jhead'><b>{esc(m['name'])}</b>"
            f"<span class='chip st-{esc(st)}'>{STATUS_AR.get(st, st)}</span></div>{bar(m.get('pct', 0))}"
            f"<div class='jmeta'>{esc(m.get('stage', ''))} · {m.get('pct', 0)}%{extra}"
            f"<span class='jid'>[{esc(m['id'])}]</span></div>"
            + (f"<div class='jnote'>{esc(m['msg'])}</div>" if m.get("msg") else "") + "</div>")
    return "".join(out)


def _tile(title, value, sub=""):
    return f"<div class='tile'><div class='tt'>{title}</div><div class='tv'>{value}</div><div class='ts'>{sub}</div></div>"


def _eta(lv):
    now = time.time()
    el = now - lv.get("phase_start", now)
    if lv.get("phase") == "translate":
        done = lv.get("u_done", 0) - lv.get("u_done0", 0)
        left = lv.get("u_total", 0) - lv.get("u_done", 0)
    elif lv.get("phase") == "edit":
        done, left = lv.get("b_done", 0), lv.get("b_total", 0) - lv.get("b_done", 0)
    else:
        return el, None
    if done <= 0 or el < 5:
        return el, None
    return el, el * left / done


def keys_html():
    rows = []
    for s in POOL.status():
        k = s["k"]
        paid = " · مدفوع" if k.get("paid") else ""
        rows.append(
            f"<tr><td><b>{esc(kname(k))}</b><div class='sub'>{esc(k.get('model') or 'نموذج تلقائي')} · "
            f"{esc(urlparse(k.get('base') or PROVIDERS[k['provider']]['base']).netloc)} · {esc(k['id'])}{paid}</div></td>"
            f"<td><span class='chip k-{s['css']}'>{esc(s['state'])}</span></td>"
            f"<td>{s['ok']}</td><td>{s['tin']:,} / {s['tout']:,}</td></tr>")
    if not rows:
        return "<div class='empty'>ما أضفت أي مفتاح بعد.</div>"
    return ("<div class='tbl'><table><thead><tr><th>المفتاح والنموذج</th><th>الحالة الآن</th><th>طلبات ناجحة</th>"
            "<th>توكنات (دخل / خرج)</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")


def events_html(n=14):
    ev = list(POOL.events)[-n:][::-1]
    if not ev:
        return "<div class='empty'>لا توجد أحداث بعد.</div>"
    return "<div class='events'>" + "".join(
        f"<div class='ev {lv}'><span>{clock(ts)}</span> {esc(msg)}</div>" for ts, lv, msg in ev) + "</div>"


def monitor_html(jid=None):
    js = jobs.list_jobs()
    m = next((x for x in js if x["id"] == jid), None) if jid else None
    m = m or next((x for x in js if x.get("status") == "running"), None) or (js[0] if js else None)
    if not m:
        return "<div class='empty'>اختر ملفاً أو ارفع ملفاً جديداً ليظهر هنا كل شي يحصل لحظة بلحظة.</div>"
    lv = m.get("live") or {}
    now = time.time()
    el, eta = _eta(lv)
    running = m.get("status") == "running"
    word = lv.get("word", "صفحة")
    wait_banner = ""
    if running and POOL.waiting_until > now:
        wait_banner = (f"<div class='warnbox'>⏳ كل المفاتيح وصلت حدها. يكمل تلقائياً الساعة "
                       f"<b>{clock(POOL.waiting_until)}</b> (بعد {human(POOL.waiting_until - now)}). لا تسكّر النافذة السوداء.</div>")
    tiles = _tile("النسبة الكلية", f"{m.get('pct', 0)}%", esc(m.get("stage", "")))
    if lv.get("u_total"):
        tiles += _tile("الفقرات", f"{lv.get('u_done', 0)} / {lv['u_total']}", "تمت ترجمتها")
        tiles += _tile(f"{'الصفحات' if word == 'صفحة' else 'الفصول'}", f"{lv.get('p_done', 0)} / {lv.get('p_total', 0)}",
                       f"{word}ات مكتملة" if word == "صفحة" else "فصول مكتملة")
    if lv.get("b_total"):
        tiles += _tile("دفعات التدقيق", f"{lv.get('b_done', 0)} / {lv['b_total']}", "دفعة تمت مراجعتها")
    if running and lv.get("phase_start"):
        tiles += _tile("الوقت المنقضي", human(el), "في هذه المرحلة")
        tiles += _tile("المتبقي تقريباً", human(eta) if eta is not None else "يُحسب بعد دقيقة",
                       "تقدير، ويطول عند انتظار الحدود")
    work = ""
    if m.get("msg"):
        work = f"<div class='infobox'>{esc(m['msg'])}</div>"
    return (f"<div class='mon'><div class='mhead'><b>{esc(m['name'])}</b>"
            f"<span class='chip st-{esc(m.get('status', ''))}'>{STATUS_AR.get(m.get('status', ''), '')}</span></div>"
            f"<div class='stage'>{esc(m.get('stage', ''))}</div>"
            f"<div class='what'>{esc(lv.get('label', ''))}</div>{bar(m.get('pct', 0), 'big')}"
            f"{wait_banner}{work}<div class='tiles'>{tiles}</div></div>")
