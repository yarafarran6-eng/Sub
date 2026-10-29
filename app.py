import os, shutil
import gradio as gr
from core import auth, jobs, editor, builder, llm
from core.config import JOBS, get_settings, update_settings, read_json
from core.keystore import PROVIDERS, add_key, delete_key, detect_provider, load_keys, mask, update_key
from core.pool import POOL

LANG_CHOICES = [("English", "en"), ("العربية", "ar"), ("日本語", "ja")]
SRC_CHOICES = [("كشف تلقائي", "auto")] + LANG_CHOICES
SENS_CHOICES = [("صارم: الأخطاء الفادحة فقط", "strict"), ("متوسط: + الركاكة والتناقض", "medium"),
                ("دقيق: + النبرة والأسلوب", "precise")]
CSS = ".gradio-container{direction:rtl} textarea,input{text-align:right} .ltr textarea{direction:ltr;text-align:left}"


def guard():
    if auth.must_change():
        raise gr.Error("غيّر كلمة السر الأولية من تبويب الإعدادات أولاً")


# ---------------- translation tab ----------------
def add_jobs(files, src, tgt, style, golden, sens):
    guard()
    if not files:
        raise gr.Error("ارفع ملفاً واحداً على الأقل")
    if not [k for k in load_keys() if k.get("enabled")]:
        raise gr.Error("ما فيه مفاتيح API مفعّلة. أضفها من تبويب API")
    if src == tgt:
        raise gr.Error("لغة المصدر والهدف متطابقتان")
    ids = [jobs.create(f if isinstance(f, str) else f.name, src, tgt, style, golden, sens) for f in files]
    return f"أُضيف {len(ids)} ملف للطابور", job_table(), gr.update(choices=job_choices())


def job_table():
    rows = []
    for m in jobs.list_jobs():
        rows.append([m["id"], m["name"], m.get("stage", ""), f"{m.get('pct', 0)}%", m.get("status", ""), m.get("msg", "")])
    return rows


def job_choices():
    return [(f"{m['name']}  [{m['id']}]  {m.get('stage', '')}", m["id"]) for m in jobs.list_jobs()]


def job_action(jid, what):
    guard()
    if not jid:
        raise gr.Error("اختر ملفاً من القائمة")
    if what == "resume":
        jobs.enqueue(jid)
    elif what == "stop":
        jobs.cancel(jid)
    elif what == "delete":
        jobs.cancel(jid)
        jobs.delete(jid)
    return job_table(), gr.update(choices=job_choices(), value=None if what == "delete" else jid)


# ---------------- review tab ----------------
def load_review(jid):
    guard()
    if not jid:
        raise gr.Error("اختر ملفاً")
    meta, units = jobs.load(jid)
    rows = [[u["id"], u["page"] + 1, u["text"], u.get("tr", "")] for u in units if u.get("translate")]
    return rows, meta.get("ctx", ""), f"{len(rows)} فقرة. الحالة: {meta.get('stage')}"


def save_review(jid, rows, ctx):
    guard()
    meta, units = jobs.load(jid)
    by = {u["id"]: u for u in units}
    n = 0
    for r in rows:
        u = by.get(r[0])
        if u and (r[3] or "") != u.get("tr", ""):
            u["tr"] = r[3] or ""
            n += 1
    jobs.save_units(jid, units)
    jobs.set_state(jid, ctx=ctx)
    return f"حُفظ {n} تعديل"


def run_chat(jid, instruction, rows):
    guard()
    if not instruction.strip():
        raise gr.Error("اكتب التعليمة")
    save_review(jid, rows, jobs.load(jid)[0].get("ctx", ""))
    meta, units = jobs.load(jid)
    patches = editor.run_instruction(units, instruction, meta["src"], meta["tgt"], meta["ctx"], meta["style"])
    jobs.save_units(jid, units)
    log = "\n".join(f"{p['id']}: {p['why']}" for p in patches[:40]) or "ما احتاج أي فقرة تعديل"
    new_rows, _, _ = load_review(jid)
    return new_rows, f"عُدّلت {len(patches)} فقرة\n{log}"


def do_replace(jid, find, repl):
    guard()
    if not find:
        raise gr.Error("اكتب الكلمة المراد استبدالها")
    meta, units = jobs.load(jid)
    n = editor.find_replace(units, find, repl)
    jobs.save_units(jid, units)
    rows, _, _ = load_review(jid)
    return rows, f"استُبدلت {n} مرة"


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
            notes.append(f"PDF: {info['pages']} صفحة، {info['shrunk_blocks']} فقرة صُغّر خطها ليتسع النص")
        else:
            notes.append("PDF متاح فقط للملفات الأصلية PDF، استخدم EPUB")
    if want_epub:
        if builder.build_epub(units, meta["tgt"], os.path.splitext(meta["name"])[0], str(out / (base + ".epub"))):
            files.append(str(out / (base + ".epub")))
    if want_txt:
        builder.build_txt(units, str(out / (base + ".txt")))
        files.append(str(out / (base + ".txt")))
    return files, "\n".join(notes) or "تم"


