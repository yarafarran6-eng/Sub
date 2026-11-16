"""Moving paragraphs around on a page WITHOUT touching a single word.
- auto_spacing(): even gaps between the paragraphs (plain geometry, no AI).
- ai_ops(): the person asks in words («كلها بالمنتصف إلا الرابعة، نزّل الثالثة شوي»); the AI answers with a short list of MOVES taken
  from a fixed menu (never text); apply_ops() turns the moves into numbers (dx/dy) using the real positions on the page.
Everything is returned as {uid: (dx, dy)} in the SAME terms as the paragraph's own shift: dx to the right, dy downwards (points)."""
import json, re

VERBS = ("center_h", "center_v", "center_block_h", "center_block_v", "move", "align_left", "align_right", "align_top", "align_bottom",
         "distribute_v", "stack", "text_align", "reset")
ALIGNS = ("right", "left", "center", "justify")


def _sorted(rects):
    return sorted(rects, key=lambda t: (round(t[1][1] / 4), t[1][0]))


def auto_spacing(rects, page_h, obstacles=()):
    """rects: [(uid, [x0,y0,x1,y1])] as drawn. Each run of paragraphs between two pictures/ornaments keeps its first top and last bottom,
    and the free space inside is shared equally between the paragraphs. Paragraphs beside the main column (labels, side notes) stay put.
    -> {uid: dy_down}"""
    if len(rects) < 2:
        return {}
    widest = max(rects, key=lambda t: t[1][2] - t[1][0])[1]
    def overlap(r):
        w = min(r[2], widest[2]) - max(r[0], widest[0])
        return w > 0.5 * (r[2] - r[0])
    main = _sorted([t for t in rects if overlap(t[1])])
    cuts = sorted([(o[1], o[3]) for o in obstacles if (o[2] - o[0]) > 20])
    segs, cur = [], []
    for uid, r in main:
        mid = (r[1] + r[3]) / 2
        seg_id = sum(1 for a, b in cuts if (a + b) / 2 < mid)
        if cur and cur[0] != seg_id:
            segs.append(cur[1])
            cur = []
        if not cur:
            cur = [seg_id, []]
        cur[1].append((uid, r))
    if cur:
        segs.append(cur[1])
    out = {}
    for seg in segs:
        if len(seg) < 2:
            continue
        top, bottom = seg[0][1][1], max(r[3] for _, r in seg)
        used = sum(r[3] - r[1] for _, r in seg)
        gap = max((bottom - top - used) / (len(seg) - 1), 0.0)
        y = top
        for uid, r in seg:
            out[uid] = y - r[1]
            y += (r[3] - r[1]) + gap
    return {k: v for k, v in out.items() if abs(v) > 0.4}


def prompt(request, items, page):
    """items: [{"n","text","rect","size"}]. The text is only there so the AI knows which paragraph is «the title», «the date»..."""
    W, H = page
    rows = "\n".join(f"{it['n']}. [x0={it['rect'][0]:.0f} y0={it['rect'][1]:.0f} x1={it['rect'][2]:.0f} y1={it['rect'][3]:.0f} size={it['size']:.0f}] "
                     f"{(it['text'] or '')[:40].replace(chr(10), ' ')}" for it in items)
    return (
        "You arrange the PARAGRAPH BOXES on one page of a PDF. You never write, edit, translate or return any page text; you only choose moves.\n"
        f"Page: width={W:.0f}pt height={H:.0f}pt, origin top-left (y grows downwards). Paragraphs (number, box on the page, font size, first words):\n{rows}\n\n"
        f"The person's request (Arabic or English):\n{request}\n\n"
        "Answer with ONE JSON object only, no other text:\n"
        '{"ops":[{"who":"all"|[numbers],"except":[numbers],"do":VERB, ...extra fields}],"note":"one short Arabic sentence saying what you did"}\n'
        "VERB is exactly one of:\n"
        " center_h        each chosen paragraph is centred horizontally on the page\n"
        " center_v        each chosen paragraph is centred vertically on the page\n"
        " center_block_h  the chosen paragraphs together (keeping their distances) are centred horizontally\n"
        " center_block_v  the chosen paragraphs together (keeping their distances) are centred vertically\n"
        " move            extra fields dx, dy in points: dx>0 right, dx<0 left, dy>0 UP, dy<0 DOWN. «a little» = 8-12, «some» = 20-30, «a lot» = 50+\n"
        " align_left / align_right / align_top / align_bottom   line the chosen paragraphs up with the same edge of the paragraph number in field \"ref\"\n"
        "                 (no ref: with the outermost edge among the chosen ones)\n"
        " distribute_v    equal vertical gaps between the chosen paragraphs (first and last stay)\n"
        " stack           field gap in points: the chosen paragraphs one under the other with exactly this gap, starting at the first one's top\n"
        " text_align      field value = right | left | center | justify (alignment of the words inside the box)\n"
        " reset           the chosen paragraphs go back to their original place\n"
        '«who» may be "all" or a list of paragraph numbers; «except» (optional) removes numbers from it. Operations run in the order you list them.\n'
        'If the request asks to change/rewrite/translate words, or cannot be done with these moves, return {"ops":[],"note":"<why, in Arabic>"}.')


