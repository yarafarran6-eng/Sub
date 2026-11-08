"""Lets the chat know about one of your novels: the context card plus the paragraphs (source and translation) most related to the question."""
import re
from . import jobs, manual

BUDGET = 14000


def projects():
    return [("— بدون —", "")] + manual.list_all()


def _load(value):
    kind, _, i = (value or "").partition(":")
    if kind == "p":
        meta, units = manual.load(i)
        if not meta:
            return None, "", []
        did = manual.ensure_draft(i)
        d = manual.load_draft(i, did)
        merged = manual.merged_units(units, d)
        return meta["name"], d.get("ctx", ""), merged
    if kind == "j":
        meta, units = jobs.load(i)
        if not meta:
            return None, "", []
        return meta["name"], meta.get("ctx", ""), [u for u in units if u.get("translate")]
    return None, "", []


def project_context(value, query, budget=BUDGET):
    name, ctx, units = _load(value)
    if not name:
        return ""
    words = {w for w in re.findall(r"\w{3,}", (query or "").lower())}
    pages = {}
    for u in units:
        pages.setdefault(u.get("page", 0), []).append(u)

    def score(us):
        blob = " ".join((u.get("text", "") + " " + (u.get("tr") or "")) for u in us).lower()
        return sum(blob.count(w) for w in words)

    order = sorted(pages, key=lambda p: (-score(pages[p]), p)) if words and any(score(v) for v in pages.values()) else sorted(pages)
    out, used = [], len(ctx)
    chosen = []
    for p in order:
        block = "\n".join(f"- {u.get('text', '')}" + (f"  ⇒ {u['tr']}" if u.get("tr") else "") for u in pages[p])
        if used + len(block) > budget:
            continue
        chosen.append((p, block))
        used += len(block)
    for p, block in sorted(chosen):
        out.append(f"[صفحة {p + 1}]\n{block}")
    head = f"\n\nPROJECT: «{name}». The user is asking about this novel. Answer from the material below; if it is not there, say so.\n"
    return head + (f"CONTEXT CARD (names, terms, tone):\n{ctx}\n\n" if ctx else "") + "PARAGRAPHS (source ⇒ translation):\n" + "\n\n".join(out)
