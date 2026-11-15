"""Tab «لصق ترجمة جاهزة»: a translation made elsewhere (a chat) for the WHOLE file, or only for a range of pages."""
import gradio as gr
from ui.common import step
from .reg import put


def build():
    gr.HTML("<div class='mini'>الصق الترجمة (أو ارفع ملف txt) بهذا الشكل: كل صفحة تبدأ بسطر <b>=== صفحة 5 ===</b> (رقمها في الملف الأصلي)، وتحتها كل فقرة بسطر يبدأ برقمها <b>1) النص</b>. "
            "الملف يبقى كما هو، وتتبدل فقط فقرات الصفحات اللي فيها. اللصق خطوة وحدة، وتقدر تتراجع عنه بزر «تراجع» فوق. "
            "أما لصق ترجمة صفحة وحدة فهو داخل تبويب «٢. الترجمة».</div>")
    step("١", "وش تبغى تلصق؟")
    put("ib_kind", gr.Radio([("الملف كامل (كل الصفحات اللي في النص)", "all"), ("نطاق صفحات فقط (تجاهل بقية الصفحات)", "range")], value="all", show_label=False))
    with gr.Row(visible=False) as rng:
        put("ib_a", gr.Number(1, label="من صفحة", precision=0, minimum=1))
        put("ib_b", gr.Number(10, label="إلى صفحة", precision=0, minimum=1))
    put("ib_rng", rng)
    step("٢", "الترجمة")
    put("ib_up", gr.UploadButton("📄 ارفع ملف txt", file_types=[".txt"], size="sm"))
    put("ib_txt", gr.Textbox(lines=14, max_lines=30, show_label=False, rtl=True, placeholder="=== صفحة 1 ===\n1) ...\n2) ...\n\n=== صفحة 2 ===\n1) ..."))
    put("b_ib", gr.Button("ألصق الترجمة", variant="primary"))
    put("ib_msg", gr.Markdown())
