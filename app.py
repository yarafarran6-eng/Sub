import html, os, shutil
import gradio as gr
from core import auth, jobs, editor, builder, llm, modelpick, monitor
from core.config import JOBS, get_settings, update_settings
from core.keystore import (ADDRESS_CHOICES, PROVIDERS, PROVIDER_LABELS, add_key_generic, detect_base, delete_key, detect_provider,
                           load_keys, mask, provider_from_base, update_key)
from core.pool import POOL, human, kname

E = html.escape
LANG_CHOICES = [("العربية", "ar"), ("English", "en"), ("日本語", "ja")]
SRC_CHOICES = [("كشف تلقائي", "auto")] + LANG_CHOICES
SENS_CHOICES = [("صارم: الأخطاء الفادحة فقط", "strict"), ("متوسط: مع الركاكة والتناقض", "medium"),
                ("دقيق: مع النبرة والأسلوب", "precise")]
ROLE_CHOICES = [("ترجمة وتدقيق", "both"), ("ترجمة فقط", "translate"), ("تدقيق فقط", "edit")]


def opt(title, what, benefit, how):
    """A collapsed explanation block: the arrow shows/hides it."""
    return gr.HTML(
        f"<details class='opt'><summary><span>{title}</span></summary><div class='b'>"
        f"<p><b>ماذا يفعل:</b> {what}</p><p><b>الفائدة:</b> {benefit}</p><p><b>كيف أستخدمه:</b> {how}</p>"
        f"</div></details>", elem_classes="optwrap")


def guard():
    if auth.must_change():
        raise gr.Error("غيّر كلمة السر الأولية من تبويب الإعدادات أولاً")


# ------------------------------------------------------------------ header / banner
def hero_html():
    ks = [k for k in load_keys() if k.get("enabled")]
    s = get_settings()
    js = jobs.list_jobs()
    run = sum(1 for m in js if m.get("status") == "running")
    return ("<div class='hero'><div><h1>مترجم الروايات</h1>"
            "<p>ارفع الملف، وخلّ المفاتيح تترجم بالتوازي، وراجع الناتج قبل التصدير.</p></div>"
            f"<div class='chips'><span class='hchip'>🔑 مفاتيح مفعّلة: {len(ks)}</span>"
            f"<span class='hchip'>📚 ملفات: {len(js)}{f' (يعمل {run})' if run else ''}</span>"
            f"<span class='hchip'>💰 المصروف: {s['spent_usd']:.3f}$ من {s['budget_usd']}$</span></div></div>")


def banner_html():
    if auth.must_change():
        return "<div class='warnbox'>⚠ غيّر كلمة السر الأولية (2222) من تبويب «٤. الإعدادات» قبل أي شي.</div>"
    if not [k for k in load_keys() if k.get("enabled")]:
        return "<div class='warnbox'>⚠ ما أضفت أي مفتاح. افتح تبويب «١. المفاتيح» وأضف مفتاحاً واحداً على الأقل.</div>"
    return "<div class='okbox'>✓ جاهز. ارفع ملفاً من تبويب «٢. الترجمة».</div>"


# ------------------------------------------------------------------ keys
def key_choices():
    return [(f"{kname(k)} · {mask(k['key'])} [{k['id']}]", k["id"]) for k in load_keys()]


def _models_text(ids, current):
    return "النماذج المتاحة عندهم: " + "، ".join(ids[:14]) + (" ..." if len(ids) > 14 else "")


def test_key(k):
    """Tests a key and ALWAYS says why it failed. Returns (ok, message)."""
    name, model = kname(k), k.get("model", "")
    base = k.get("base") or PROVIDERS[k["provider"]]["base"]
    try:
        llm.chat(k, [{"role": "user", "content": "Reply with the single word OK"}], 20, 0, "ping", 60)
        POOL.revive(k["id"])
        POOL.mark_verified(k["id"], True)
        return True, f"✅ «{name}» شغّال."
    except llm.RateLimited as e:
        if e.reason == "zero":
            reason = (f"الحصة المجانية لنموذج «{model or 'تلقائي'}» تساوي صفر عندهم، فهو غير متاح بدون دفع أو غير مفعّل لمفتاحك. "
                      f"جرّب «اختيار النموذج تلقائياً». رد الخدمة: {e.detail}")
            POOL.mark_verified(k["id"], False, reason)
            return False, f"❌ «{name}»: {reason}"
        POOL.revive(k["id"])
        POOL.mark_verified(k["id"], True)
        kind = "اليومي" if e.reason == "day" else "حد الدقيقة"
        return True, (f"⚠ «{name}» صحيح لكن الخدمة ردّت بأنه وصل الحد {kind}، ويرجع بعد {human(e.retry_after)}. "
                      f"رد الخدمة: {e.detail}")
    except llm.KeyDead as e:
        POOL.kill(k, str(e))
        return False, f"❌ «{name}»: المفتاح مرفوض أو بدون صلاحية. رد الخدمة: {e}"
    except llm.BadRequest as e:
        s_, low = str(e), str(e).lower()
        if s_.startswith("404") or "not found" in low or "does not exist" in low:
            ids, err = None, ""
            try:
                ids = llm.list_models(k["provider"], k.get("key", ""), base)
            except Exception as ex:
                err = str(ex)
            if ids and model not in ids:
                reason = f"اسم النموذج «{model}» غير موجود عند هذه الخدمة. " + _models_text(ids, model)
            elif ids is None:
                reason = f"العنوان أو اسم النموذج غير صحيح (404). رد الخدمة: {s_}. وتعذر جلب قائمة النماذج: {err}"
            else:
                reason = f"رد الخدمة: {s_}"
        elif s_.startswith("402") or any(w in low for w in ("quota", "billing", "insufficient", "credit", "balance", "payment")):
            reason = f"الرصيد أو الحصة غير كافية. رد الخدمة: {s_}"
        else:
            reason = f"الخدمة رفضت الطلب. رد الخدمة: {s_}"
        POOL.mark_verified(k["id"], False, reason)
        return False, f"❌ «{name}»: {reason}"
    except llm.Transient as e:
        POOL.mark_verified(k["id"], False, str(e))
        return False, f"❌ «{name}»: {e}"
    except Exception as e:
        reason = f"خطأ غير متوقع ({type(e).__name__}): {str(e)[:160]}"
        POOL.mark_verified(k["id"], False, reason)
        return False, f"❌ «{name}»: {reason}"


