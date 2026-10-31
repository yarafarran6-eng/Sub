import os, time, uuid
from .config import DATA, LOCK, read_json, write_json

KEYS_FILE = DATA / "keys.json"

# Model names change often; every key lets you edit its model in the UI.
PROVIDERS = {
    "gemini": {"label": "Google AI Studio (Gemini)", "base": "https://generativelanguage.googleapis.com/v1beta/openai",
               "prefixes": ("AIza", "AQ."), "model": "gemini-2.5-flash", "rpm": 8, "max_chars": 9000, "need_key": True},
    "groq": {"label": "Groq", "base": "https://api.groq.com/openai/v1", "prefixes": ("gsk_",),
             "model": "llama-3.3-70b-versatile", "rpm": 25, "max_chars": 4500, "need_key": True},
    "cerebras": {"label": "Cerebras", "base": "https://api.cerebras.ai/v1", "prefixes": ("csk-",),
                 "model": "gpt-oss-120b", "rpm": 25, "max_chars": 3500, "need_key": True},
    "openrouter": {"label": "OpenRouter", "base": "https://openrouter.ai/api/v1", "prefixes": ("sk-or-",),
                   "model": "meta-llama/llama-3.3-70b-instruct:free", "rpm": 15, "max_chars": 4500, "need_key": True},
    "mistral": {"label": "Mistral", "base": "https://api.mistral.ai/v1", "prefixes": (),
                "model": "mistral-large-latest", "rpm": 20, "max_chars": 5000, "need_key": True},
    "ollama": {"label": "Ollama (محلي على جهازك، بدون مفتاح)", "base": "http://localhost:11434/v1", "prefixes": (),
               "model": "qwen2.5:7b", "rpm": 30, "max_chars": 3000, "need_key": False},
    "custom": {"label": "خادم آخر (متوافق مع OpenAI)", "base": "", "prefixes": (),
               "model": "", "rpm": 30, "max_chars": 4000, "need_key": False},
    "mock": {"label": "تجريبي", "base": "", "prefixes": ("mock",), "model": "mock", "rpm": 600,
             "max_chars": 4000, "need_key": False},
}
PROVIDER_LABELS = {k: v["label"] for k, v in PROVIDERS.items()}
# Ready-made addresses for companies that speak the OpenAI-style API. Check the address in the company's docs.
PRESETS = {
    "OpenAI": "https://api.openai.com/v1", "DeepSeek": "https://api.deepseek.com/v1",
    "xAI": "https://api.x.ai/v1", "Together AI": "https://api.together.xyz/v1",
    "Fireworks AI": "https://api.fireworks.ai/inference/v1", "SambaNova": "https://api.sambanova.ai/v1",
    "NVIDIA NIM": "https://integrate.api.nvidia.com/v1", "Hyperbolic": "https://api.hyperbolic.xyz/v1",
    "Hugging Face": "https://router.huggingface.co/v1", "LM Studio (محلي)": "http://localhost:1234/v1",
}
UI_PROVIDERS = [(v["label"], k) for k, v in PROVIDERS.items() if k != "mock"]


ADDRESS_CHOICES = ([(v["label"], v["base"]) for n, v in PROVIDERS.items() if n not in ("mock", "custom") and v["base"]]
                   + [(n, u) for n, u in PRESETS.items()])


def provider_from_base(base: str) -> str:
    b = (base or "").strip().rstrip("/")
    for n, v in PROVIDERS.items():
        if v["base"] and n != "mock" and v["base"].rstrip("/") == b:
            return n
    return "custom"


def detect_base(key: str) -> str:
    d = detect_provider(key)
    return PROVIDERS[d]["base"] if d and d != "mock" else ""


def detect_provider(key: str):
    """Returns the provider name when the key has a known prefix, otherwise None (never guess)."""
    key = (key or "").strip()
    for name, p in PROVIDERS.items():
        if any(key.startswith(x) for x in p["prefixes"]):
            return name
    return None


ENV_NAMES = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "cerebras": "CEREBRAS_API_KEY",
             "openrouter": "OPENROUTER_API_KEY", "mistral": "MISTRAL_API_KEY"}


def _env_keys():
    out = []
    for prov, var in ENV_NAMES.items():
        for i, k in enumerate([x.strip() for x in os.getenv(var, "").split(",") if x.strip()], 1):
            p = PROVIDERS[prov]
            out.append({"id": f"env-{prov}-{i}", "provider": prov, "key": k,
                        "model": os.getenv(var.replace("API_KEY", "MODEL"), p["model"]), "role": "both",
                        "enabled": True, "paid": False, "price_in": 0.0, "price_out": 0.0, "rpm": p["rpm"],
                        "tokens_in": 0, "tokens_out": 0, "env": True})
    return out


def load_keys():
    return read_json(KEYS_FILE, []) + _env_keys()


def save_keys(keys):
    write_json(KEYS_FILE, [k for k in keys if not str(k.get("id", "")).startswith("env-")])


def add_key(provider, key, model="", role="both", paid=False, price_in=0.0, price_out=0.0, rpm=0, base="", label=""):
    p = PROVIDERS[provider]
    entry = {
        "id": uuid.uuid4().hex[:8], "provider": provider, "key": (key or "").strip(),
        "model": (model or p["model"]).strip(), "role": role, "enabled": True, "base": (base or "").strip(),
        "label": (label or "").strip(),
        "paid": bool(paid), "price_in": float(price_in or 0), "price_out": float(price_out or 0),
        "rpm": int(rpm or p["rpm"]), "tokens_in": 0, "tokens_out": 0, "added": int(time.time()),
    }
    with LOCK:
        keys = read_json(KEYS_FILE, [])
        keys.append(entry)
        write_json(KEYS_FILE, keys)
    return entry


def update_key(key_id, **kw):
    with LOCK:
        keys = read_json(KEYS_FILE, [])
        for k in keys:
            if k["id"] == key_id:
                k.update(kw)
        write_json(KEYS_FILE, keys)


def delete_key(key_id):
    with LOCK:
        write_json(KEYS_FILE, [k for k in read_json(KEYS_FILE, []) if k["id"] != key_id])


def add_usage(key_id, tin, tout):
    with LOCK:
        keys = read_json(KEYS_FILE, [])
        changed = False
        for k in keys:
            if k["id"] == key_id:
                k["tokens_in"] = k.get("tokens_in", 0) + tin
                k["tokens_out"] = k.get("tokens_out", 0) + tout
                changed = True
        if changed:
            write_json(KEYS_FILE, keys)


def mask(key: str) -> str:
    if not key:
        return "بدون مفتاح"
    return key[:4] + "…" + key[-3:] if len(key) > 9 else "…"


def add_key_generic(name, key, base, model, role="both", paid=False, price_in=0.0, price_out=0.0, rpm=0):
    """Any OpenAI-style service: you choose the name, the address, the key and the model."""
    from urllib.parse import urlparse
    base = (base or "").strip().rstrip("/")
    prov = provider_from_base(base)
    name = (name or "").strip() or urlparse(base).netloc or "مفتاح"
    return add_key(prov, key, model, role, paid, price_in, price_out, rpm or (20 if prov == "custom" else 0),
                   base if prov in ("custom", "ollama") else "", name)
