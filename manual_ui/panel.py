"""The style panel: ONE grid of options that applies either to the whole page or to one chosen paragraph."""
import time
import gradio as gr
from core import manual
from ui.common import safe, toast
from .consts import BG_PRESETS, DELTA, HL_DEFAULT
from .data import items_now, need, orig_page
from .reg import R

PAGE, PARA = "page", "para"
SCOPES = [("الصفحة كلها", PAGE), ("فقرة واحدة", PARA)]
# which stored keys each option owns
KEYS = {PAGE: {"font": ["font"], "size": ["scale"], "align": ["align"], "tcolor": ["tcolor"], "hl": ["hl"], "pos": ["dx", "dy"], "bg": ["bg"]},
        PARA: {"font": ["font"], "size": ["size"], "align": ["align"], "tcolor": ["tcolor"], "hl": ["hl"], "pos": ["dx", "dy"]}}
NAMES = {"font": "الخط", "size": "حجم الخط", "align": "المحاذاة", "tcolor": "لون النص", "hl": "لون التحديد", "pos": "المكان", "bg": "الخلفية"}


def _target(d, allit, cur, scope, pn):
    """-> (prefix list in the draft, kind label) or raises a clear error."""
    p = orig_page(d, cur)
    if p is None:
        raise gr.Error("التنسيق متاح فقط للصفحات الأصلية داخل نطاق الترجمة. هذي الصفحة مستوردة أو فارغة أو خارج النطاق.", title="لا يمكن التنسيق هنا")
    if scope == PAGE:
        return ["pstyle", str(p)]
    n = int(pn or 0)
    if not 1 <= n <= len(allit):
        raise gr.Error(f"اكتب رقم فقرة بين 1 و {len(allit)} (الأرقام ظاهرة فوق كل فقرة)", title="رقم الفقرة غير صحيح")
    return ["ustyle", allit[n - 1]["uid"]]


SHORT = ("font", "size", "align", "tOn", "tc", "hOn", "hc", "dx", "dy")


def values(d, allit, e, scope, pn, px):
    """What the controls named px+... show now. px is "p_" for the page block and "s<i>_" for the block under paragraph i."""
    u = gr.update
    if not (e and e["k"] == "o" and e.get("tr_on")):
        return {}
    if scope == PAGE:
        s = d["pstyle"].get(str(e["p"]), {})
        bg = s.get("bg") or {}
        vals = [s.get("font", ""), s.get("scale", 100), s.get("align", ""), bool(s.get("tcolor")), s.get("tcolor") or "#000000",
                bool(s.get("hl")), s.get("hl") or HL_DEFAULT, s.get("dx", 0) or 0, s.get("dy", 0) or 0]
        extra = R(bg_mode=u(value=bg.get("mode", "none")), bg_c1=u(value=bg.get("c1", "#ffffff")),
                  bg_c2=u(value=bg.get("c2", "#cccccc")), bg_dir=u(value=bg.get("dir", "vertical")))
    else:
        n = int(pn or 1)
        if not 1 <= n <= len(allit):
            return {}
        it = allit[n - 1]
        vals = [it["font"] or "", it["size"] or 0, it["align"] or "", bool(it["tcolor"]), it["tcolor"] or it["def_color"],
                bool(it["hl"]), it["hl"] or HL_DEFAULT, it["dx"] or 0, it["dy"] or 0]
        extra = {}
    out = R(**{px + k: u(value=v) for k, v in zip(SHORT, vals)})
    out.update(extra)
    return out


def _now(pid, did, cur, grp, scope, pn):
    meta, units, d, eff, allit, items = items_now(pid, did, cur, grp)
    e = eff[int(cur)] if eff and 0 <= int(cur) < len(eff) else None
    return d, allit, e


@safe
def apply(pid, did, cur, grp, scope, pn, font, size, align, tOn, tc, hOn, hc, dx, dy, bgm, c1, c2, bgd):
    if not pid:
        return R(saved="")
    with manual._lock:
        d, allit, e = _now(pid, did, cur, grp, scope, pn)
        pre = _target(d, allit, cur, scope, pn)
        if scope == PAGE:
            bg = {"mode": bgm, "c1": c1, "c2": c2, "dir": bgd} if bgm and bgm != "none" else None
            manual.set_pstyle(d, int(pre[1]), font=font or None, scale=(float(size) if size and float(size) != 100 else None),
                              tcolor=tc if tOn else None, hl=hc if hOn else None, bg=bg, align=align or None,
                              dx=float(dx or 0), dy=float(dy or 0))
        else:
            manual.set_ustyle(d, pre[1], font=font or None, size=float(size or 0), tcolor=tc if tOn else None,
                              hl=hc if hOn else None, dx=float(dx or 0), dy=float(dy or 0), align=align or None)
        manual.save_draft(pid, d)
    return R(saved=f"🎨 حُفظ التنسيق {time.strftime('%H:%M:%S')}", last=_last(d))


