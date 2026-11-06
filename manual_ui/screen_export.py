"""Tab «الملف النهائي»."""
import gradio as gr
from ui.common import step
from .consts import fonts
from .reg import put


def build():
    step("١", "الخط الافتراضي", "الخط العربي لكل الفقرات إلا اللي غيّرت خطها. تقدر تضيف خطوطك بوضع ملف ttf في مجلد fonts باسم «Name-Regular.ttf» و«Name-Bold.ttf».")
    put("font", gr.Dropdown(fonts(), value="", show_label=False))
    step("٢", "الملف النهائي", "يبني ملف PDF جديد: يحذف النص الأصلي من الفقرات المترجمة ويكتب ترجمتك مكانه بنفس الموضع. الفقرات اللي ما ترجمتها تبقى بلغتها، فتقدر تسلّم على دفعات. (المعاينة صارت تحت الفقرات في تبويب «الترجمة».)")
    put("b_build", gr.Button("✅ ابنِ الملف النهائي", variant="primary"))
    put("out", gr.File(show_label=False))