def auto_model(k):
    """Lets the site choose a working model for this key. Returns (ok, message)."""
    name = kname(k)
    res = modelpick.auto_pick(k)
    if res["ok"]:
        update_key(k["id"], model=res["model"])
        POOL.revive(k["id"])
        POOL.mark_verified(k["id"], True)
        shown = f"«{res['model']}»" if res["model"] else "(بدون اسم، الخدمة تختار بنفسها)"
        return True, (f"✅ «{name}» شغّال. اخترت له النموذج {shown} تلقائياً. "
                      "تقدر تغيّره من «إدارة مفتاح». لو خدمتك مدفوعة وتبي تتحكم بالتكلفة، اكتب النموذج بنفسك.")
    if res["kind"] == "key":
        POOL.kill(k, res["reason"])
    else:
        POOL.mark_verified(k["id"], False, res["reason"])
    return False, f"❌ «{name}»: {res['reason']}"


def fetch_models_ui(addr, key):
    addr = (addr or "").strip()
    if not addr:
        return gr.update(), "❌ اختر الخدمة أو اكتب عنوانها أولاً."
    try:
        ids = llm.list_models(provider_from_base(addr), (key or "").strip(), addr)
    except llm.KeyDead as e:
        return gr.update(), f"❌ المفتاح مرفوض. رد الخدمة: {e}"
    except Exception as e:
        return gr.update(), f"❌ تعذر جلب القائمة: {e}. تقدر تكتب اسم النموذج بيدك."
    if not ids:
        return gr.update(), "ما رجعت الخدمة أي نموذج. اكتب اسم النموذج بيدك."
    return gr.update(choices=ids, value=None), f"✅ وجدت {len(ids)} نموذج. اختر واحداً من خانة النموذج."


def fetch_models_for_key(kid):
    k = next((x for x in load_keys() if x["id"] == kid), None)
    if not k:
        raise gr.Error("اختر مفتاحاً من القائمة")
    return fetch_models_ui(k.get("base") or PROVIDERS[k["provider"]]["base"], k.get("key", ""))


def on_key_change(key, addr):
    base = detect_base(key)
    if base and not (addr or "").strip():
        return gr.update(value=base)
    return gr.update()


def add_key_ui(name, key, addr, model, role, paid, pin, pout, rpm):
    guard()
    addr, key = (addr or "").strip(), (key or "").strip()
    if not addr:
        raise gr.Error("اختر الخدمة من القائمة، أو الصق عنوانها")
    if not addr.startswith("http"):
        raise gr.Error("العنوان لازم يبدأ بـ http أو https")
    warn = ""
    det = detect_base(key)
    if det and det.rstrip("/") != addr.rstrip("/"):
        warn = "\n\n⚠ شكل المفتاح يدل على خدمة ثانية غير العنوان اللي اخترته. لو فشل الاختبار فهذا غالباً السبب."
    entry = add_key_generic(name, key, addr, (model or "").strip(), role, paid, pin, pout, rpm)
    if (model or "").strip():
        ok, msg = test_key(entry)
    else:
        ok, msg = auto_model(entry)
    return "", "", key_panel(), gr.update(choices=key_choices()), msg + warn


def key_panel():
    return monitor.keys_html()


