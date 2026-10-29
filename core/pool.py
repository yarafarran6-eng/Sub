"""Key pool: spreads calls over all enabled keys, respects each key's RPM, cools down on 429."""
import threading, time
from . import llm
from .config import get_settings, add_spent
from .keystore import load_keys, update_key, add_usage


class NoKeys(Exception):
    pass


class KeyPool:
    def __init__(self):
        self.lock = threading.Lock()
        self.rt = {}
        self.glob_next = 0.0
        self.stop = threading.Event()

    def _rt(self, kid):
        return self.rt.setdefault(kid, {"next_ok": 0.0, "cool": 0.0, "dead": "", "ok": 0, "err": 0})

    def _usable(self, k, role, now):
        r = self._rt(k["id"])
        if not k.get("enabled") or r["dead"] or r["cool"] > now:
            return False
        if k.get("role", "both") not in ("both", role):
            return False
        if k.get("paid") and get_settings()["spent_usd"] >= get_settings()["budget_usd"]:
            return False
        return True

    def acquire(self, role="translate", timeout=900):
        t0 = time.time()
        while not self.stop.is_set():
            chosen = None
            with self.lock:
                now = time.time()
                ks = [k for k in load_keys() if self._usable(k, role, now)]
                if ks:
                    # free keys first; paid keys only when no free key can serve right now
                    free = [k for k in ks if not k.get("paid") and self._rt(k["id"])["next_ok"] <= now + 3]
                    cand = free or ks
                    k = min(cand, key=lambda x: self._rt(x["id"])["next_ok"])
                    r = self._rt(k["id"])
                    start = max(now, r["next_ok"], self.glob_next)
                    r["next_ok"] = start + 60.0 / max(k.get("rpm", 10), 1)
                    self.glob_next = start + get_settings()["stagger_seconds"]
                    chosen = (k, start - now)
            if chosen:
                if chosen[1] > 0:
                    time.sleep(chosen[1])
                return chosen[0]
            if time.time() - t0 > timeout:
                raise NoKeys("no usable API keys (all disabled, cooling down, or budget exhausted)")
            time.sleep(1.0)
        raise NoKeys("stopped")

    def cooldown(self, k, seconds):
        self._rt(k["id"])["cool"] = time.time() + seconds

    def kill(self, k, why):
        self._rt(k["id"])["dead"] = why

    def revive(self, kid):
        self.rt[kid] = {"next_ok": 0.0, "cool": 0.0, "dead": "", "ok": 0, "err": 0}

    def record(self, k, usage):
        self._rt(k["id"])["ok"] += 1
        add_usage(k["id"], usage["in"], usage["out"])
        if k.get("paid"):
            add_spent((usage["in"] * k.get("price_in", 0) + usage["out"] * k.get("price_out", 0)) / 1e6)

    def status(self):
        now = time.time()
        out = []
        for k in load_keys():
            r = self._rt(k["id"])
            if not k.get("enabled"):
                st = "متوقف"
            elif r["dead"]:
                st = "مرفوض: " + r["dead"][:40]
            elif r["cool"] > now:
                st = f"انتظار {int(r['cool'] - now)}ث"
            else:
                st = "جاهز"
            out.append((k, st, r["ok"]))
        return out


POOL = KeyPool()


def call(messages, role="translate", max_tokens=4096, temperature=0.3, task="translate", tries=8, pool=None):
    pool = pool or POOL
    last = None
    for i in range(tries):
        k = pool.acquire(role)
        try:
            text, usage = llm.chat(k, messages, max_tokens, temperature, task)
            pool.record(k, usage)
            return text
        except llm.RateLimited as e:
            pool.cooldown(k, e.retry_after)
            last = e
        except llm.KeyDead as e:
            pool.kill(k, str(e))
            last = e
        except llm.Transient as e:
            time.sleep(min(2 ** i, 20))
            last = e
    raise RuntimeError(f"API call failed after {tries} tries: {last}")
