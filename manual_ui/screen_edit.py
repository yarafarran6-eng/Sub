"""Tab «الترجمة»: page navigation, the paragraphs, and the style panel."""
import gradio as gr
from ui.common import opt
from . import panel
from .consts import ALIGN_CHOICES, BG_PRESETS, HL_DEFAULT, SLOTS, fonts
from .reg import put
from .widgets import danger, option_buttons


def _slot(i):
    with gr.Group(visible=False, elem_classes="slotcard") as g:
        put(f"s{i}_head", gr.HTML())
        with gr.Row():
            put(f"s{i}_ar", gr.Textbox(label="الترجمة العربية", lines=3, max_lines=14, interactive=True, elem_classes="arbox", rtl=True))
            put(f"s{i}_en", gr.Textbox(label="النص الأصلي", lines=3, max_lines=14, interactive=False, elem_classes="enbox"))
        with gr.Row():
            put(f"s{i}_ai", gr.Button("🤖 ترجم هذي الفقرة", size="sm"))
            put(f"s{i}_style", gr.Button("🎨 تنسيق هذي الفقرة", size="sm"))
            put(f"s{i}_ocr", gr.Button("👁 اقرأ من الصورة", size="sm"))
            put(f"s{i}_num", gr.Button("🔢 رقّم الأسطر", size="sm"))
            put(f"s{i}_del", gr.Button("🗑 حذف الفقرة", size="sm"))
    put(f"s{i}_g", g)


def _panel():
    with gr.Column(elem_classes="stylepanel"):
        put("p_title", gr.Markdown("### 🎨 التنسيق"))
        gr.HTML("<div class='mini'>تحت كل خيار زران: <b>↩ تراجع خطوة</b> يلغي آخر تعديل في هذا الخيار فقط، و<b>↺ إعادة</b> يرجّعه لقيمة الملف الأصلي.</div>")
        with gr.Row():
            put("p_scope", gr.Radio(panel.SCOPES, value=panel.PAGE, label="ما الذي أنسّقه؟", scale=3))
            put("p_num", gr.Number(1, label="رقم الفقرة", precision=0, minimum=1, scale=1))
        with gr.Group():
            put("p_font", gr.Dropdown(fonts(), value="", label="الخط والأسلوب"))
            option_buttons("font", "الخط")
        with gr.Group():
            put("p_size", gr.Number(100, label="حجم الخط"))
            option_buttons("size", "حجم الخط")
        with gr.Group():
            put("p_align", gr.Dropdown(ALIGN_CHOICES, value="", label="محاذاة النص"))
            option_buttons("align", "المحاذاة")
        with gr.Group():
            with gr.Row():
                put("p_tOn", gr.Checkbox(False, label="غيّر لون النص"))
                put("p_tc", gr.ColorPicker("#000000", label="لون النص"))
            option_buttons("tcolor", "لون النص")
        with gr.Group():
            with gr.Row():
                put("p_hOn", gr.Checkbox(False, label="تحديد يحيط بالكلام"))
                put("p_hc", gr.ColorPicker(HL_DEFAULT, label="لون التحديد"))
            option_buttons("hl", "لون التحديد")
        with gr.Group():
            with gr.Row():
                put("p_dx", gr.Number(0, label="إزاحة أفقية (نقطة)"))
                put("p_dy", gr.Number(0, label="إزاحة رأسية (نقطة)"))
                put("p_step", gr.Number(5, label="خطوة السهم"))
            with gr.Row(elem_classes="arrows"):
                for k, t in (("left", "◀ يسار"), ("right", "يمين ▶"), ("up", "▲ فوق"), ("down", "▼ تحت")):
                    put(f"mv_{k}", gr.Button(t, size="sm"))
            option_buttons("pos", "المكان")
        with gr.Group(visible=True) as bgbox:
            put("bg_preset", gr.Dropdown(list(BG_PRESETS), value=None, label="خلفية الصفحة: قوالب جاهزة"))
            with gr.Row():
                put("bg_mode", gr.Radio([("الأصلية", "none"), ("لون ثابت", "solid"), ("تدرج", "gradient")], value="none", label="النوع"))
                put("bg_dir", gr.Dropdown([("عمودي", "vertical"), ("أفقي", "horizontal"), ("قطري", "diagonal")], value="vertical", label="اتجاه التدرج"))
            with gr.Row():
                put("bg_c1", gr.ColorPicker("#ffffff", label="اللون الأول"))
                put("bg_c2", gr.ColorPicker("#cccccc", label="اللون الثاني"))
            option_buttons("bg", "خلفية الصفحة")
        put("p_bg_box", bgbox)
        put("b_page_all", gr.Button("⟲ إعادة تنسيق الصفحة كلها للأصل (الصفحة + كل فقراتها + الخلفية)", size="sm"))
        danger("pageall")


def build():
    with gr.Row():
        put("chap", gr.Dropdown([], value=None, label="الفصول", interactive=True, scale=2))
        put("b_prev", gr.Button("◀ الصفحة السابقة", scale=1))
        put("page", gr.Number(1, label="رقم الصفحة", precision=0, minimum=1, scale=1))
        put("b_go", gr.Button("اذهب", scale=1))
        put("b_next", gr.Button("الصفحة التالية ▶", scale=1))
        put("b_todo", gr.Button("أقرب صفحة ناقصة", scale=1))
    put("info", gr.Markdown())
    put("note", gr.Markdown())
    with gr.Row():
        with gr.Column(scale=5):
            for i in range(SLOTS):
                _slot(i)
            put("pager", gr.Markdown())
            with gr.Row():
                put("b_grp_prev", gr.Button("◀ الفقرات السابقة"))
                put("b_grp_next", gr.Button("الفقرات التالية ▶"))
            with gr.Group():
                gr.Markdown("**لكل الصفحة:**")
                with gr.Row():
                    put("ai_keep", gr.Checkbox(True, label="لا تستبدل الفقرات اللي كتبتها بيدي"))
                    put("b_ai_page", gr.Button("🤖 ترجم كل فقرات الصفحة", variant="primary"))
                    put("b_ocr_page", gr.Button("👁 اقرأ الفقرات غير المقروءة"))
                    put("b_save", gr.Button("💾 حفظ الصفحة"))
            with gr.Accordion("➕ إضافة فقرة جديدة في هذي الصفحة", open=False):
                with gr.Row():
                    put("add_after", gr.Number(0, label="أضفها بعد الفقرة رقم (0 = بالأعلى)", precision=0, minimum=0))
                    put("b_add", gr.Button("➕ أضف الفقرة"))
            with gr.Accordion("🖼 صورة الصفحة الأصلية (اقرأ منها لو النص غير مقروء)", open=False):
                put("orig", gr.Image(show_label=False, type="filepath", interactive=False))
            with gr.Accordion("🤖 تعليمات الذكاء: الأسلوب والمسرد", open=False):
                put("style", gr.Textbox(label="وصف الأسلوب", lines=2, placeholder="مثال: سرد أدبي فصيح"))
                put("ctx", gr.Textbox(label="بطاقة السياق (أسماء ومصطلحات)", lines=6, elem_classes="ltr"))
                put("b_ctx", gr.Button("بناء المسرد من نص الملف"))
        with gr.Column(scale=4):
            _panel()