def key_action(kid, what, newval=""):
    guard()
    if not kid:
        raise gr.Error("اختر مفتاحاً من القائمة")
    k = next((x for x in load_keys() if x["id"] == kid), None)
    msg = "تم"
    if what == "delete":
        if k and k.get("env"):
            msg = "هذا المفتاح قادم من إعدادات الاستضافة، احذفه من هناك."
        else:
            delete_key(kid)
            msg = "🗑 حُذف المفتاح."
    elif what in ("toggle", "rename", "model") and k and k.get("env"):
        msg = "هذا المفتاح قادم من إعدادات الاستضافة، عدّله من هناك."
    elif what == "toggle" and k:
        update_key(kid, enabled=not k.get("enabled"))
        POOL.revive(kid)
        msg = "تم التفعيل." if not k.get("enabled") else "تم الإيقاف المؤقت."
    elif what == "test" and k:
        ok, msg = test_key(k)
    elif what == "rename" and k:
        if not (newval or "").strip():
            raise gr.Error("اكتب الاسم الجديد")
        update_key(kid, label=newval.strip())
        msg = f"✏ صار الاسم «{newval.strip()}»."
    elif what == "auto" and k:
        ok, msg = auto_model(k)
    elif what == "model" and k:
        if not (newval or "").strip():
            raise gr.Error("اختر النموذج الجديد أو اكتب اسمه، أو اضغط «اختيار النموذج تلقائياً»")
        update_key(kid, model=newval.strip())
        POOL.revive(kid)
        ok, msg = test_key(next(x for x in load_keys() if x["id"] == kid))
        msg = "غيّرت النموذج. " + msg
    return key_panel(), gr.update(choices=key_choices(), value=None if what == "delete" else kid), msg


def test_all():
    guard()
    out = []
    for k in load_keys():
        if k.get("enabled"):
            ok, m = test_key(k)
            out.append(f"- {m}")
    return key_panel(), "\n".join(out) or "ما فيه مفاتيح"


# ------------------------------------------------------------------ jobs
def job_choices():
    return [(f"{m['name']}  [{m['id']}]  {m.get('stage', '')}", m["id"]) for m in jobs.list_jobs()]


def add_jobs(files, src, tgt, style, golden, sens):
    guard()
    if not files:
        raise gr.Error("ارفع ملفاً واحداً على الأقل")
    if not [k for k in load_keys() if k.get("enabled")]:
        raise gr.Error("ما فيه مفاتيح مفعّلة. أضفها من تبويب «١. المفاتيح»")
    if src == tgt:
        raise gr.Error("لغة المصدر والهدف متطابقتان")
    ids = [jobs.create(f if isinstance(f, str) else f.name, src, tgt, style, golden, sens) for f in files]
    return f"✅ أُضيف {len(ids)} ملف للطابور وبدأت المعالجة. تابعها من لوحة المتابعة أدناه.", gr.update(choices=job_choices(), value=ids[0])


def job_action(jid, what):
    guard()
    if not jid:
        raise gr.Error("اختر ملفاً من القائمة")
    msgs = {"queued": "✅ رجع للطابور وبيكمل من حيث وقف.",
            "already_running": "ℹ الملف يعمل الآن، ما يحتاج استكمال. تابعه من لوحة المتابعة.",
            "already_queued": "ℹ الملف في الطابور فعلاً وينتظر دوره.",
            "will_resume": "⏳ جاري الإيقاف، وبيستأنف تلقائياً بعد ثواني."}
    if what == "resume":
        msg = msgs[jobs.enqueue(jid)]
    elif what == "stop":
        jobs.cancel(jid)
        msg = "⏹ جاري الإيقاف. قد ياخذ ثواني لين تنتهي الطلبات الجارية، وبعدها اضغط استكمال متى ما بغيت."
    else:
        jobs.delete(jid)
        msg = "🗑 حُذف الملف."
    return gr.update(choices=job_choices(), value=None if what == "delete" else jid), msg


def tick(jid):
    return hero_html(), banner_html(), monitor.jobs_html(), monitor.monitor_html(jid), monitor.keys_html(), monitor.events_html()


# ------------------------------------------------------------------ review
def load_review(jid):
    guard()
    if not jid:
        raise gr.Error("اختر ملفاً")
    meta, units = jobs.load(jid)
    rows = [[u["id"], u["page"] + 1, u["text"], u.get("tr", "")] for u in units if u.get("translate")]
    return rows, meta.get("ctx", ""), f"تم تحميل **{len(rows)}** فقرة. الحالة: {meta.get('stage')}"


def save_review(jid, rows, ctx):
    guard()
    meta, units = jobs.load(jid)
    by = {u["id"]: u for u in units}
    n = 0
    for r in rows.values.tolist() if hasattr(rows, "values") else rows:
        u = by.get(r[0])
        if u and (r[3] or "") != u.get("tr", ""):
            u["tr"] = r[3] or ""
            n += 1
    jobs.save_units(jid, units)
    jobs.set_state(jid, ctx=ctx)
    return f"💾 حُفظ {n} تعديل"


def run_chat(jid, instruction, rows):
    guard()
    if not instruction.strip():
        raise gr.Error("اكتب التعليمة")
    save_review(jid, rows, jobs.load(jid)[0].get("ctx", ""))
    meta, units = jobs.load(jid)
    patches = editor.run_instruction(units, instruction, meta["src"], meta["tgt"], meta["ctx"], meta["style"])
    jobs.save_units(jid, units)
    log = "\n".join(f"- {p['id']}: {p['why']}" for p in patches[:40]) or "ما احتاج أي فقرة تعديل"
    new_rows, _, _ = load_review(jid)
    return new_rows, f"✏ عُدّلت **{len(patches)}** فقرة\n\n{log}"


