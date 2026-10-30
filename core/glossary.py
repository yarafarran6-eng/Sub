import json, re
from .config import LANGS
from .pool import call


def extract_json(text, opener="{"):
    closer = "}" if opener == "{" else "]"
    text = re.sub(r"```\w*", "", text)
    i, j = text.find(opener), text.rfind(closer)
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(text[i:j + 1])
    except Exception:
        return None


def sample_text(units, budget=14000):
    texts = [u["text"] for u in units if u.get("translate")]
    if not texts:
        return ""
    total = sum(len(t) for t in texts)
    if total <= budget:
        return "\n".join(texts)
    head, mid, tail = [], [], []
    acc = 0
    for t in texts:
        if acc > budget * 0.5:
            break
        head.append(t); acc += len(t)
    m = len(texts) // 2
    acc = 0
    for t in texts[m:]:
        if acc > budget * 0.25:
            break
        mid.append(t); acc += len(t)
    acc = 0
    for t in reversed(texts):
        if acc > budget * 0.25:
            break
        tail.insert(0, t); acc += len(t)
    return "\n".join(head) + "\n[...]\n" + "\n".join(mid) + "\n[...]\n" + "\n".join(tail)


def build_context(units, src, tgt, style="", stop=None):
    """Returns the context card as pretty JSON text (the user can edit it before translation)."""
    sample = sample_text(units)
    sysmsg = (f"You are a literary editor preparing a translation bible for a novel being translated into "
              f"{LANGS.get(tgt, tgt)}. Read the excerpts and return ONLY JSON with keys: "
              '"title", "genre", "tone", "narrator" (person/tense), '
              '"characters" (list of {"name", "target_name", "gender": "male|female|unknown", "notes"}), '
              '"terms" (list of {"src", "target", "note"} for special terms, titles, honorifics, places, fantasy terms), '
              '"style_notes" (short guidance for keeping the voice consistent). '
              "Choose one fixed target rendering for every name and term. Do not invent facts not in the text.")
    user = (f"Client style request: {style or 'none'}\n\nEXCERPTS:\n{sample}")
    try:
        text = call([{"role": "system", "content": sysmsg}, {"role": "user", "content": user}],
                    role="edit", max_tokens=3000, temperature=0.2, task="context", stop=stop)
        data = extract_json(text) or {}
    except Exception as e:
        if type(e).__name__ in ("Stopped", "NoKeys"):
            raise
        data = {}
    return json.dumps(data, ensure_ascii=False, indent=1) if data else ""
