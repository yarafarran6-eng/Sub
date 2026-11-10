"""Tab 2: upload files, choose languages, follow the automatic translation live."""
import gradio as gr
from core import edition, jobs, monitor
from core.keystore import load_keys
from .common import guard, opt, step
from .header import hero_html, banner_html

LANG_CHOICES = [("العربية", "ar"), ("English", "en"), ("日本語", "ja")]
SRC_CHOICES = [("كشف تلقائي", "auto")] + LANG_CHOICES
SENS_CHOICES = [("صارم: الأخطاء الفادحة فقط", "strict"), ("متوسط: مع الركاكة والتناقض", "medium"),
                ("دقيق: مع النبرة والأسلوب", "precise")]

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


def build():
    with gr.Tab("٢. الترجمة الآلية", visible=not edition.is_lite()):
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
    go.click(add_jobs, [files, src, tgt, style, golden, sens], [gmsg, jsel])
    b_resume.click(lambda j: job_action(j, "resume"), jsel, [jsel, jmsg])
    b_stop.click(lambda j: job_action(j, "stop"), jsel, [jsel, jmsg])
    b_del.click(lambda j: job_action(j, "delete"), jsel, [jsel, jmsg])
    return {"jsel": jsel, "jlist": jlist, "mon": mon, "kmon": kmon, "ev": ev}
