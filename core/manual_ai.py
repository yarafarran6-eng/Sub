"""AI help inside the manual editor: translate one paragraph or a whole page, and pasted-list numbering."""
import re
from . import glossary, translator


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


def translate_units(items, ctx="", style=""):
    """items: [{"uid","text"}]. Uses the same pipeline as the automatic translation (parallel keys, quality gate, retries).
    Returns {uid: (translation, problem note)}. Raises NoKeys when no key can be used."""
    units = [{"id": i["uid"], "text": i["text"], "translate": True, "tr": "", "page": 0, "heading": False}
             for i in items if (i.get("text") or "").strip()]
    if not units:
        return {}
    translator.translate_all(units, "auto", "ar", ctx, style, "")
    return {u["id"]: (u.get("tr", ""), u.get("flag", "")) for u in units}


def build_context(texts, style=""):
    units = [{"text": t, "translate": True, "id": f"P_{i}"} for i, t in enumerate(texts) if (t or "").strip()]
    return glossary.build_context(units, "auto", "ar", style)