# ---------------- API tab ----------------
def key_table():
    rows = []
    for k, st, ok in POOL.status():
        rows.append([k["id"], k["provider"], mask(k["key"]), k["model"], k.get("role", "both"),
                     "نعم" if k.get("paid") else "لا", "نعم" if k.get("enabled") else "لا", st,
                     f"{k.get('tokens_in', 0)}/{k.get('tokens_out', 0)}"])
    return rows


def key_choices():
    return [(f"{k['provider']} {mask(k['key'])} [{k['id']}]", k["id"]) for k in load_keys()]


def on_key_change(key):
    p = detect_provider(key)
    return gr.update(value=p), gr.update(value=PROVIDERS[p]["model"])


def add_key_ui(provider, key, model, role, paid, pin, pout):
    guard()
    if not key.strip():
        raise gr.Error("الصق المفتاح")
    add_key(provider, key, model, role, paid, pin, pout)
    return "", key_table(), gr.update(choices=key_choices()), "أُضيف المفتاح. اضغط اختبار للتأكد"


def key_action(kid, what):
    guard()
    if not kid:
        raise gr.Error("اختر مفتاحاً")
    msg = "تم"
    k = next((x for x in load_keys() if x["id"] == kid), None)
    if what == "delete":
        delete_key(kid)
    elif what == "toggle" and k:
        update_key(kid, enabled=not k.get("enabled"))
        POOL.revive(kid)
    elif what == "test" and k:
        try:
            text, _ = llm.chat(k, [{"role": "user", "content": "Reply with the single word OK"}], 20, 0, "ping", 40)
            POOL.revive(kid)
            msg = f"شغّال ✓ ({text.strip()[:30]})"
        except Exception as e:
            msg = f"فشل: {str(e)[:200]}"
    return key_table(), gr.update(choices=key_choices(), value=None if what == "delete" else kid), msg


def save_budget(usd, spent_reset):
    guard()
    s = update_settings(budget_usd=float(usd), **({"spent_usd": 0.0} if spent_reset else {}))
    return f"السقف {s['budget_usd']}$، المصروف {s['spent_usd']}$"


def budget_text():
    s = get_settings()
    return f"المصروف {s['spent_usd']:.4f}$ من {s['budget_usd']}$ (يُحسب للمفاتيح المدفوعة فقط)"


def change_pw(old, new):
    return auth.change(old, new)


