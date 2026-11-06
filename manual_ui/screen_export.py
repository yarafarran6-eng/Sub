"""Tab «المعاينة والملف النهائي»."""
import gradio as gr
from ui.common import opt, step
from .consts import fonts
from .reg import put


def build():
    step("١", "الخط الافتراضي", "الخط العربي لكل الفقرات إلا اللي غيّرت خطها. تقدر تضيف خطوطك بوضع ملف ttf في مجلد fonts باسم «Name-Regular.ttf» و«Name-Bold.ttf».")
    put("font", gr.Dropdown(fonts(), value="", show_label=False))
    step("٢", "المعاينة", "أي صفحة كما ستظهر في الملف النهائي بترجمتك وتنسيقك.")
    with gr.Row():
        put("b_pv_prev", gr.Button("◀ معاينة السابقة"))
        put("b_pv_cur", gr.Button("👁 معاينة الصفحة الحالية", variant="primary"))
        put("b_pv_next", gr.Button("معاينة التالية ▶"))
        put("b_pv_edit", gr.Button("✍ حرّر الصفحة المعروضة"))
    put("pv_info", gr.Markdown())
    put("pv_img", gr.Image(show_label=False, type="filepath", interactive=False))
    step("٣", "الملف النهائي", "يبني ملف PDF جديد: يحذف النص الأصلي من الفقرات المترجمة ويكتب ترجمتك مكانه بنفس الموضع. الفقرات اللي ما ترجمتها تبقى بلغتها، فتقدر تسلّم على دفعات.")
    put("b_build", gr.Button("✅ ابنِ الملف النهائي", variant="primary"))
    put("out", gr.File(show_label=False))
