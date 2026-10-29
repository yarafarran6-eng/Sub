"""Surgical editor: reads source + translation, returns ONLY patches keyed by paragraph ID."""
import concurrent.futures as cf
from .config import LANGS, get_settings
from .glossary import extract_json
from .keystore import load_keys
from .pool import call

SENS = {
    "strict": "Fix ONLY serious problems: mistranslations, omissions, additions, wrong character gender or name versus the context card, and sentences that are broken or ungrammatical.",
    "medium": "Fix serious problems (mistranslations, omissions, additions, wrong gender/names, broken sentences) AND awkward, stiff or literal phrasing, plus inconsistent terminology, names or pronouns across paragraphs.",
    "precise": "Fix serious problems, awkward or literal phrasing, inconsistent terminology/names/pronouns, AND any paragraph whose tone or register clashes with the requested style or with the surrounding text.",
}


def _batches(units, max_chars):
    cur, n, out = [], 0, []
    for u in units:
        if not (u.get("translate") and u.get("tr")):
            continue
        l = len(u["text"]) + len(u["tr"]) + 30
        if cur and n + l > max_chars:
            out.append(cur); cur, n = [], 0
        cur.append(u); n += l
    if cur:
        out.append(cur)
    return out


def _run_batch(batch, system, max_tok=3000):
    user = "\n\n".join(f"[{u['id']}]\nSOURCE: {u['text']}\nTRANSLATION: {u['tr']}" for u in batch)
    text = call([{"role": "system", "content": system}, {"role": "user", "content": user}],
                role="edit", max_tokens=max_tok, temperature=0.2, task="edit")
    data = extract_json(text, "[") or []
    return data if isinstance(data, list) else []


def _apply(units_by_id, patches, batch_ids):
    applied = []
    for p in patches:
        if not isinstance(p, dict):
            continue
        uid, fix = str(p.get("id", "")).strip("[] "), (p.get("fix") or "").strip()
        u = units_by_id.get(uid)
        if not u or uid not in batch_ids or not fix or fix == u["tr"]:
            continue
        ratio = len(fix) / max(len(u["tr"]), 1)
        if ratio > 2.5 or ratio < 0.35:      # guard against runaway rewrites
            continue
        applied.append({"id": uid, "old": u["tr"], "new": fix, "why": p.get("why", "")})
        u["tr"] = fix
    return applied


def _editor_chars():
    ks = [k for k in load_keys() if k.get("enabled") and k.get("role", "both") in ("both", "edit")]
    return 12000 if any(k["provider"] == "gemini" for k in ks) else 6000


def edit_pass(units, src, tgt, ctx, style, sensitivity="medium", on_progress=None, should_stop=lambda: False):
    system = (f"You are the chief editor of a professional literary translation into {LANGS.get(tgt, tgt)}. "
              f"You receive paragraphs with SOURCE and TRANSLATION. {SENS[sensitivity]}\n"
              "Do NOT touch paragraphs that are already good. Do not rewrite for taste.\n"
              'Return ONLY a JSON array of patches: [{"id": "P_12", "fix": "<full corrected translation of that paragraph>", "why": "<few words>"}]. '
              "Return [] if nothing needs fixing. Keep the author's voice. No text outside the JSON.\n"
              f"CONTEXT CARD:\n{ctx or 'none'}\nSTYLE: {style or 'none'}")
    by_id = {u["id"]: u for u in units}
    batches = _batches(units, _editor_chars())
    applied, done = [], 0
    workers = max(1, min(get_settings()["max_workers"], len([k for k in load_keys() if k.get("enabled")]) * 2 or 1))
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(_run_batch, b, system): b for b in batches}
        for f in cf.as_completed(futs):
            if should_stop():
                break
            b = futs[f]
            try:
                applied += _apply(by_id, f.result(), {u["id"] for u in b})
            except Exception:
                pass
            done += 1
            if on_progress:
                on_progress(done, len(batches))
    return applied


def run_instruction(units, instruction, src, tgt, ctx, style, on_progress=None):
    system = (f"You are the chief editor of a literary translation into {LANGS.get(tgt, tgt)}. "
              f"The client gave this instruction, apply it faithfully across the paragraphs you receive:\n\"{instruction}\"\n"
              "Only return paragraphs that must change. "
              'Return ONLY a JSON array: [{"id": "P_12", "fix": "<full new translation of that paragraph>", "why": "<few words>"}]. '
              "Return [] if none. Keep everything else untouched.\n"
              f"CONTEXT CARD:\n{ctx or 'none'}\nSTYLE: {style or 'none'}")
    by_id = {u["id"]: u for u in units}
    applied, batches = [], _batches(units, _editor_chars())
    with cf.ThreadPoolExecutor(max(1, min(8, len(batches)))) as ex:
        futs = {ex.submit(_run_batch, b, system): b for b in batches}
        for n, f in enumerate(cf.as_completed(futs), 1):
            b = futs[f]
            try:
                applied += _apply(by_id, f.result(), {u["id"] for u in b})
            except Exception:
                pass
            if on_progress:
                on_progress(n, len(batches))
    return applied


def find_replace(units, find, repl):
    n = 0
    for u in units:
        if u.get("tr") and find in u["tr"]:
            n += u["tr"].count(find)
            u["tr"] = u["tr"].replace(find, repl)
    return n