def parse(raw, n_items):
    """The AI's answer -> a clean list of ops. Unknown verbs, numbers out of range and every field that is not in the menu are dropped."""
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return [], "ما فهمت رد الذكاء الاصطناعي"
    try:
        data = json.loads(m.group(0))
    except Exception:
        return [], "رد الذكاء الاصطناعي ما كان مرتباً"
    ops = []
    def nums(v):
        if v == "all":
            return list(range(1, n_items + 1))
        if isinstance(v, int):
            v = [v]
        return [int(x) for x in v if isinstance(x, (int, float)) and 1 <= int(x) <= n_items] if isinstance(v, list) else []
    for o in data.get("ops") or []:
        if not isinstance(o, dict) or o.get("do") not in VERBS:
            continue
        who = [x for x in nums(o.get("who", "all")) if x not in set(nums(o.get("except") or []))]
        if not who:
            continue
        c = {"do": o["do"], "who": who}
        for k in ("dx", "dy", "gap"):
            if isinstance(o.get(k), (int, float)):
                c[k] = max(-2000.0, min(2000.0, float(o[k])))
        if isinstance(o.get("ref"), int) and 1 <= o["ref"] <= n_items:
            c["ref"] = o["ref"]
        if o["do"] == "text_align":
            if o.get("value") not in ALIGNS:
                continue
            c["value"] = o["value"]
        ops.append(c)
    note = data.get("note") if isinstance(data.get("note"), str) else ""
    return ops, note[:200]


def apply_ops(ops, rects, page, offs=None):
    """rects: {n: [x0,y0,x1,y1]} (n = paragraph number as shown); offs: {n: (dx, dy)} the shifts the paragraphs already have (for «reset»).
    Returns ({n: [dx_right, dy_down]}, {n: align}), both relative to now."""
    W, H = page
    cur = {n: list(r) for n, r in rects.items()}
    moved = {n: [0.0, 0.0] for n in rects}
    aligns = {}

    def shift(n, dx, dy):
        r = cur[n]
        r[0] += dx; r[2] += dx; r[1] += dy; r[3] += dy
        moved[n][0] += dx; moved[n][1] += dy

    for o in ops:
        who = [n for n in o["who"] if n in cur]
        if not who:
            continue
        v = o["do"]
        if v == "center_h":
            for n in who:
                shift(n, W / 2 - (cur[n][0] + cur[n][2]) / 2, 0)
        elif v == "center_v":
            for n in who:
                shift(n, 0, H / 2 - (cur[n][1] + cur[n][3]) / 2)
        elif v in ("center_block_h", "center_block_v"):
            lo = [min(cur[n][i] for n in who) for i in (0, 1)]
            hi = [max(cur[n][i] for n in who) for i in (2, 3)]
            for n in who:
                shift(n, (W / 2 - (lo[0] + hi[0]) / 2) if v == "center_block_h" else 0,
                      (H / 2 - (lo[1] + hi[1]) / 2) if v == "center_block_v" else 0)
        elif v == "move":
            for n in who:
                shift(n, o.get("dx", 0.0), -o.get("dy", 0.0))
        elif v in ("align_left", "align_right", "align_top", "align_bottom"):
            ref = cur.get(o.get("ref"))
            i = {"align_left": 0, "align_right": 2, "align_top": 1, "align_bottom": 3}[v]
            tgt = ref[i] if ref else (min if i < 2 else max)(cur[n][i] for n in who)
            for n in who:
                d = tgt - cur[n][i]
                shift(n, d if i in (0, 2) else 0, d if i in (1, 3) else 0)
        elif v == "distribute_v" and len(who) > 2:
            seq = sorted(who, key=lambda n: cur[n][1])
            top, bottom = cur[seq[0]][1], max(cur[n][3] for n in seq)
            gap = (bottom - top - sum(cur[n][3] - cur[n][1] for n in seq)) / (len(seq) - 1)
            y = top
            for n in seq:
                shift(n, 0, y - cur[n][1])
                y += cur[n][3] - cur[n][1] + max(gap, 0.0)
        elif v == "stack":
            seq = sorted(who, key=lambda n: cur[n][1])
            y = cur[seq[0]][1]
            for n in seq:
                shift(n, 0, y - cur[n][1])
                y += cur[n][3] - cur[n][1] + o.get("gap", 10.0)
        elif v == "text_align":
            for n in who:
                aligns[n] = o["value"]
        elif v == "reset":
            for n in who:
                ox, oy = (offs or {}).get(n, (0.0, 0.0))
                shift(n, -(ox + moved[n][0]), -(oy + moved[n][1]))
    return moved, aligns
