"""AI help inside the manual editor: translate one paragraph or a whole page, and pasted-list numbering."""
import base64, re
from . import glossary, llm, translator
from .pool import call


def number_lines(text, fmt="{n}_ "):
    """Numbers every non-empty line that is not already numbered (1_ , 1- , 1. , (1) , ١_ ...)."""
    lines = (text or "").splitlines()
    out, n = [], 1
    for ln in lines:
        if not ln.strip():
            out.append(ln)
            continue
        if re.match(r"^\s*[\(\[]?[0-9٠-٩]+\s*[_\-\.\)\]:،]", ln):
            out.append(ln)
        else:
            out.append(fmt.format(n=n) + ln.strip())
        n += 1
    return "\n".join(out)


def translate_units(items, ctx="", style="", route=None):
    """items: [{"uid","text"}]. Uses the same pipeline as the automatic translation (parallel keys, quality gate, retries).
    Returns {uid: (translation, problem note)}. Raises NoKeys when no key can be used."""
    units = [{"id": i["uid"], "text": i["text"], "translate": True, "tr": "", "page": 0, "heading": False}
             for i in items if (i.get("text") or "").strip()]
    if not units:
        return {}
    translator.translate_all(units, "auto", "ar", ctx, style, "", route=route)
    return {u["id"]: (u.get("tr", ""), u.get("flag", "")) for u in units}


def build_context(texts, style=""):
    units = [{"text": t, "translate": True, "id": f"P_{i}"} for i, t in enumerate(texts) if (t or "").strip()]
    return glossary.build_context(units, "auto", "ar", style)


def read_image(png_bytes):
    """Asks a vision-capable key to read the text in a picture. The picture is sent to that service."""
    b64 = base64.b64encode(png_bytes).decode()
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": "Transcribe the text in this image exactly as written, in its original language and script. "
                                 "Return only the text, nothing else. Join the lines of a paragraph with spaces."},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]
    avoid, last = set(), ""
    for _ in range(5):
        try:
            txt = call(msgs, role="translate", max_tokens=1500, temperature=0, task="ocr", avoid=avoid).strip()
            if txt:
                return txt
        except llm.BadRequest as e:
            avoid.add(getattr(e, "key_id", ""))
            last = str(e)
    raise RuntimeError("لا يوجد مفتاح يقبل الصور (أو رفضها). جرّب مفتاح Gemini أو نموذجاً يدعم الرؤية. آخر رد: " + last[:150])
