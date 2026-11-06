"""Tab «الصفحات»: the list of pages, range, delete / move / swap, add or replace a page, with a live picture of the result."""
import gradio as gr
from ui.common import step
from .h_pages import OPS
from .reg import put
from .widgets import danger


def build():
    with gr.Row():
        with gr.Column(scale=5):
            step("١", "اختر الصفحة", "الجدول يعرض صفحات الملف النهائي بترتيبها. اكتب رقم الصفحة اللي تبي تشتغل عليها، وكل العمليات تحت تتعامل مع هذا الرقم.")
            put("plan", gr.Dataframe(headers=["#", "الصفحة", "الحالة"], interactive=False, wrap=True, max_height=240, value=[]))
            put("pg_target", gr.Number(1, label="رقم الصفحة اللي أشتغل عليها", precision=0, minimum=1))
            step("٢", "حذف أو نقل أو تبديل")
            with gr.Group():
                put("b_delpage", gr.Button("🗑 حذف هذي الصفحة من الملف النهائي"))
                danger("delpage")
            with gr.Row():
                put("mv_to", gr.Number(1, label="انقلها إلى الموضع رقم", precision=0, minimum=1))
                put("b_move", gr.Button("↕ انقل الصفحة"))
            with gr.Row():
                put("sw_with", gr.Number(1, label="بدّلها مع الصفحة رقم", precision=0, minimum=1))
                put("b_swap", gr.Button("⇄ بدّل الصفحتين"))
            step("٣", "أضف صفحة أو استبدل صفحة", "مثال: تبي تغيّر الصفحة 5 بصورة من جهازك: اختر «أستبدل بها الصفحة»، ارفع الصورة، علّم خانة التأكيد، ثم «نفّذ».")
            put("ins_op", gr.Radio(OPS, value="after", label="ماذا أسوي؟ (على الصفحة المكتوب رقمها فوق)"))
            put("ins_file", gr.File(label="صورة (png, jpg, webp) أو ملف PDF من جهازك", file_types=[".pdf", ".png", ".jpg", ".jpeg", ".webp"]))
            put("ins_page", gr.Number(1, label="لو رفعت PDF: أي صفحة منه؟", precision=0, minimum=1))
            put("ins_sure", gr.Checkbox(False, label="أؤكد حذف الصفحة القديمة (مطلوب فقط مع الاستبدال)"))
            with gr.Row():
                put("b_ins", gr.Button("✅ نفّذ", variant="primary"))
                put("b_blank", gr.Button("📄 صفحة فارغة بدل الملف"))
            step("٤", "نطاق الترجمة", "اختياري: تترجم جزءاً من الملف فقط (مثلاً من 20 إلى 40)، والباقي يبقى بالأصل أو يُحذف.")
            with gr.Row():
                put("r_on", gr.Checkbox(False, label="حدد نطاقاً"))
                put("r_a", gr.Number(1, label="من صفحة", precision=0, minimum=1))
                put("r_b", gr.Number(1, label="إلى صفحة", precision=0, minimum=1))
            put("r_out", gr.Radio([("تبقى بالأصل (بدون ترجمة)", "keep"), ("تُحذف من الملف النهائي", "delete")], value="keep", label="باقي الصفحات"))
            put("b_range", gr.Button("تطبيق النطاق"))
        with gr.Column(scale=4):
            gr.Markdown("### 👁 الصفحة كما ستظهر الآن")
            put("pg_prev_info", gr.Markdown("بعد أي عملية تظهر هنا الصفحة الجديدة فوراً."))
            put("pg_prev", gr.Image(show_label=False, type="filepath", interactive=False))
            put("b_peek", gr.Button("👁 شاهد الصفحة المكتوب رقمها"))
