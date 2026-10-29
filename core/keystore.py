import time, uuid
from .config import DATA, LOCK, read_json, write_json

KEYS_FILE = DATA / "keys.json"

# Model names change often; every key lets you edit its model in the UI.
PROVIDERS = {
    "gemini": {"base": "https://generativelanguage.googleapis.com/v1beta/openai", "prefix": "AIza",
               "model": "gemini-2.5-flash", "rpm": 8, "max_chars": 9000},
    "groq": {"base": "https://api.groq.com/openai/v1", "prefix": "gsk_",
             "model": "llama-3.3-70b-versatile", "rpm": 25, "max_chars": 4500},
    "cerebras": {"base": "https://api.cerebras.ai/v1", "prefix": "csk-",
                 "model": "gpt-oss-120b", "rpm": 25, "max_chars": 3500},
    "openrouter": {"base": "https://openrouter.ai/api/v1", "prefix": "sk-or-",
                   "model": "meta-llama/llama-3.3-70b-instruct:free", "rpm": 15, "max_chars": 4500},
    "mistral": {"base": "https://api.mistral.ai/v1", "prefix": "",
                "model": "mistral-large-latest", "rpm": 20, "max_chars": 5000},
    "mock": {"base": "", "prefix": "mock", "model": "mock", "rpm": 600, "max_chars": 4000},
}


def detect_provider(key: str) -> str:
    key = (key or "").strip()
    for name, p in PROVIDERS.items():
        if p["prefix"] and key.startswith(p["prefix"]):
            return name
    return "mistral" if key else "gemini"


def load_keys():
    return read_json(KEYS_FILE, [])


def save_keys(keys):
    write_json(KEYS_FILE, keys)


def add_key(provider, key, model="", role="both", paid=False, price_in=0.0, price_out=0.0, rpm=0):
    p = PROVIDERS[provider]
    entry = {
        "id": uuid.uuid4().hex[:8], "provider": provider, "key": key.strip(),
        "model": (model or p["model"]).strip(), "role": role, "enabled": True,
        "paid": bool(paid), "price_in": float(price_in or 0), "price_out": float(price_out or 0),
        "rpm": int(rpm or p["rpm"]), "tokens_in": 0, "tokens_out": 0, "added": int(time.time()),
    }
    with LOCK:
        keys = load_keys()
        keys.append(entry)
        save_keys(keys)
    return entry


def update_key(key_id, **kw):
    with LOCK:
        keys = load_keys()
        for k in keys:
            if k["id"] == key_id:
                k.update(kw)
        save_keys(keys)


def delete_key(key_id):
    with LOCK:
        save_keys([k for k in load_keys() if k["id"] != key_id])


def add_usage(key_id, tin, tout):
    with LOCK:
        keys = load_keys()
        for k in keys:
            if k["id"] == key_id:
                k["tokens_in"] = k.get("tokens_in", 0) + tin
                k["tokens_out"] = k.get("tokens_out", 0) + tout
        save_keys(keys)


def mask(key: str) -> str:
    return key[:4] + "…" + key[-3:] if len(key) > 9 else "…"
