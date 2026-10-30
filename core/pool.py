"""Key pool: spreads calls over all usable keys, respects each key's RPM, waits (never gives up) on rate limits."""
import threading, time
from collections import deque
from . import llm
from .config import get_settings, add_spent
from .keystore import load_keys, add_usage, PROVIDER_LABELS

TASK_AR = {"translate": "ترجمة", "context": "بناء المسرد", "edit": "تدقيق", "ping": "اختبار"}


class NoKeys(Exception):
    pass


class Stopped(Exception):
    pass


def kname(k):
    return f"{PROVIDER_LABELS.get(k['provider'], k['provider'])} · {k.get('model', '')}"


def clock(ts):
    return time.strftime("%H:%M:%S", time.localtime(ts))


def human(sec):
    sec = int(max(0, sec))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    parts = []
    if h:
        parts.append(f"{h} ساعة")
    if m:
        parts.append(f"{m} دقيقة")
    if s and not h:
        parts.append(f"{s} ثانية")
    return " و ".join(parts) or "لحظات"


class KeyPool:
    def __init__(self):
        self.lock = threading.Lock()
        self.rt = {}
        self.glob_next = 0.0
        self.events = deque(maxlen=300)
        self.waiting_until = 0.0

    def log(self, msg, level="info"):
        self.events.append((time.time(), level, msg))

    def _rt(self, kid):
        return self.rt.setdefault(kid, {"next_ok": 0.0, "cool": 0.0, "reason": "", "dead": "", "verified": None,
                                        "ok": 0, "busy": 0, "task": "", "tin": 0, "tout": 0})

    def _alive(self, k, role):
        r = self._rt(k["id"])
        if not k.get("enabled") or r["dead"]:
            return False
        if k.get("role", "both") not in ("both", role):
            return False
        if k.get("paid") and get_settings()["spent_usd"] >= get_settings()["budget_usd"]:
            return False
        return True

    def acquire(self, role="translate", stop=None):
        while True:
            if stop and stop():
                raise Stopped()
            chosen, wait_for = None, 2.0
            with self.lock:
                now = time.time()
                alive = [k for k in load_keys() if self._alive(k, role)]
                if not alive:
                    raise NoKeys("ما فيه أي مفتاح صالح (كلها مرفوضة أو متوقفة أو نفد رصيدها). أضف مفتاحاً أو اختبر المفاتيح.")
                ready = [k for k in alive if self._rt(k["id"])["cool"] <= now]
                if ready:
                    free = [k for k in ready if not k.get("paid") and self._rt(k["id"])["next_ok"] <= now + 3]
                    k = min(free or ready, key=lambda x: self._rt(x["id"])["next_ok"])
                    r = self._rt(k["id"])
                    start = max(now, r["next_ok"], self.glob_next)
                    r["next_ok"] = start + 60.0 / max(k.get("rpm", 10), 1)
                    self.glob_next = start + get_settings()["stagger_seconds"]
                    self.waiting_until = 0.0
                    chosen = (k, start - now)
                else:
                    self.waiting_until = min(self._rt(k["id"])["cool"] for k in alive)
                    wait_for = min(2.0, max(0.1, self.waiting_until - now))
            if chosen:
                if chosen[1] > 0:
                    time.sleep(chosen[1])
                return chosen[0]
            time.sleep(wait_for)

    def cooldown(self, k, seconds, reason="minute"):
        r = self._rt(k["id"])
        r["cool"], r["reason"] = time.time() + seconds, reason
        others = [x for x in load_keys() if x["id"] != k["id"] and self._alive(x, "translate")
                  and self._rt(x["id"])["cool"] <= time.time()]
        why = "الحد اليومي" if reason == "day" else "حد الدقيقة"
        tail = "وتحوّلت الطلبات إلى مفتاح آخر" if others else "وكل المفاتيح الأخرى مشغولة أو تنتظر"
        self.log(f"⏳ {kname(k)} وصل {why}. ينتظر {human(seconds)} (حتى {clock(r['cool'])}) {tail}", "warn")

    def kill(self, k, why):
        r = self._rt(k["id"])
        r["dead"], r["verified"] = why, False
        self.log(f"❌ {kname(k)} مرفوض ولن يُستخدم: {why[:90]}", "error")

    def revive(self, kid):
        self.rt.pop(kid, None)

    def mark_verified(self, kid, ok):
        self._rt(kid)["verified"] = ok

    def record(self, k, usage):
        r = self._rt(k["id"])
        r["ok"] += 1
        r["tin"] += usage["in"]
        r["tout"] += usage["out"]
        r["dead"] = ""
        add_usage(k["id"], usage["in"], usage["out"])
        if k.get("paid"):
            add_spent((usage["in"] * k.get("price_in", 0) + usage["out"] * k.get("price_out", 0)) / 1e6)

    def status(self):
        now = time.time()
        out = []
        for k in load_keys():
            r = self._rt(k["id"])
            if not k.get("enabled"):
                st, css = "متوقف يدوياً", "off"
            elif r["dead"]:
                st, css = "مرفوض: " + r["dead"][:70], "bad"
            elif r["cool"] > now:
                why = "الحد اليومي" if r["reason"] == "day" else "حد الدقيقة"
                st, css = f"ينتظر حتى {clock(r['cool'])} ({why}، باقي {human(r['cool'] - now)})", "wait"
            elif r["busy"] > 0:
                st, css = f"يعمل الآن: {TASK_AR.get(r['task'], r['task'])} ({r['busy']} طلب)", "busy"
            elif r["verified"] is False:
                st, css = "فشل الاختبار", "bad"
            elif r["verified"] or r["ok"]:
                st, css = "جاهز ✓", "ok"
            else:
                st, css = "لم يُختبر بعد", "new"
            out.append({"k": k, "state": st, "css": css, "ok": r["ok"], "tin": k.get("tokens_in", 0) + 0,
                        "tout": k.get("tokens_out", 0) + 0})
        return out


POOL = KeyPool()


def call(messages, role="translate", max_tokens=4096, temperature=0.3, task="translate", tries=6, stop=None):
    errs, last = 0, None
    while errs < tries:
        k = POOL.acquire(role, stop)
        r = POOL._rt(k["id"])
        r["busy"] += 1
        r["task"] = task
        try:
            text, usage = llm.chat(k, messages, max_tokens, temperature, task)
            POOL.record(k, usage)
            return text
        except llm.RateLimited as e:          # rate limits never count as failures: wait and switch key
            POOL.cooldown(k, e.retry_after, e.reason)
        except llm.KeyDead as e:
            POOL.kill(k, str(e))
        except llm.Transient as e:
            errs += 1
            last = e
            POOL.log(f"⚠ {kname(k)}: {str(e)[:100]} (محاولة {errs} من {tries})", "warn")
            time.sleep(min(2 ** errs, 20))
        finally:
            r["busy"] -= 1
    raise RuntimeError(f"فشل الطلب بعد {tries} محاولات: {last}")