with gr.Blocks(title="Sub — مترجم الروايات") as demo:
    gr.Markdown("## مترجم الروايات والملفات")
    with gr.Tab("الترجمة"):
        files = gr.File(label="ارفع ملفات PDF أو EPUB أو TXT", file_count="multiple", file_types=[".pdf", ".epub", ".txt"])
        with gr.Row():
            src = gr.Dropdown(SRC_CHOICES, value="auto", label="لغة المصدر")
            tgt = gr.Dropdown(LANG_CHOICES, value="ar", label="لغة الهدف")
            sens = gr.Dropdown(SENS_CHOICES, value="medium", label="حساسية المدقق")
        style = gr.Textbox(label="وصف الأسلوب المطلوب", lines=2, placeholder="مثال: سرد أدبي فصيح، حوار حاد وعسكري")
        golden = gr.Textbox(label="عينة ذهبية (اختياري): فقرة مترجمة بالأسلوب اللي تبيه", lines=3)
        go = gr.Button("أضف للطابور وابدأ", variant="primary")
        msg = gr.Textbox(label="", interactive=False)
        table = gr.Dataframe(headers=["id", "الملف", "المرحلة", "التقدم", "الحالة", "ملاحظة"], value=job_table, every=3,
                             interactive=False, wrap=True)
        jsel = gr.Dropdown(job_choices(), label="اختر ملفاً", value=None)
        with gr.Row():
            b_resume = gr.Button("استكمال")
            b_stop = gr.Button("إيقاف")
            b_del = gr.Button("حذف")
    with gr.Tab("المعاينة والتعديل"):
        rsel = gr.Dropdown(job_choices(), label="الملف", value=None)
        b_load = gr.Button("تحميل")
        rinfo = gr.Textbox(label="", interactive=False)
        grid = gr.Dataframe(headers=["id", "صفحة", "الأصل", "الترجمة (قابلة للتعديل)"], interactive=True, wrap=True,
                            column_count=(4, "fixed"), datatype=["str", "number", "str", "str"], max_height=520)
        ctx = gr.Textbox(label="بطاقة السياق (أسماء، جنس، مصطلحات) — قابلة للتعديل", lines=6, elem_classes="ltr")
        with gr.Row():
            chat = gr.Textbox(label="أمر للذكاء الاصطناعي", placeholder="مثال: أعد صياغة الحوار ليكون أكثر حدة")
            b_chat = gr.Button("نفّذ")
        with gr.Row():
            f_find = gr.Textbox(label="استبدال: الكلمة")
            f_repl = gr.Textbox(label="بـ")
            b_repl = gr.Button("استبدل في المجلد كاملاً")
        b_save = gr.Button("حفظ التعديلات")
        rmsg = gr.Textbox(label="", interactive=False, lines=3)
        with gr.Row():
            c_pdf = gr.Checkbox(True, label="PDF")
            c_epub = gr.Checkbox(True, label="EPUB")
            c_txt = gr.Checkbox(False, label="TXT")
        b_gen = gr.Button("توليد الملف النهائي", variant="primary")
        out_files = gr.File(label="الملفات النهائية", file_count="multiple")
    with gr.Tab("API"):
        gr.Markdown("الصق المفتاح وبيتعرف الموقع على المزود. المفاتيح تُحفظ على جهازك فقط ولا تُرفع للمستودع.")
        with gr.Row():
            k_key = gr.Textbox(label="المفتاح", type="password")
            k_prov = gr.Dropdown(list(PROVIDERS), value="gemini", label="المزود")
            k_model = gr.Textbox(label="النموذج", value=PROVIDERS["gemini"]["model"])
        with gr.Row():
            k_role = gr.Dropdown([("ترجمة وتدقيق", "both"), ("ترجمة فقط", "translate"), ("تدقيق فقط", "edit")],
                                 value="both", label="الاستخدام")
            k_paid = gr.Checkbox(False, label="مفتاح مدفوع")
            k_pin = gr.Number(0, label="سعر الإدخال $ لكل مليون")
            k_pout = gr.Number(0, label="سعر الإخراج $ لكل مليون")
        b_addk = gr.Button("إضافة API", variant="primary")
        ktable = gr.Dataframe(headers=["id", "المزود", "المفتاح", "النموذج", "الاستخدام", "مدفوع", "مفعّل", "الحالة", "توكنات"],
                              value=key_table, every=3, interactive=False)
        ksel = gr.Dropdown(key_choices(), label="اختر مفتاحاً", value=None)
        with gr.Row():
            b_test = gr.Button("اختبار")
            b_tog = gr.Button("تفعيل/إيقاف")
            b_delk = gr.Button("حذف")
        kmsg = gr.Textbox(label="", interactive=False)
    with gr.Tab("الإعدادات"):
        gr.Markdown("**كلمة السر الأولية 2222، لازم تغيّرها قبل الاستخدام.**")
        with gr.Row():
            pw_old = gr.Textbox(label="الحالية", type="password")
            pw_new = gr.Textbox(label="الجديدة", type="password")
        b_pw = gr.Button("تغيير كلمة السر")
        pw_msg = gr.Textbox(label="", interactive=False)
        gr.Markdown("### سقف الصرف للمفاتيح المدفوعة")
        bud = gr.Number(get_settings()["budget_usd"], label="الحد الأقصى بالدولار (5 ريال تقريباً 1.33$)")
        reset = gr.Checkbox(False, label="صفّر العداد")
        b_bud = gr.Button("حفظ")
        bud_msg = gr.Textbox(value=budget_text, every=5, label="", interactive=False)

    go.click(add_jobs, [files, src, tgt, style, golden, sens], [msg, table, jsel])
    b_resume.click(lambda j: job_action(j, "resume"), jsel, [table, jsel])
    b_stop.click(lambda j: job_action(j, "stop"), jsel, [table, jsel])
    b_del.click(lambda j: job_action(j, "delete"), jsel, [table, jsel])
    b_load.click(load_review, rsel, [grid, ctx, rinfo])
    b_save.click(save_review, [rsel, grid, ctx], rmsg)
    b_chat.click(run_chat, [rsel, chat, grid], [grid, rmsg])
    b_repl.click(do_replace, [rsel, f_find, f_repl], [grid, rmsg])
    b_gen.click(generate, [rsel, grid, ctx, c_pdf, c_epub, c_txt], [out_files, rmsg])
    k_key.change(on_key_change, k_key, [k_prov, k_model])
    b_addk.click(add_key_ui, [k_prov, k_key, k_model, k_role, k_paid, k_pin, k_pout], [k_key, ktable, ksel, kmsg])
    b_test.click(lambda k: key_action(k, "test"), ksel, [ktable, ksel, kmsg])
    b_tog.click(lambda k: key_action(k, "toggle"), ksel, [ktable, ksel, kmsg])
    b_delk.click(lambda k: key_action(k, "delete"), ksel, [ktable, ksel, kmsg])
    b_pw.click(change_pw, [pw_old, pw_new], pw_msg)
    b_bud.click(save_budget, [bud, reset], bud_msg)
    demo.load(lambda: (gr.update(choices=job_choices()), gr.update(choices=job_choices()), gr.update(choices=key_choices())),
              None, [jsel, rsel, ksel])

if __name__ == "__main__":
    demo.queue(default_concurrency_limit=8).launch(
        server_name=os.getenv("HOST", "127.0.0.1"), server_port=int(os.getenv("PORT", "7860")),
        auth=auth.check, css=CSS, max_file_size="200mb")
