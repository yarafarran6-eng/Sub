import concurrent.futures as cf, re
from . import llm
from .config import LANGS, get_settings
from .keystore import PROVIDERS, load_keys
from .pool import call, NoKeys, Stopped

MARK = re.compile(r"^\s*\[(P_\d+)\]\s?(.*)$")


def system_prompt(src, tgt, ctx, style, golden):
    s = LANGS.get(tgt, tgt)
    p = f"""You are a senior professional literary translator with decades of experience translating published novels.
Translate from {LANGS.get(src, 'the source language') if src != 'auto' else 'the source language (detect it)'} into {s}.

QUALITY RULES
- Translate for meaning, voice and rhythm, as a skilled human novelist-translator would. Never translate word-for-word. Recast idioms naturally.
- Keep each character's voice consistent. Respect the character genders, name renderings and terminology in the CONTEXT CARD exactly; never vary them.
- Keep dialogue as dialogue. Keep tone, register, humour, tension and sentence rhythm of the original.
- Do not add, omit, explain or summarize. No translator notes.
- Use correct target-language punctuation and typography.
FORMAT RULES (strict)
- The input is paragraphs, each starting with a marker like [P_12].
- Output exactly one translated paragraph per input paragraph, starting with the SAME marker, in the same order.
- Never merge, split, renumber or skip paragraphs. Output nothing but the marked paragraphs.
- Numbers, page numbers and symbols that need no translation: copy as-is after the marker."""
    if tgt == "ar":
        p += "\n- Write fluent, elegant Modern Standard Arabic suitable for published literature, with Arabic punctuation (، ؛ ؟)."
    if ctx:
        p += f"\n\nCONTEXT CARD (authoritative):\n{ctx}"
    if style:
        p += f"\n\nSTYLE REQUESTED BY THE CLIENT:\n{style}"
    if golden:
        p += f"\n\nREFERENCE SAMPLE OF THE DESIRED STYLE (imitate its voice, do not copy its content):\n{golden}"
    return p


def parse_response(text):
    text = re.sub(r"^```\w*\n|\n```$", "", text.strip())
    out, cur = {}, None
    for line in text.splitlines():
        m = MARK.match(line)
        if m:
            cur = m.group(1)
            out[cur] = m.group(2).strip()
        elif cur and line.strip():
            out[cur] += " " + line.strip()
    return out


def make_chunks(units, max_chars):
    chunks, cur, n = [], [], 0
    for u in units:
        if not u.get("translate"):
            continue
        l = len(u["text"]) + 12
        if cur and (n + l > max_chars or (u.get("heading") and n > max_chars * 0.5)):
            chunks.append(cur)
            cur, n = [], 0
        cur.append(u)
        n += l
    if cur:
        chunks.append(cur)
    return chunks


def _translate_chunk(chunk, sysmsg, stop=None, depth=0):
    user = "\n".join(f"[{u['id']}] {u['text'].replace(chr(10), ' ')}" for u in chunk)
    max_tok = min(8000, max(1024, int(len(user) * 1.3)))
    try:
        text = call([{"role": "system", "content": sysmsg}, {"role": "user", "content": user}],
                    role="translate", max_tokens=max_tok, temperature=0.3, task="translate", stop=stop)
    except llm.BadRequest:
        if len(chunk) > 1 and depth < 4:
            mid = len(chunk) // 2
            return {**_translate_chunk(chunk[:mid], sysmsg, stop, depth + 1),
                    **_translate_chunk(chunk[mid:], sysmsg, stop, depth + 1)}
        raise
    got = parse_response(text)
    missing = [u for u in chunk if not got.get(u["id"])]
    if missing and len(missing) < len(chunk) and depth < 3:
        got.update(_translate_chunk(missing, sysmsg, stop, depth + 1))
    elif missing and len(chunk) > 1 and depth < 3:
        mid = len(chunk) // 2
        got.update(_translate_chunk(chunk[:mid], sysmsg, stop, depth + 1))
        got.update(_translate_chunk(chunk[mid:], sysmsg, stop, depth + 1))
    return got


def chunk_budget():
    ks = [k for k in load_keys() if k.get("enabled")]
    if not ks:
        return 4000
    return min(PROVIDERS[k["provider"]]["max_chars"] for k in ks)


def translate_all(units, src, tgt, ctx, style, golden, on_progress=None, should_stop=lambda: False):
    """Fills u['tr'] for every translatable unit. Resumable: units with a translation are skipped.
    on_progress(n_new_units, n_chunks_done, n_chunks_total) is called after every finished chunk."""
    sysmsg = system_prompt(src, tgt, ctx, style, golden)
    todo = [u for u in units if u.get("translate") and not u.get("tr")]
    chunks = make_chunks(todo, chunk_budget())
    total, done, fatal = len(chunks), 0, None
    by_id = {u["id"]: u for u in units}
    workers = max(1, min(get_settings()["max_workers"], len([k for k in load_keys() if k.get("enabled")]) * 3 or 1))
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(_translate_chunk, c, sysmsg, should_stop): c for c in chunks}
        for f in cf.as_completed(futs):
            if should_stop():
                for g in futs:
                    g.cancel()
                break
            chunk, n_new = futs[f], 0
            try:
                got = f.result()
            except NoKeys as e:
                fatal = str(e)
                for g in futs:
                    g.cancel()
                break
            except Stopped:
                got = {}
            except Exception as e:  # keep going; failed paragraphs are retried on resume
                got = {}
                for u in chunk:
                    u["error"] = str(e)[:200]
            for u in chunk:
                t = got.get(u["id"])
                if t:
                    by_id[u["id"]]["tr"] = t
                    u.pop("error", None)
                    n_new += 1
            done += 1
            if on_progress:
                on_progress(n_new, done, total)
    if fatal:
        raise NoKeys(fatal)
    return sum(1 for u in units if u.get("translate") and not u.get("tr"))
