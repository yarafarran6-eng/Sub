"""One OpenAI-compatible chat call. Gemini, Groq, Cerebras, OpenRouter, Mistral, Ollama all speak it."""
import json, re
import httpx
from .keystore import PROVIDERS


class RateLimited(Exception):
    def __init__(self, retry_after=30.0, reason="minute", detail=""):
        self.retry_after, self.reason, self.detail = retry_after, reason, detail


class KeyDead(Exception):
    pass


class Transient(Exception):
    pass


class BadRequest(Exception):
    pass


def _msg(r):
    """The service's own error text, as short as possible."""
    try:
        j = r.json()
        if isinstance(j, list) and j:
            j = j[0]
        if isinstance(j, dict):
            e = j.get("error", j)
            m = (e.get("message") or e.get("detail") or json.dumps(e, ensure_ascii=False)) if isinstance(e, dict) else str(e)
            return str(j.get("detail") or m)[:260]
    except Exception:
        pass
    return r.text[:260]


def _net(e):
    s = str(e).lower()
    if isinstance(e, (httpx.ConnectTimeout, httpx.ReadTimeout)) or "timed out" in s:
        return "انتهت المهلة بدون رد: الخدمة بطيئة أو غير متاحة"
    if "name or service not known" in s or "getaddrinfo" in s or "[errno -2]" in s or "[errno -3]" in s or "nodename" in s:
        return "العنوان غير معروف: تأكد من كتابته ومن اتصال الإنترنت"
    if "refused" in s or "[errno 111]" in s or "10061" in s:
        return "الاتصال مرفوض: البرنامج غير شغّال عند هذا العنوان (مثل Ollama) أو رقم المنفذ غلط"
    return f"تعذر الاتصال: {str(e)[:100]}"


def _wait_from(r):
    ra = r.headers.get("retry-after")
    if ra:
        try:
            return max(float(ra), 1.0)
        except ValueError:
            pass
    t = r.text
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', t)
    if m:
        return float(m.group(1)) + 1
    m = re.search(r"try again in\s+(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+(?:\.\d+)?)s)?", t, re.I)
    if m and any(m.groups()):
        h, mi, s = (float(x) if x else 0.0 for x in m.groups())
        return h * 3600 + mi * 60 + s + 1
    return 30.0


def _reason(text, wait):
    t = text.lower()
    if re.search(r"limit['\"]?\s*[:=]\s*0(?![\d.])", t):
        return "zero"                         # the quota of this model is zero for this key (not "used up")
    if wait > 900 or any(w in t for w in ("per day", "perday", "daily", "tpd", "rpd", "per_day")):
        return "day"
    return "minute"


_mock_n = {"n": 0}


def _mock(key, messages, task):
    _mock_n["n"] += 1
    if key["key"].startswith("mock-dead"):
        raise KeyDead("401: mock invalid key")
    if key["key"].startswith("mock-limit"):
        key_n = _mock_n.setdefault(key["key"], 0) + 1
        _mock_n[key["key"]] = key_n
        if key_n <= 3 or key_n % 3 == 0:
            raise RateLimited(1.5, "minute", "mock limit")
    user = messages[-1]["content"]
    if task == "translate":
        out = []
        for line in user.splitlines():
            m = re.match(r"^\s*\[(P_\d+)\]\s*(.*)$", line)
            if m:
                out.append(f"[{m.group(1)}] «ترجمة تجريبية: {m.group(2)}»")
        return "\n".join(out)
    if task == "context":
        return json.dumps({"title": "Test", "tone": "neutral", "characters": [
            {"name": "Alice", "target_name": "أليس", "gender": "female"}], "terms": []})
    return "[]"


def chat(key, messages, max_tokens=4096, temperature=0.3, task="translate", timeout=180):
    prov = PROVIDERS[key["provider"]]
    if key["provider"] == "mock":
        return _mock(key, messages, task), {"in": 10, "out": 10}
    base = (key.get("base") or prov["base"]).rstrip("/")
    if not base:
        raise BadRequest("لم تحدد عنوان الخادم")
    headers = {"Authorization": f"Bearer {key['key']}"} if key.get("key") else {}
    if any(x in base for x in ("localhost", "127.0.0.1", "0.0.0.0", "192.168.")):
        timeout = max(timeout, 900)           # local models can be slow
    body = {"messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if key.get("model"):                       # no model name = let the service choose its own
        body["model"] = key["model"]
    try:
        r = httpx.post(base + "/chat/completions", json=body, timeout=timeout, headers=headers)
    except (httpx.TimeoutException, httpx.TransportError) as e:
        raise Transient(_net(e))
    if r.status_code == 429:
        w = _wait_from(r)
        raise RateLimited(w, _reason(r.text, w), _msg(r))
    if r.status_code in (401, 403):
        raise KeyDead(f"{r.status_code}: {_msg(r)}")
    if r.status_code >= 500:
        raise Transient(f"خطأ من الخدمة نفسها ({r.status_code}): {_msg(r)}")
    if r.status_code >= 400:
        raise BadRequest(f"{r.status_code}: {_msg(r)}")
    data = r.json()
    ch = (data.get("choices") or [{}])[0]
    if ch.get("finish_reason") == "length":
        raise BadRequest("truncated output")
    text = (ch.get("message") or {}).get("content") or ""
    u = data.get("usage") or {}
    return text, {"in": u.get("prompt_tokens", 0), "out": u.get("completion_tokens", 0)}


_SKIP = ("embed", "whisper", "tts", "audio", "guard", "moderation", "rerank", "imagen", "veo", "dall-e", "transcribe")


def list_models(provider, key="", base=""):
    """Asks the company which models it offers (OpenAI-style /models). Returns a sorted list of ids."""
    if provider == "mock":
        return ["mock"]
    b = (base or PROVIDERS[provider]["base"]).rstrip("/")
    if not b:
        raise BadRequest("حدد عنوان الخادم أولاً")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        r = httpx.get(b + "/models", headers=headers, timeout=30)
    except (httpx.TimeoutException, httpx.TransportError) as e:
        raise Transient(_net(e))
    if r.status_code in (401, 403):
        raise KeyDead(f"{r.status_code}: {_msg(r)}")
    if r.status_code >= 400:
        raise BadRequest(f"{r.status_code}: {_msg(r)}")
    data = r.json()
    items = data.get("data") or data.get("models") or [] if isinstance(data, dict) else data
    ids = []
    for it in items:
        i = (it.get("id") or it.get("name")) if isinstance(it, dict) else str(it)
        if i:
            ids.append(i.replace("models/", ""))
    return sorted(i for i in dict.fromkeys(ids) if not any(w in i.lower() for w in _SKIP))
