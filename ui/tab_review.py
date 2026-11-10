"""Tab 4: review the automatic translation, fix it, export PDF / EPUB / TXT."""
import os, shutil
import gradio as gr
from core import builder, edition, editor, jobs, monitor, quality
from core.config import JOBS
from .common import guard, opt, step
from .tab_translate import job_choices


def load_review(jid, only_flagged=False):
    guard()
    if not jid:
        raise gr.Error("اختر ملفاً")
    meta, units = jobs.load(jid)
    if quality.recheck(units, meta["tgt"]):
        jobs.save_units(jid, units)
    us = [u for u in units if u.get("translate")]
    if only_flagged:
        us = [u for u in us if u.get("flag") or not u.get("tr")]
    rows = [[u["id"], u["page"] + 1, u["text"], u.get("tr", ""), u.get("flag") or ("بدون ترجمة" if not u.get("tr") else "")] for u in us]
    note = " (المشبوهة فقط)" if only_flagged else ""
    return rows, meta.get("ctx", ""), f"تم تحميل **{len(rows)}** فقرة{note}. الحالة: {meta.get('stage')}", monitor.quality_html(jid)


def save_review(jid, rows, ctx):
    guard()
    meta, units = jobs.load(jid)
    by = {u["id"]: u for u in units}
    n = 0
    for r in rows.values.tolist() if hasattr(rows, "values") else rows:
        u = by.get(r[0])
        if u and (r[3] or "") != u.get("tr", ""):
            u["tr"] = r[3] or ""
            fl = quality.check(u["text"], u["tr"], meta["tgt"])
            if fl:
                u["flag"] = "؛ ".join(fl)
            else:
                u.pop("flag", None)
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
    new_rows, _, _, _ = load_review(jid)
    return new_rows, f"✏ عُدّلت **{len(patches)}** فقرة\n\n{log}"


def do_replace(jid, find, repl):
    guard()
    if not find:
        raise gr.Error("اكتب الكلمة المراد استبدالها")
    meta, units = jobs.load(jid)
    n = editor.find_replace(units, find, repl)
    jobs.save_units(jid, units)
    rows, _, _, _ = load_review(jid)
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


def build():
    with gr.Tab("٤. المراجعة والتصدير") as tab_review:
        step("أ", "اختر الملف", "بعد ما تنتهي الترجمة يظهر الملف هنا للمراجعة قبل التصدير.")
        opt("الملف", "قائمة الملفات التي تمت معالجتها.", "تراجع الترجمة قبل إنتاج الملف النهائي.",
            "اختر ملفاً ثم اضغط «تحميل».")
        rsel = gr.Dropdown(job_choices(), show_label=False, value=None, interactive=True)
        b_load = gr.Button("تحميل", variant="primary")
        rinfo = gr.Markdown()
        step("ب", "راجع الترجمة وعدّلها")
        opt("جدول المراجعة", "يعرض كل فقرة: الأصل بجانب الترجمة.", "تصحح أي كلمة بيدك مباشرة.",
            "اضغط على خلية الترجمة واكتب، ثم اضغط «حفظ التعديلات».")
        qrep = gr.HTML(lambda: monitor.quality_html(None))
        only_flag = gr.Checkbox(False, label="عرض الفقرات المشبوهة وغير المترجمة فقط (للإصلاح السريع)")
        grid = gr.Dataframe(headers=["المعرّف", "صفحة", "الأصل", "الترجمة (اضغط للتعديل)", "ملاحظة البرنامج"], interactive=True,
                            wrap=True, column_count=(5, "fixed"), datatype=["str", "number", "str", "str", "str"],
                            max_height=520, column_widths=["8%", "6%", "34%", "34%", "18%"])
        b_save = gr.Button("حفظ التعديلات")
        with gr.Accordion("بطاقة السياق: أسماء الشخصيات والمصطلحات", open=False):
            opt("بطاقة السياق", "قائمة أسماء الشخصيات وجنسها والمصطلحات ونبرة الرواية، يبنيها الموقع من النص.",
                "تثبّت الأسماء والضمائر بين كل الأجزاء.",
                "صحّح أي اسم أو جنس غلط. التعديل يؤثر على الأوامر القادمة، والترجمة الجاهزة تتغير فقط بالأمر الذكي أو الاستبدال.")
            ctx = gr.Textbox(show_label=False, lines=8, elem_classes="ltr")
        with gr.Group(visible=not edition.is_lite()):          # أوامر الذكاء الاصطناعي: مخفية في النسخة المخففة
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
    b_load.click(load_review, [rsel, only_flag], [grid, ctx, rinfo, qrep])
    only_flag.change(load_review, [rsel, only_flag], [grid, ctx, rinfo, qrep])
    b_save.click(save_review, [rsel, grid, ctx], rmsg)
    b_chat.click(run_chat, [rsel, chat, grid], [grid, rmsg])
    b_repl.click(do_replace, [rsel, f_find, f_repl], [grid, rmsg])
    b_gen.click(generate, [rsel, grid, ctx, c_pdf, c_epub, c_txt], [out_files, rmsg])
    return {"rsel": rsel, "tab": tab_review}
