"""One OpenAI-compatible chat call. Gemini, Groq, Cerebras, OpenRouter and Mistral all speak it."""
import json, re
import httpx
from .keystore import PROVIDERS


class RateLimited(Exception):
    def __init__(self, retry_after=30.0):
        self.retry_after = retry_after


class KeyDead(Exception):
    pass


class Transient(Exception):
    pass


class BadRequest(Exception):
    pass


def _mock(messages, task):
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
        return _mock(messages, task), {"in": 10, "out": 10}
    body = {"model": key["model"], "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens}
    try:
        r = httpx.post(prov["base"] + "/chat/completions", json=body, timeout=timeout,
                       headers={"Authorization": f"Bearer {key['key']}"})
    except (httpx.TimeoutException, httpx.TransportError) as e:
        raise Transient(str(e))
    if r.status_code == 429:
        try:
            ra = float(r.headers.get("retry-after", 30))
        except ValueError:
            ra = 30.0
        raise RateLimited(max(ra, 5.0))
    if r.status_code in (401, 403):
        raise KeyDead(f"{r.status_code}: {r.text[:200]}")
    if r.status_code >= 500:
        raise Transient(f"{r.status_code}")
    if r.status_code >= 400:
        raise BadRequest(f"{r.status_code}: {r.text[:300]}")
    data = r.json()
    ch = (data.get("choices") or [{}])[0]
    if ch.get("finish_reason") == "length":
        raise BadRequest("truncated output")
    text = (ch.get("message") or {}).get("content") or ""
    u = data.get("usage") or {}
    return text, {"in": u.get("prompt_tokens", 0), "out": u.get("completion_tokens", 0)}