def do_replace(jid, find, repl):
    guard()
    if not find:
        raise gr.Error("اكتب الكلمة المراد استبدالها")
    meta, units = jobs.load(jid)
    n = editor.find_replace(units, find, repl)
    jobs.save_units(jid, units)
    rows, _, _ = load_review(jid)
    return rows, f"🔁 استُبدلت **{n}** مرة"


def generate(jid, rows, ctx, want_pdf, want_epub, want_txt):
    guard()
    save_review(jid, rows, ctx)
    meta, units = jobs.load(jid)
    out = JOBS / jid / "out"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    base = os.path.splitext(meta["name"])[0] + f"_{meta['tgt']}"
    files, notes = [], []
    if want_pdf:
        if meta.get("kind") == "pdf":
            info = builder.build_pdf(str(JOBS / jid / "source.pdf"), units, meta["tgt"], str(out / (base + ".pdf")))
            files.append(str(out / (base + ".pdf")))
            notes.append(f"PDF: {info['pages']} صفحة، وصُغّر خط {info['shrunk_blocks']} فقرة ليتسع النص")
        else:
            notes.append("PDF متاح فقط للملفات الأصلية PDF، استخدم EPUB")
    if want_epub and builder.build_epub(units, meta["tgt"], os.path.splitext(meta["name"])[0], str(out / (base + ".epub"))):
        files.append(str(out / (base + ".epub")))
    if want_txt:
        builder.build_txt(units, str(out / (base + ".txt")))
        files.append(str(out / (base + ".txt")))
    return files, "✅ " + ("، ".join(notes) or "تم توليد الملفات")


# ------------------------------------------------------------------ settings
def save_budget(usd, reset):
    guard()
    s = update_settings(budget_usd=float(usd), **({"spent_usd": 0.0} if reset else {}))
    return f"السقف {s['budget_usd']}$ · المصروف {s['spent_usd']}$"


CSS = """
.gradio-container{direction:rtl;max-width:1120px!important;margin:auto!important;font-family:'Segoe UI',Tahoma,'Noto Naskh Arabic',sans-serif}
footer{display:none!important}
textarea,input[type=text]{unicode-bidi:plaintext;border-radius:10px!important}
.ltr textarea{direction:ltr;text-align:left}
.hero{display:flex;flex-wrap:wrap;gap:14px;justify-content:space-between;align-items:center;padding:22px 24px;border-radius:18px;
 background:linear-gradient(135deg,#4338ca,#7c3aed);color:#fff;margin-bottom:10px}
.hero h1{margin:0;font-size:1.7em;color:#fff}.hero p{margin:6px 0 0;opacity:.9}
.chips{display:flex;flex-wrap:wrap;gap:8px}.hchip{background:rgba(255,255,255,.18);padding:6px 12px;border-radius:99px;font-size:.9em}
.warnbox,.okbox,.infobox{padding:12px 16px;border-radius:12px;margin:8px 0;line-height:1.8}
.warnbox{background:#f59e0b22;border:1px solid #f59e0b88}.okbox{background:#16a34a22;border:1px solid #16a34a77}
.infobox{background:#6366f122;border:1px solid #6366f177}
.step{display:flex;gap:10px;align-items:center;font-size:1.15em;font-weight:700;margin:10px 0 4px}
.step i{background:#6366f1;color:#fff;border-radius:50%;width:30px;height:30px;display:inline-flex;align-items:center;justify-content:center;font-style:normal}
.hint{opacity:.8;margin:0 0 10px;line-height:1.8}
.optwrap{padding:0!important;margin:10px 0 2px!important;border:none!important;background:none!important}
details.opt{border-radius:10px}
details.opt summary{cursor:pointer;list-style:none;display:flex;justify-content:space-between;align-items:center;font-weight:700;padding:6px 2px}
details.opt summary::-webkit-details-marker{display:none}
details.opt summary::after{content:'▾';font-size:1.2em;opacity:.7;transition:transform .2s}
details.opt[open] summary::after{transform:rotate(180deg)}
details.opt .b{background:#6366f118;border-right:4px solid #6366f1;border-radius:10px;padding:8px 14px;margin:4px 0 6px;line-height:1.9;font-size:.93em}
details.opt .b p{margin:6px 0}
button.primary{min-height:50px;font-size:1.05em!important;border-radius:12px!important;font-weight:700!important}
button[role=tab]{font-weight:700!important;font-size:1.02em!important}
.job,.mon{border:1px solid var(--border-color-primary);border-radius:14px;padding:14px 16px;margin:8px 0;background:var(--background-fill-secondary)}
.jhead,.mhead{display:flex;justify-content:space-between;align-items:center;gap:10px}
.bar{height:9px;border-radius:99px;background:var(--border-color-primary);overflow:hidden;margin:10px 0}
.bar.big{height:14px}.bar i{display:block;height:100%;background:linear-gradient(90deg,#6366f1,#a78bfa);transition:width .6s}
.jmeta,.sub{opacity:.75;font-size:.88em}.jid{margin-right:10px;opacity:.6}.jnote{margin-top:6px;font-size:.9em;color:#d97706}
.chip{padding:3px 11px;border-radius:99px;font-size:.82em;font-weight:700;background:#9ca3af33;white-space:normal}
.st-running,.k-busy{background:#6366f133;color:#818cf8}.st-ready,.k-ok{background:#16a34a2e;color:#22c55e}
.st-partial,.st-stopped,.k-wait,.k-new{background:#f59e0b2e;color:#f59e0b}.st-error,.k-bad{background:#ef44442e;color:#f87171}
.stage{font-size:1.25em;font-weight:800;margin-top:8px}.what{opacity:.85;margin:4px 0;line-height:1.8}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:8px}
.tile{border:1px solid var(--border-color-primary);border-radius:12px;padding:10px 12px}
.tt{opacity:.7;font-size:.82em}.tv{font-size:1.3em;font-weight:800;margin:2px 0}.ts{opacity:.6;font-size:.78em}
.tbl{overflow-x:auto}.tbl table{width:100%;border-collapse:collapse}
.tbl th,.tbl td{text-align:right;padding:9px 10px;border-bottom:1px solid var(--border-color-primary);vertical-align:top}
.events{max-height:300px;overflow:auto;border:1px solid var(--border-color-primary);border-radius:12px;padding:6px 10px}
.ev{padding:5px 0;border-bottom:1px dashed var(--border-color-primary);font-size:.9em;line-height:1.7}
.ev span{opacity:.55;margin-left:8px;font-family:monospace}.ev.warn{color:#f59e0b}.ev.error{color:#f87171}
.empty{padding:22px;text-align:center;opacity:.7;border:1px dashed var(--border-color-primary);border-radius:12px}
"""

