"""HTML fragments for the live dashboard (job cards, live panel, key states, event log)."""
import html, re, time
from . import jobs
from .pool import POOL, clock, human, kname, ltr
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
            extra = f" · {ltr(lv.get('u_done', 0))} من {ltr(lv['u_total'])} فقرة"
        out.append(
            f"<div class='job'><div class='jhead'><b>{esc(m['name'])}</b>"
            f"<span class='chip st-{esc(st)}'>{STATUS_AR.get(st, st)}</span></div>{bar(m.get('pct', 0))}"
            f"<div class='jmeta'>{esc(m.get('stage', ''))} · {ltr(str(m.get('pct', 0)) + '%')}{extra}"
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


ROLE_AR = {"both": "ترجمة وتدقيق", "translate": "ترجمة فقط", "edit": "تدقيق فقط"}


def _dur(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        pass
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m(?!s))?(?:(\d+(?:\.\d+)?)s)?", str(v).strip())
    if m and any(m.groups()):
        h, mi, sec = (float(x) if x else 0.0 for x in m.groups())
        return h * 3600 + mi * 60 + sec
    return None


def _num(v):
    try:
        return ltr(f"{int(float(v)):,}")
    except (TypeError, ValueError):
        return esc(v)


def limits_html(k):
    """Remaining allowance: the service's own numbers when it sends them, otherwise our own counters."""
    L = POOL.limits(k)
    lines, groups = [], {}
    for h, v in L["rl"].items():
        m = re.match(r"x-ratelimit-(remaining|limit|reset)-(requests|tokens)(?:-(\w+))?$", h)
        if m:
            groups.setdefault((m.group(2), m.group(3) or ""), {})[m.group(1)] = v
    names, sufs = {"requests": "طلبات", "tokens": "توكنات"}, {"day": " اليوم", "minute": " في الدقيقة", "hour": " في الساعة", "": ""}
    for (what, suf), d in groups.items():
        t = f"{names[what]}{sufs.get(suf, ' (' + suf + ')')}: متبقي {_num(d.get('remaining'))}"
        if "limit" in d:
            t += f" من {_num(d['limit'])}"
        if _dur(d.get("reset")) is not None:
            t += f"، يتجدد بعد {human(_dur(d['reset']))}"
        lines.append(t)
    rpm = k.get("rpm")
    lines.append(f"آخر دقيقة: {ltr(L['min_req'])} طلب" + (f" (وتيرتك المحددة {ltr(rpm)} في الدقيقة)" if rpm else ""))
    lines.append(f"آخر 24 ساعة منذ تشغيل البرنامج: {ltr(L['day_req'])} طلب · {ltr(format(L['day_tok'], ','))} توكن")
    if k.get("daily_requests"):
        lines.append(f"المتبقي من حدك اليومي: {ltr(max(0, k['daily_requests'] - L['day_req']))} طلب")
    if k.get("daily_tokens"):
        lines.append(f"المتبقي من حدك اليومي: {ltr(format(max(0, k['daily_tokens'] - L['day_tok']), ','))} توكن")
    if not groups and not k.get("daily_requests") and not k.get("daily_tokens"):
        lines.append("هذه الخدمة لا تعلن المتبقي، فالأرقام أعلاه عدّاد البرنامج فقط")
    return "<br>".join(esc(x).replace("\u2066", "\u2066") for x in lines)


def keys_html():
    rows = []
    for s in POOL.status():
        k = s["k"]
        paid = " · مدفوع" if k.get("paid") else ""
        rows.append(
            f"<tr><td><b>{esc(kname(k))}</b><div class='sub'>{esc(k.get('model') or 'نموذج تلقائي')} · "
            f"{esc(urlparse(k.get('base') or PROVIDERS[k['provider']]['base']).netloc)} · {esc(k['id'])}{paid}</div></td>"
            f"<td><span class='chip k-{s['css']}'>{esc(s['state'])}</span><div class='sub'>{ROLE_AR.get(k.get('role', 'both'), '')}</div></td>"
            f"<td class='lim'>{limits_html(k)}</td>"
            f"<td>{ltr(s['ok'])}</td><td>{ltr(format(s['tin'], ','))} / {ltr(format(s['tout'], ','))}</td></tr>")
    if not rows:
        return "<div class='empty'>ما أضفت أي مفتاح بعد.</div>"
    return ("<div class='tbl'><table><thead><tr><th>المفتاح والنموذج</th><th>الحالة والاستخدام</th><th>المتبقي وموعد التجديد</th><th>طلبات ناجحة</th>"
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
        why = "".join(f"<li><b>{esc(kname(s['k']))}</b>: {esc(s['state'])}</li>" for s in POOL.status() if s["css"] == "wait")
        long_hint = ("<p>لو ما استخدمت هذي المفاتيح قبل، فغالباً الخدمة هي اللي ردّت بأن حصة هذا النموذج صغيرة أو منتهية. "
                     "اقرأ «رد الخدمة» أعلاه، ثم أوقف الملف وجرّب «اختيار النموذج تلقائياً» أو أضف مفتاحاً آخر من تبويب المفاتيح.</p>"
                     if POOL.waiting_until - now > 3600 else "")
        wait_banner = (f"<div class='warnbox'>⏳ كل المفاتيح وصلت حدها. يكمل تلقائياً الساعة "
                       f"<b>{clock(POOL.waiting_until)}</b> (بعد {human(POOL.waiting_until - now)}). لا تسكّر النافذة السوداء."
                       f"<ul>{why}</ul>{long_hint}</div>")
    tiles = _tile("النسبة الكلية", ltr(f"{m.get('pct', 0)}%"), esc(m.get("stage", "")))
    if lv.get("u_total"):
        tiles += _tile("الفقرات", ltr(f"{lv.get('u_done', 0)} / {lv['u_total']}"), "تمت ترجمتها")
        tiles += _tile(f"{'الصفحات' if word == 'صفحة' else 'الفصول'}", ltr(f"{lv.get('p_done', 0)} / {lv.get('p_total', 0)}"),
                       f"{word}ات مكتملة" if word == "صفحة" else "فصول مكتملة")
    if lv.get("b_total"):
        tiles += _tile("دفعات التدقيق", ltr(f"{lv.get('b_done', 0)} / {lv['b_total']}"), "دفعة تمت مراجعتها")
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


def quality_html(jid):
    """The honest report: how much is missing, how much looks wrong, and which key produced the bad parts."""
    from . import quality
    if not jid:
        return "<div class='empty'>اختر ملفاً لتشوف تقرير جودته.</div>"
    meta, units = jobs.load(jid)
    if not meta or not units:
        return "<div class='empty'>ما فيه بيانات بعد.</div>"
    r = quality.report(units)
    if not r["total"]:
        return "<div class='empty'>الملف ما فيه نص قابل للترجمة.</div>"
    pct_bad = 100 * r["flagged"] / max(r["total"] - r["missing"], 1)
    verdict = ("<div class='okbox'>✓ ما رصد البرنامج مشاكل ظاهرة. هذا لا يعني أن الأسلوب ممتاز، راجع عينة بنفسك.</div>"
               if not r["missing"] and not r["flagged"] else
               f"<div class='warnbox'>⚠ {'فيه فقرات بلا ترجمة وبقيت بنصها الأصلي. ' if r['missing'] else ''}"
               f"{'فيه فقرات رُصدت فيها مشاكل. ' if r['flagged'] else ''}افتح «عرض المشبوهة فقط» أدناه وأصلحها قبل التصدير.</div>")
    tiles = (_tile("فقرات بلا ترجمة", ltr(r["missing"]), "تبقى بالأصل") + _tile("فقرات فيها مشاكل", f"{ltr(r['flagged'])} ({ltr(round(pct_bad))}%)", "كلمات أجنبية، رموز، نقص")
             + _tile("طول الترجمة نسبة للأصل", ltr(f"{r['ratio']:.2f}"), "العربي غالباً بين 0.7 و 1.2 من الإنجليزي"))
    rows = "".join(f"<tr><td>{esc(n)}</td><td>{ltr(a)}</td><td>{ltr(b)} ({ltr(round(100 * b / max(a, 1)))}%)</td></tr>"
                   for n, (a, b) in sorted(r["by"].items(), key=lambda x: -x[1][1] / max(x[1][0], 1)))
    pages = "، ".join(f"{ltr(p)} ({ltr(c)})" for p, c in r["bad_pages"]) or "لا يوجد"
    return (verdict + f"<div class='tiles'>{tiles}</div>"
            "<div class='tbl'><table><thead><tr><th>المفتاح الذي ترجم</th><th>فقرات</th><th>فيها مشاكل</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div><p class='hint'>أكثر الصفحات مشاكل (عدد الفقرات): {pages}</p>")