def _last(d):
    x = manual.last_label(d)
    return f"آخر تغيير: {x}" if x else "لا توجد تغييرات للتراجع عنها"


@safe
def reset(pid, did, cur, grp, scope, pn, which, px):
    """«إعادة تعيين»: the option goes back to the original file's value."""
    need(pid)
    with manual._lock:
        d, allit, e = _now(pid, did, cur, grp, scope, pn)
        pre = _target(d, allit, cur, scope, pn)
        tx = manual.Tx(d, f"إعادة تعيين {NAMES[which]}")
        for k in KEYS[scope][which]:
            tx.set(*pre, k, value=manual.MISSING)
        tx.commit()
        manual.save_draft(pid, d)
    toast(f"رجع «{NAMES[which]}» إلى قيمة الملف الأصلي.")
    return {**values(d, allit, e, scope, pn, px), **R(last=_last(d))}


@safe
def stepback(pid, did, cur, grp, scope, pn, which, px):
    """«تراجع خطوة»: undoes only the LAST change of this one option; other options stay."""
    need(pid)
    with manual._lock:
        d, allit, e = _now(pid, did, cur, grp, scope, pn)
        pre = _target(d, allit, cur, scope, pn)
        got = None
        for k in KEYS[scope][which]:
            got = manual.undo_option(d, *pre, k) or got
        manual.save_draft(pid, d)
    if got:
        toast(f"تراجعت خطوة واحدة في «{NAMES[which]}» فقط.")
    else:
        toast(f"ما فيه تغيير سابق في «{NAMES[which]}» أتراجع عنه.", warn=True)
    return {**values(d, allit, e, scope, pn, px), **R(last=_last(d))}


@safe
def move(pid, did, cur, grp, scope, pn, dirn, step, px):
    need(pid)
    st = float(step or 5)
    with manual._lock:
        d, allit, e = _now(pid, did, cur, grp, scope, pn)
        pre = _target(d, allit, cur, scope, pn)
        us = (d["pstyle"] if pre[0] == "pstyle" else d["ustyle"]).get(pre[1], {})
        dx = round(float(us.get("dx", 0) or 0) + DELTA[dirn][0] * st, 2)
        dy = round(float(us.get("dy", 0) or 0) + DELTA[dirn][1] * st, 2)
        (manual.set_pstyle(d, int(pre[1]), dx=dx, dy=dy) if pre[0] == "pstyle" else manual.set_ustyle(d, pre[1], dx=dx, dy=dy))
        manual.save_draft(pid, d)
    return R(**{px + "dx": dx, px + "dy": dy}, saved=f"⬌ الإزاحة الآن: أفقي {dx} ورأسي {dy} نقطة.", last=_last(d))


@safe
def preset(pid, did, cur, grp, scope, pn, name):
    need(pid)
    if scope != PAGE:
        raise gr.Error("الخلفية للصفحة كلها فقط. اختر «الصفحة كلها» في اللوحة.", title="الخلفية للصفحة")
    mode, c1, c2, dr = BG_PRESETS[name]
    with manual._lock:
        d, allit, e = _now(pid, did, cur, grp, scope, pn)
        pre = _target(d, allit, cur, scope, pn)
        manual.set_pstyle(d, int(pre[1]), bg={"mode": mode, "c1": c1, "c2": c2, "dir": dr} if mode != "none" else None)
        manual.save_draft(pid, d)
    toast("طُبّقت الخلفية.")
    return R(bg_mode=mode, bg_c1=c1, bg_c2=c2, bg_dir=dr, last=_last(d))


@safe
def reset_everything(pid, did, cur, grp):
    """Every style of the page (page options + all its paragraphs + background) back to the original."""
    need(pid)
    with manual._lock:
        meta, units, d = manual.load(pid)[0], manual.load(pid)[1], manual.load_draft(pid, did)
        p = orig_page(d, cur)
        if p is None:
            raise gr.Error("هذي ليست صفحة أصلية", title="لا يمكن")
        manual.reset_page(d, p, units)
        manual.save_draft(pid, d)
    from .view import view
    return view(pid, did, cur, grp, "رجعت الصفحة كلها (خطوط وأحجام وألوان وخلفية ومواضع) إلى الأصل.")
