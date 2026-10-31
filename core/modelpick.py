"""Picks a working model automatically, so you only give a name, a key and an address."""
import re
from . import llm
from .keystore import PROVIDERS

PING = [{"role": "user", "content": "Reply with the single word OK"}]
PREMIUM = ("opus", "gpt-5", "o1", "o3", "o4", "ultra", "gpt-4.5")
QUOTA_WORDS = ("quota", "billing", "insufficient", "credit", "balance", "payment")


def score(model_id):
    """Bigger open/general models first; very small or special-purpose ones last; premium (costly) ones avoided."""
    m = model_id.lower()
    s = 0
    for w, v in (("instruct", 2), ("chat", 2), ("versatile", 2), ("flash", 3), ("large", 4), ("pro", 2),
                 ("gemini", 2), ("llama", 3), ("qwen", 3), ("deepseek", 3), ("mistral", 3), ("gpt-4", 3),
                 ("claude", 3), ("sonnet", 3), ("haiku", 1)):
        if w in m:
            s += v
    for w, v in (("mini", -1), ("nano", -5), ("tiny", -5), ("small", -2), ("lite", -2), ("preview", -1),
                 ("vision", -4), ("coder", -3), ("code", -2), ("-vl", -3), ("embed", -9), ("guard", -9),
                 ("distill", -1), ("thinking", -2)):
        if w in m:
            s += v
    if any(w in m for w in PREMIUM):
        s -= 8
    sz = re.search(r"(?<![a-z0-9.])(\d{1,3}(?:\.\d)?)b(?![a-z])", m)
    if sz:
        n = float(sz.group(1))
        s += 6 if n >= 70 else 3 if n >= 30 else 1 if n >= 20 else -2 if n >= 8 else -5
    return s


def _fail(kind, reason):
    return {"ok": False, "kind": kind, "model": "", "reason": reason}


def auto_pick(k):
    """Returns {"ok", "model", "kind" (key|net|quota|model), "reason"}. An empty model means: let the service decide."""
    prov = PROVIDERS[k["provider"]]
    base = k.get("base") or prov["base"]
    default = prov.get("model") or ""
    ids, list_err = None, ""
    try:
        ids = llm.list_models(k["provider"], k.get("key", ""), base)
    except llm.KeyDead as e:
        return _fail("key", f"المفتاح مرفوض أو بدون صلاحية. رد الخدمة: {e}")
    except llm.Transient as e:
        return _fail("net", str(e))
    except Exception as e:
        list_err = str(e)
    if ids and "openrouter.ai" in base and not k.get("paid"):
        ids = [i for i in ids if i.endswith(":free")] or ids      # never pick a paid model by surprise
    if ids:
        ranked = sorted(ids, key=score, reverse=True)
        cands = ([default] if default in ids else []) + [i for i in ranked if i != default][:6]
    else:
        cands = ([default] if default else []) + [""]               # last resort: send no model name at all
    last = ""
    for c in cands:
        try:
            llm.chat(dict(k, model=c), PING, 20, 0, "ping", 60)
            return {"ok": True, "model": c, "kind": "", "reason": ""}
        except llm.RateLimited:
            return {"ok": True, "model": c, "kind": "", "reason": ""}
        except llm.KeyDead as e:
            return _fail("key", f"المفتاح مرفوض أو بدون صلاحية. رد الخدمة: {e}")
        except llm.Transient as e:
            return _fail("net", str(e))
        except llm.BadRequest as e:
            last = str(e)
            if last.startswith("402") or any(w in last.lower() for w in QUOTA_WORDS):
                return _fail("quota", f"الرصيد أو الحصة غير كافية. رد الخدمة: {last}")
    extra = f" وتعذر جلب قائمة النماذج ({list_err})" if list_err else ""
    return _fail("model", f"جربت {len(cands)} خيار ولا واحد اشتغل{extra}. آخر رد من الخدمة: {last}")
