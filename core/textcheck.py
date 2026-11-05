"""Detects text that was extracted from a PDF whose fonts have no proper text mapping (it comes out as symbols)."""
import re

_WEIRD = re.compile("[\u0080-\u009f\u00a1-\u00ac\u00ae-\u00bf\u0100-\u024f\ue000-\uf8ff\ufffd\u0000-\u0008\u000b-\u001f]")
_ASCII_LETTER = re.compile("[A-Za-z]")


def garbled(text, min_len=6):
    """Mostly symbols from unusual ranges AND hardly any normal letters. Polish, Czech or French text is not flagged."""
    t = re.sub(r"\s+", "", text or "")
    if len(t) < min_len:
        return False
    weird = len(_WEIRD.findall(t)) / len(t)
    ascii_share = len(_ASCII_LETTER.findall(t)) / len(t)
    return weird > 0.2 and ascii_share < 0.5


def share(texts):
    ts = [t for t in texts if len((t or "").strip()) >= 6]
    return (sum(1 for t in ts if garbled(t)) / len(ts)) if ts else 0.0
