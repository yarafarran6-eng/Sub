import concurrent.futures as cf, re
from . import llm
from .config import LANGS, get_settings
from .keystore import PROVIDERS, load_keys
from . import quality
from .pool import POOL, call, NoKeys, Stopped

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
- Write EVERYTHING in the target language's own script. Transliterate every name and place; translate every title, rank and term (for example "mage" must become an Arabic word, never left in Latin letters). Never output words or characters from any other language or script (no Latin letters inside Arabic text, no Chinese, Japanese, Korean or Russian characters, no broken symbols).
- Translate every sentence completely. Do not skip, shorten or summarise anything.
FORMAT RULES (strict)
- The input is paragraphs, each starting with a marker like [P_12].
- Output exactly one translated paragraph per input paragraph, starting with the SAME marker, in the same order.
- Never merge, split, renumber or skip paragraphs. Output nothing but the marked paragraphs.
- Numbers, page numbers and symbols that need no translation: copy as-is after the marker."""
    if tgt == "ar":
        p += ("\n- Write fluent, elegant Modern Standard Arabic suitable for published literature, with Arabic punctuation (، ؛ ؟)."
              "\n- Use correct Arabic grammar. Numbers must agree with what they count: use the dual and plural forms correctly "
              "(say «قاعدتان» or «ثلاث قواعد», NEVER «اثنين قاعدة»). Do not translate word for word; avoid awkward calques.")
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


def _translate_chunk(chunk, sysmsg, stop=None, depth=0, avoid=None, temperature=0.2):
    """Returns (translations by id, producer by id). The producer is (key name, key id)."""
    user = "\n".join(f"[{u['id']}] {u['text'].replace(chr(10), ' ')}" for u in chunk)
    max_tok = min(8000, max(1024, int(len(user) * 1.3)))
    meta = {}
    try:
        text = call([{"role": "system", "content": sysmsg}, {"role": "user", "content": user}],
                    role="translate", max_tokens=max_tok, temperature=temperature, task="translate", stop=stop,
                    avoid=avoid, meta=meta)
    except llm.BadRequest:
        if len(chunk) > 1 and depth < 4:
            mid = len(chunk) // 2
            a, ab = _translate_chunk(chunk[:mid], sysmsg, stop, depth + 1, avoid, temperature)
            b, bb = _translate_chunk(chunk[mid:], sysmsg, stop, depth + 1, avoid, temperature)
            return {**a, **b}, {**ab, **bb}
        raise
    got = parse_response(text)
    who = (meta.get("name", "?"), meta.get("key_id", ""))
    by = {i: who for i in got}
    missing = [u for u in chunk if not got.get(u["id"])]
    if missing and depth < 3:
        parts = [missing] if len(missing) < len(chunk) else ([chunk[:len(chunk) // 2], chunk[len(chunk) // 2:]] if len(chunk) > 1 else [])
        for part in parts:
            g, b = _translate_chunk(part, sysmsg, stop, depth + 1, avoid, temperature)
            got.update(g)
            by.update(b)
    return got, by


def _translate_checked(chunk, sysmsg, stop, tgt):
    """Translate, check every paragraph, retry the bad ones (on another key, lower temperature), keep the best."""
    avoid = set()
    got, by = _translate_chunk(chunk, sysmsg, stop, avoid=avoid)
    first_bad = {u["id"] for u in chunk if u["id"] in got and quality.check(u["text"], got[u["id"]], tgt)}
    first_by = dict(by)
    for attempt in range(2):
        bad = [u for u in chunk if (u["id"] not in got) or quality.check(u["text"], got[u["id"]], tgt)]
        if not bad:
            break
        avoid.update(by[u["id"]][1] for u in bad if u["id"] in by)
        why = "؛ ".join(sorted({x for u in bad if u["id"] in got for x in quality.check(u["text"], got[u["id"]], tgt)}))
        note = (f"\n\nYOUR PREVIOUS ANSWER FOR SOME PARAGRAPHS HAD THESE PROBLEMS: {why or 'missing paragraphs'}. "
                "Translate them again, completely, using ONLY the target language's script. No foreign words or symbols.")
        try:
            g2, b2 = _translate_chunk(bad, sysmsg + note, stop, avoid=avoid, temperature=0.1)
        except (NoKeys, Stopped):
            raise
        except Exception:
            break
        for u in bad:
            i = u["id"]
            if i in g2 and (i not in got or len(quality.check(u["text"], g2[i], tgt)) <= len(quality.check(u["text"], got[i], tgt))):
                got[i], by[i] = g2[i], b2.get(i, by.get(i, ("?", "")))
    flags = {u["id"]: quality.check(u["text"], got[u["id"]], tgt) for u in chunk if u["id"] in got}
    return got, by, flags, first_bad, first_by


def _update_quality(chunk, by, first_bad):
    """Counts how often each key fails the first-pass checks and stops a key that keeps failing."""
    for u in chunk:
        if u["id"] not in by or not by[u["id"]][1]:
            continue
        kid = by[u["id"]][1]
        st = POOL.qstats.setdefault(kid, [0, 0])
        st[0] += 1
        st[1] += 1 if u["id"] in first_bad else 0
    from .keystore import load_keys
    keys = {k["id"]: k for k in load_keys()}
    for kid, (n, bad) in list(POOL.qstats.items()):
        if n >= 12 and bad / n >= 0.4 and kid not in POOL.quarantine and kid in keys:
            others = [k for k in keys.values() if k["id"] != kid and k.get("enabled") and k["id"] not in POOL.quarantine
                      and k.get("role", "both") in ("both", "translate")]
            if others:
                POOL.quarantine.add(kid)
                POOL.log(f"🚫 أوقفت «{keys[kid].get('label') or keys[kid]['provider']}» عن الترجمة تلقائياً: "
                         f"{bad} من {n} فقرة خرجت منه بأخطاء ظاهرة. بقية المفاتيح تكمل.", "warn")


def chunk_budget():
    ks = [k for k in load_keys() if k.get("enabled")]
    if not ks:
        return 4000
    return min(PROVIDERS[k["provider"]]["max_chars"] for k in ks)


def translate_all(units, src, tgt, ctx, style, golden, on_progress=None, should_stop=lambda: False):
    POOL.reset_quality()
    """Fills u['tr'] for every translatable unit. Resumable: units with a translation are skipped.
    on_progress(n_new_units, n_chunks_done, n_chunks_total) is called after every finished chunk."""
    sysmsg = system_prompt(src, tgt, ctx, style, golden)
    todo = [u for u in units if u.get("translate") and not u.get("tr")]
    chunks = make_chunks(todo, chunk_budget())
    total, done, fatal = len(chunks), 0, None
    by_id = {u["id"]: u for u in units}
    workers = max(1, min(get_settings()["max_workers"], len([k for k in load_keys() if k.get("enabled")]) * 3 or 1))
    ex = cf.ThreadPoolExecutor(workers)
    try:
        futs = {ex.submit(_translate_checked, c, sysmsg, should_stop, tgt): c for c in chunks}
        for f in cf.as_completed(futs):
            if should_stop():
                for g in futs:
                    g.cancel()
                break
            chunk, n_new = futs[f], 0
            try:
                got, by, flags, first_bad, first_by = f.result()
                _update_quality(chunk, first_by, first_bad)
            except NoKeys as e:
                fatal = str(e)
                for g in futs:
                    g.cancel()
                break
            except Stopped:
                got, by, flags = {}, {}, {}
            except Exception as e:  # keep going; failed paragraphs are retried on resume
                got, by, flags = {}, {}, {}
                for u in chunk:
                    u["error"] = str(e)[:200]
            for u in chunk:
                t = got.get(u["id"])
                if t:
                    by_id[u["id"]]["tr"] = t
                    by_id[u["id"]]["by"] = by.get(u["id"], ("", ""))[0]
                    fl = flags.get(u["id"])
                    if fl:
                        by_id[u["id"]]["flag"] = "؛ ".join(fl)
                    else:
                        by_id[u["id"]].pop("flag", None)
                    u.pop("error", None)
                    n_new += 1
            done += 1
            if on_progress:
                on_progress(n_new, done, total)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    if fatal:
        raise NoKeys(fatal)
    return sum(1 for u in units if u.get("translate") and not u.get("tr"))
