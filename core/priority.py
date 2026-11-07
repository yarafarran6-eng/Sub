"""The person's priority order of AIs (one list for translating, one for checking), and the "route" a request follows.

A route is a small dict: {"order": [key ids, best first], "only": bool, "max_wait": seconds or None, "calls": [...]}.
The pool picks the first key of the order that is free; when its limit ends it moves to the next one."""
import math
from .config import get_settings, update_settings
from .keystore import load_keys

ROLES = ("translate", "edit")
AUTO = "auto"


def _compatible(k, role):
    return k.get("enabled") and (role == "any" or k.get("role", "both") in ("both", role))


def get_order(role):
    """The saved order, without keys that were deleted."""
    ids = {k["id"] for k in load_keys()}
    return [i for i in (get_settings().get("prio_" + role) or []) if i in ids]


def set_order(role, ids):
    seen, out = set(), []
    for i in ids:
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    update_settings(**{"prio_" + role: out})
    return out


def order_for(role):
    """What the pool follows when nothing else was chosen. [] = no priority set (the pool spreads the work over all keys)."""
    if role not in ROLES:
        return []
    keys = {k["id"]: k for k in load_keys()}
    return [i for i in get_order(role) if i in keys and _compatible(keys[i], role)]


def new_route(role, choice=AUTO, fallback=True, max_wait=30):
    """choice: "auto" = follow the saved priority; or one key id = start with it, and (if fallback) continue with the priority."""
    pri = order_for(role)
    if choice and choice != AUTO:
        order = [choice] + ([i for i in pri if i != choice] if fallback else [])
        return {"order": order, "only": not fallback, "max_wait": max_wait, "calls": []}
    return {"order": pri, "only": False, "max_wait": max_wait, "calls": []}


def choices(role="any", with_auto=True, auto_label="حسب ترتيب الأولوية في الإعدادات"):
    from .pool import kname
    out = [(auto_label, AUTO)] if with_auto else []
    for k in load_keys():
        if _compatible(k, role):
            out.append((f"{kname(k)} · {k.get('model') or 'نموذج تلقائي'}", k["id"]))
    return out


def brief_limit(k):
    """One short line: what is left of this key's allowance."""
    import re
    from .pool import POOL, ltr
    L = POOL.limits(k)
    g = {}
    for h, v in L["rl"].items():
        m = re.match(r"x-ratelimit-(remaining|limit)-(requests|tokens)(?:-(\w+))?$", h)
        if m:
            g.setdefault((m.group(2), m.group(3) or ""), {})[m.group(1)] = v
    sufs = {"day": "اليوم", "minute": "بالدقيقة", "hour": "بالساعة", "": ""}
    for pref in (("requests", "day"), ("requests", ""), ("requests", "minute"), ("tokens", "day"), ("tokens", "minute")):
        d = g.get(pref)
        if d and d.get("remaining") is not None:
            what = "طلب" if pref[0] == "requests" else "توكن"
            tail = f" من {ltr(d['limit'])}" if d.get("limit") else ""
            return f"المتبقي {sufs.get(pref[1], '')}: {ltr(d['remaining'])}{tail} {what}".replace("  ", " ")
    if k.get("daily_requests"):
        return f"المتبقي من حدك اليومي: {ltr(max(0, k['daily_requests'] - L['day_req']))} من {ltr(k['daily_requests'])} طلب"
    return f"الخدمة لا تعلن المتبقي. استخدمت اليوم {ltr(L['day_req'])} طلب"


def first_key(route, role):
    """Which key a request would use first now (for the 'working…' notice)."""
    from .pool import POOL
    import time
    keys = {k["id"]: k for k in load_keys()}
    for kid in route["order"]:
        k = keys.get(kid)
        if k and POOL._alive(k, role) and POOL._rt(kid)["cool"] <= time.time():
            return k
    for k in load_keys():
        if POOL._alive(k, role) and POOL._rt(k["id"])["cool"] <= time.time():
            return k
    return None


def estimate_seconds(k, units=1):
    from .pool import POOL
    lat = POOL._rt(k["id"]).get("lat") or 6.0
    return max(2, int(lat * max(1, math.ceil(units / 12)) + 1))


def announce(route, role, what, units=1):
    """Text of the 'working now' notice: who, how long (about), and how much is left."""
    from .pool import kname, ltr
    k = first_key(route, role)
    if not k:
        return None
    return (f"{what} بـ <b>{kname(k)}</b> ({k.get('model') or 'نموذج تلقائي'})<br>"
            f"المدة التقريبية: نحو {ltr(estimate_seconds(k, units))} ثانية<br>{brief_limit(k)}")


def summary(route, what):
    """Text of the 'finished' notice: who answered (and if it switched because a limit ended), how long, what is left."""
    from .pool import POOL, ltr
    calls = route["calls"]
    if not calls:
        return None
    names, seen = [], set()
    for c in calls:
        if c["id"] not in seen:
            seen.add(c["id"])
            names.append(c)
    keys = {k["id"]: k for k in load_keys()}
    who = " ثم ".join(f"<b>{c['name']}</b> ({c['model'] or 'تلقائي'})" for c in names)
    secs = sum(c["secs"] for c in calls)
    last = keys.get(calls[-1]["id"])
    lines = [f"{what}: {who}", f"المدة: نحو {ltr(round(secs, 1))} ثانية"]
    if len(names) > 1:
        lines.insert(1, f"تحوّل تلقائياً من {names[0]['name']} إلى {names[-1]['name']} لأن حدّه انتهى أو تعذّر")
    if last:
        lines.append(brief_limit(last))
    return "<br>".join(lines)
