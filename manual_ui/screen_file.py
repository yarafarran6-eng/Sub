"""Tab «الملف»: open a new file, go back to an old one, manage drafts."""
import gradio as gr
from ui.common import opt, step
from .reg import put
from .view import file_choices
from .widgets import danger


def build():
    step("١", "ملف جديد", "ما يحتاج أي مفتاح: الموقع يستخرج النص فقط وأنت تترجم بيدك (أو بالذكاء لو تبي). كل شي يُحفظ تلقائياً.")
    put("file_in", gr.File(show_label=False, file_types=[".pdf"]))
    put("b_new", gr.Button("استخراج النص وفتح الملف", variant="primary"))
    step("٢", "ملفاتي السابقة", "كل ملف اشتغلت عليه، وكل ملف ترجمته آلياً من تبويب «الترجمة الآلية»، في قائمة وحدة. اختر ملفاً ثم «فتح» وتكمل من آخر مكان وقفت عنده.")
    put("files_sel", gr.Dropdown(file_choices(), show_label=False, value=None, interactive=True))
    with gr.Row():
        put("b_open", gr.Button("📂 فتح الملف", variant="primary"))
        put("b_delfile", gr.Button("🗑 حذف الملف نهائياً"))
    danger("delfile")
    step("٣", "المسودات", "المسودة نسخة مستقلة من ترجمتك للملف نفسه (مثلاً نسخة بخط ثاني). تتبدل بينها بدون ما تضيع وحدة.")
    put("dsel", gr.Dropdown([], label="المسودة الحالية", value=None, interactive=True))
    with gr.Row():
        put("b_dnew", gr.Button("➕ مسودة جديدة فاضية"))
        put("b_dcopy", gr.Button("⧉ نسخ المسودة الحالية"))
        put("b_ddel", gr.Button("🗑 حذف المسودة الحالية"))
    danger("deldraft")
    with gr.Row():
        put("dname", gr.Textbox(label="اسم جديد للمسودة الحالية", scale=3))
        put("b_dren", gr.Button("✏ تغيير الاسم", scale=1))