THEME = gr.themes.Soft(primary_hue="indigo", secondary_hue="violet", neutral_hue="slate")


def step(n, title, hint=""):
    return gr.HTML(f"<div class='step'><i>{n}</i>{title}</div>" + (f"<p class='hint'>{hint}</p>" if hint else ""))


with gr.Blocks(title="مترجم الروايات") as demo:
    hero = gr.HTML(hero_html)
    banner = gr.HTML(banner_html)
    with gr.Tabs():
        # ============================================================ 1. KEYS
        with gr.Tab("١. المفاتيح"):
            step("أ", "أضف مفتاحاً", "تعطي الموقع: اسماً تختاره، والمفتاح، وعنوان الخدمة، وهو يختار النموذج بنفسه. أي خدمة تدعم الطريقة المعيارية (OpenAI) تشتغل، مو بس اللي في القائمة. المفاتيح تُحفظ على جهازك فقط.")
            opt("الاسم", "اسم تختاره أنت عشان تعرف المفتاح، مثل «سيارة» أو «فيصل» أو «جيميني الأول».",
                "يظهر في الجداول والتنبيهات، وما له علاقة باسم النموذج.", "اكتب أي اسم. لو تركته فارغاً يسمّيه الموقع باسم عنوان الخدمة.")
            k_name = gr.Textbox(show_label=False, placeholder="مثال: سيارة، فيصل، جيميني الأول")
            opt("المفتاح", "الرمز السري اللي تعطيك إياه الخدمة.", "بدونه ما تقبل الخدمة الطلبات (إلا الخدمات المحلية).",
                "الصقه هنا. لو الخدمة محلية بدون مفتاح، مثل Ollama، اتركه فارغاً.")
            k_key = gr.Textbox(show_label=False, type="password", placeholder="الصق المفتاح هنا (اتركه فارغاً للخدمات المحلية)")
            opt("عنوان الخدمة", "الرابط اللي يرسل له الموقع الطلبات.",
                "تستخدم أي شركة أو برنامج محلي، مو بس القائمة.",
                "اختر من القائمة، أو الصق عنوان أي خدمة من صفحة وثائقها (يبدأ بـ https). لـ Ollama اختر «Ollama (على جهازك)». لو المفتاح معروف الشكل يتعبى العنوان لحاله.")
            k_addr = gr.Dropdown(ADDRESS_CHOICES, value=None, allow_custom_value=True, show_label=False,
                                 elem_classes="ltr", info="اختر من القائمة أو الصق أي عنوان")
            with gr.Accordion("خيارات إضافية", open=False):
                opt("النموذج (اختياري)", "اسم «العقل» اللي يترجم عند هذه الخدمة.",
                    "لو تركته فارغاً يختار الموقع بنفسه: يسأل الخدمة عن قائمتها ويجرّب لين يلقى نموذجاً يشتغل، وإذا الخدمة ما تعرض قائمة يرسل الطلب بدون اسم نموذج.",
                    "اتركه فارغاً. اكتبه فقط لو تبي نموذجاً معيناً، أو خدمتك مدفوعة وتبي تتحكم بالتكلفة. وتقدر تضغط «جلب النماذج المتاحة» لتختار من قائمتهم.")
                k_model = gr.Dropdown([], value=None, allow_custom_value=True, show_label=False, elem_classes="ltr")
                b_fetch = gr.Button("جلب النماذج المتاحة من الخدمة")
                opt("الاستخدام", "يحدد هل المفتاح يشارك في الترجمة أو المراجعة أو الاثنين.",
                    "تخصص المفتاح الأقوى للتدقيق والبقية للترجمة.", "اتركه «ترجمة وتدقيق» لو ما عندك سبب ثاني.")
                k_role = gr.Dropdown(ROLE_CHOICES, value="both", show_label=False)
                opt("حد الطلبات بالدقيقة", "كم طلب يرسل الموقع لهذا المفتاح كل دقيقة كحد أعلى.",
                    "يمنع الوصول للحد بسرعة. ولو وصل الحد فعلاً، الموقع ينتظر ويحوّل لمفتاح ثاني.",
                    "اتركه 0 ليختار الموقع قيمة مناسبة، أو اكتب الرقم اللي تعرفه من حد خدمتك.")
                k_rpm = gr.Number(0, show_label=False, precision=0)
                opt("مفتاح مدفوع", "تعلّم الموقع إن هذا المفتاح يخصم من رصيدك.",
                    "الموقع يحسب الصرف ويوقف المدفوع عند السقف، ويستخدم المجاني أولاً. (الاختيار التلقائي للنموذج لا يعرف الأسعار.)",
                    "علّمه فقط لو مفتاحك مدفوع، واكتب الأسعار من صفحة أسعار الخدمة.")
                k_paid = gr.Checkbox(False, label="هذا المفتاح مدفوع")
                with gr.Row(visible=False) as price_row:
                    k_pin = gr.Number(0, label="سعر الإدخال بالدولار لكل مليون توكن")
                    k_pout = gr.Number(0, label="سعر الإخراج بالدولار لكل مليون توكن")
            b_addk = gr.Button("إضافة المفتاح واختباره", variant="primary")
            kmsg = gr.Markdown()
            step("ب", "مفاتيحك وحالتها الآن", "الحالة تتحدث لحظياً، وأي فشل يظهر معه سببه.")
            kpanel = gr.HTML(key_panel)
            opt("إدارة مفتاح", "اختر مفتاحاً ثم اختبره، أوقفه مؤقتاً، غيّر اسمه أو نموذجه، أو احذفه.",
                "تصلح مفتاحاً فشل بدون ما تعيد إضافته.", "اختر المفتاح من القائمة ثم اضغط الزر المناسب.")
            ksel = gr.Dropdown(key_choices(), show_label=False, value=None, interactive=True)
            with gr.Row():
                b_test = gr.Button("اختبار")
                b_tog = gr.Button("تفعيل / إيقاف")
                b_delk = gr.Button("حذف")
                b_testall = gr.Button("اختبار الكل")
            with gr.Row():
                k_newname = gr.Textbox(show_label=False, placeholder="الاسم الجديد", scale=3)
                b_rename = gr.Button("تغيير الاسم", scale=1)
            with gr.Row():
                k_newmodel = gr.Dropdown([], value=None, allow_custom_value=True, show_label=False,
                                         info="النموذج الجديد (اكتبه أو اجلب القائمة)", elem_classes="ltr", scale=3)
                b_fetch2 = gr.Button("جلب نماذج هذا المفتاح", scale=1)
                b_model = gr.Button("تغيير النموذج", scale=1)
            b_auto = gr.Button("اختيار النموذج تلقائياً لهذا المفتاح")
        # ============================================================ 2. TRANSLATE
        with gr.Tab("٢. الترجمة"):
            step("أ", "ارفع الملفات", "تقدر ترفع أكثر من ملف، وتترجم بالدور واحداً بعد واحد.")
            opt("الملفات", "تقبل ملفات PDF وEPUB وTXT.", "ترفع عدة كتب مرة وحدة وتتركها تشتغل.",
                "اضغط على المربع أو اسحب الملفات إليه.")
            files = gr.File(show_label=False, file_count="multiple", file_types=[".pdf", ".epub", ".txt"])
            step("ب", "اختر اللغات والأسلوب")
            with gr.Row():
                with gr.Column():
                    opt("لغة الأصل", "لغة الملف المرفوع.", "كل ما تحددها صارت الترجمة أدق.",
                        "اتركها «كشف تلقائي» إلا لو الملف يخلط لغات.")
                    src = gr.Dropdown(SRC_CHOICES, value="auto", show_label=False)
                with gr.Column():
                    opt("لغة الهدف", "اللغة اللي تبي الترجمة إليها.", "تحدد لغة الناتج.", "اختر لغة تختلف عن لغة الأصل.")
                    tgt = gr.Dropdown(LANG_CHOICES, value="ar", show_label=False)
                with gr.Column():
                    opt("حساسية المدقق", "كم يتدخل المدقق في الترجمة بعد انتهائها. هو يعدّل الفقرات الضعيفة فقط ولا يعيد كتابة السليم.",
                        "الصارم أسرع وأرخص، والدقيق يضبط الأسلوب أكثر.", "ابدأ بـ «متوسط». اختر «دقيق» للروايات الأدبية.")
                    sens = gr.Dropdown(SENS_CHOICES, value="medium", show_label=False)
            opt("وصف الأسلوب", "جملة تصف الأسلوب اللي تبيه في الترجمة.", "يوجّه النموذج لنبرة الرواية.",
                "اكتب مثل: «سرد أدبي فصيح، وحوار حاد وعسكري».")
            style = gr.Textbox(show_label=False, lines=2, placeholder="مثال: سرد أدبي فصيح، حوار حاد وعسكري")
            with gr.Accordion("خيارات متقدمة", open=False):
                opt("عينة ذهبية", "فقرة مترجمة بالأسلوب اللي يعجبك.", "الموقع يقلّد أسلوبها في كل الأجزاء.",
                    "الصق فقرة أو اثنتين مترجمتين بالشكل اللي تبيه (اختياري).")
                golden = gr.Textbox(show_label=False, lines=4)
            go = gr.Button("أضف للطابور وابدأ الترجمة", variant="primary")
            gmsg = gr.Markdown()
            step("ج", "تابع التقدم لحظة بلحظة", "تتحدث الصفحة كل ثانيتين. تقدر تغلق المتصفح، والترجمة تكمل ما دام البرنامج شغال.")
            opt("لوحة المتابعة", "تعرض المرحلة الحالية، وعدد الفقرات والصفحات المنتهية، والوقت المنقضي والمتبقي، وحالة كل مفتاح.",
                "تعرف وين وصلت الترجمة ولماذا تتأخر، مثل انتظار حد الدقيقة مع ساعة الاستئناف.",
                "اختر ملفاً من القائمة لتشوف تفاصيله، وإلا تظهر تفاصيل الملف الشغال.")
            jsel = gr.Dropdown(job_choices(), show_label=False, value=None, interactive=True)
            with gr.Row():
                b_resume = gr.Button("استكمال")
                b_stop = gr.Button("إيقاف")
                b_del = gr.Button("حذف")
            jmsg = gr.Markdown()
            mon = gr.HTML(monitor.monitor_html)
            gr.HTML("<div class='step'><i>⏱</i>كل الملفات</div>")
            jlist = gr.HTML(monitor.jobs_html)
            gr.HTML("<div class='step'><i>🔑</i>حالة المفاتيح الآن</div>")
            kmon = gr.HTML(monitor.keys_html)
            gr.HTML("<div class='step'><i>📜</i>آخر الأحداث</div>")
            ev = gr.HTML(monitor.events_html)
        # ============================================================ 3. REVIEW
        with gr.Tab("٣. المراجعة والتصدير") as tab_review:
            step("أ", "اختر الملف", "بعد ما تنتهي الترجمة يظهر الملف هنا للمراجعة قبل التصدير.")
            opt("الملف", "قائمة الملفات التي تمت معالجتها.", "تراجع الترجمة قبل إنتاج الملف النهائي.",
                "اختر ملفاً ثم اضغط «تحميل».")
            rsel = gr.Dropdown(job_choices(), show_label=False, value=None, interactive=True)
            b_load = gr.Button("تحميل", variant="primary")
            rinfo = gr.Markdown()
            step("ب", "راجع الترجمة وعدّلها")
            opt("جدول المراجعة", "يعرض كل فقرة: الأصل بجانب الترجمة.", "تصحح أي كلمة بيدك مباشرة.",
                "اضغط على خلية الترجمة واكتب، ثم اضغط «حفظ التعديلات».")
            grid = gr.Dataframe(headers=["المعرّف", "صفحة", "الأصل", "الترجمة (اضغط للتعديل)"], interactive=True,
                                wrap=True, column_count=(4, "fixed"), datatype=["str", "number", "str", "str"],
                                max_height=520, column_widths=["9%", "7%", "42%", "42%"])
            b_save = gr.Button("حفظ التعديلات")
            with gr.Accordion("بطاقة السياق: أسماء الشخصيات والمصطلحات", open=False):
                opt("بطاقة السياق", "قائمة أسماء الشخصيات وجنسها والمصطلحات ونبرة الرواية، يبنيها الموقع من النص.",
                    "تثبّت الأسماء والضمائر بين كل الأجزاء.",
                    "صحّح أي اسم أو جنس غلط. التعديل يؤثر على الأوامر القادمة، والترجمة الجاهزة تتغير فقط بالأمر الذكي أو الاستبدال.")
                ctx = gr.Textbox(show_label=False, lines=8, elem_classes="ltr")
            step("ج", "تعديلات ذكية")
            opt("أمر للذكاء الاصطناعي", "تكتب تعليمة والنموذج يطبقها على الفقرات المناسبة فقط.",
                "تعدّل الأسلوب أو الحوار في كل الملف بجملة وحدة.", "مثال: «اجعل الحوار أكثر حدة». ثم اضغط «نفّذ».")
            chat = gr.Textbox(show_label=False, placeholder="مثال: أعد صياغة الحوار ليكون أكثر حدة")
            b_chat = gr.Button("نفّذ")
            with gr.Accordion("استبدال كلمة في الملف كله", open=False):
                opt("الاستبدال", "يبدل كلمة بأخرى في كل الترجمة بدون ذكاء اصطناعي.", "سريع ومضمون.",
                    "اكتب الكلمة القديمة والجديدة ثم اضغط الزر.")
                with gr.Row():
                    f_find = gr.Textbox(label="الكلمة القديمة")
                    f_repl = gr.Textbox(label="الكلمة الجديدة")
                b_repl = gr.Button("استبدل")
            rmsg = gr.Markdown()
            step("د", "صدّر الملف النهائي")
            opt("صيغ التصدير", "PDF يحافظ على شكل الصفحات الأصلية، وEPUB كتاب إلكتروني، وTXT نص عادي.",
                "تختار الصيغة المناسبة لقراءتك.", "علّم الصيغ المطلوبة ثم اضغط «توليد».")
            with gr.Row():
                c_pdf = gr.Checkbox(True, label="PDF")
                c_epub = gr.Checkbox(True, label="EPUB")
                c_txt = gr.Checkbox(False, label="TXT")
            b_gen = gr.Button("توليد الملف النهائي", variant="primary")
            out_files = gr.File(show_label=False, file_count="multiple")
        # ============================================================ 4. SETTINGS
        with gr.Tab("٤. الإعدادات"):
            step("أ", "كلمة السر", "كلمة السر الأولية 2222، ولازم تغيّرها قبل الاستخدام.")
            opt("تغيير كلمة السر", "يغيّر كلمة الدخول للموقع.", "يمنع غيرك من استخدام مفاتيحك.",
                "اكتب الحالية ثم الجديدة (6 خانات فأكثر).")
            with gr.Row():
                pw_old = gr.Textbox(label="الحالية", type="password")
                pw_new = gr.Textbox(label="الجديدة", type="password")
            b_pw = gr.Button("تغيير كلمة السر")
            pw_msg = gr.Markdown()
            step("ب", "سقف الصرف")
            opt("سقف الصرف", "أقصى مبلغ بالدولار يصرفه الموقع من المفاتيح المدفوعة.",
                "يوقف المدفوع تلقائياً عند الوصول، ويكمل بالمجاني.", "5 ريال تقريباً 1.33 دولار. علّم «صفّر العداد» لتبدأ حساباً جديداً.")
            bud = gr.Number(get_settings()["budget_usd"], show_label=False)
            reset = gr.Checkbox(False, label="صفّر عداد الصرف")
            b_bud = gr.Button("حفظ")
            bud_msg = gr.Markdown()

    timer = gr.Timer(2)
    timer.tick(tick, jsel, [hero, banner, jlist, mon, kmon, ev])
    timer.tick(lambda: key_panel(), None, kpanel)
    demo.load(lambda: (gr.update(choices=job_choices()), gr.update(choices=job_choices()), gr.update(choices=key_choices())),
              None, [jsel, rsel, ksel])
    tab_review.select(lambda: gr.update(choices=job_choices()), None, rsel)

    k_key.change(on_key_change, [k_key, k_addr], k_addr)
    k_paid.change(lambda v: gr.update(visible=v), k_paid, price_row)
    b_fetch.click(fetch_models_ui, [k_addr, k_key], [k_model, kmsg])
    b_fetch2.click(fetch_models_for_key, ksel, [k_newmodel, kmsg])
    b_addk.click(add_key_ui, [k_name, k_key, k_addr, k_model, k_role, k_paid, k_pin, k_pout, k_rpm],
                 [k_key, k_name, kpanel, ksel, kmsg])
    b_test.click(lambda k: key_action(k, "test"), ksel, [kpanel, ksel, kmsg])
    b_tog.click(lambda k: key_action(k, "toggle"), ksel, [kpanel, ksel, kmsg])
    b_delk.click(lambda k: key_action(k, "delete"), ksel, [kpanel, ksel, kmsg])
    b_rename.click(lambda k, n: key_action(k, "rename", n), [ksel, k_newname], [kpanel, ksel, kmsg])
    b_model.click(lambda k, m: key_action(k, "model", m), [ksel, k_newmodel], [kpanel, ksel, kmsg])
    b_auto.click(lambda k: key_action(k, "auto"), ksel, [kpanel, ksel, kmsg])
    b_testall.click(test_all, None, [kpanel, kmsg])
    go.click(add_jobs, [files, src, tgt, style, golden, sens], [gmsg, jsel])
    b_resume.click(lambda j: job_action(j, "resume"), jsel, [jsel, jmsg])
    b_stop.click(lambda j: job_action(j, "stop"), jsel, [jsel, jmsg])
    b_del.click(lambda j: job_action(j, "delete"), jsel, [jsel, jmsg])
    b_load.click(load_review, rsel, [grid, ctx, rinfo])
    b_save.click(save_review, [rsel, grid, ctx], rmsg)
    b_chat.click(run_chat, [rsel, chat, grid], [grid, rmsg])
    b_repl.click(do_replace, [rsel, f_find, f_repl], [grid, rmsg])
    b_gen.click(generate, [rsel, grid, ctx, c_pdf, c_epub, c_txt], [out_files, rmsg])
    b_pw.click(auth.change, [pw_old, pw_new], pw_msg)
    b_bud.click(save_budget, [bud, reset], bud_msg)

if __name__ == "__main__":
    jobs.recover()
    kw = dict(server_name=os.getenv("HOST") or ("0.0.0.0" if os.getenv("SPACE_ID") else "127.0.0.1"),
              server_port=int(os.getenv("PORT", "7860")), auth=auth.check, css=CSS, max_file_size="200mb")
    try:
        demo.queue(default_concurrency_limit=8).launch(theme=THEME, **kw)
    except TypeError:
        demo.queue(default_concurrency_limit=8).launch(**kw)
