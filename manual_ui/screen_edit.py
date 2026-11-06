"""Tab «الترجمة»: page navigation, the page's style at the top, the paragraphs (each with its own style arrow), the live preview below."""
import gradio as gr
from .consts import ALIGN_CHOICES, BG_PRESETS, HL_DEFAULT, SLOTS, fonts
from .reg import put
from .widgets import danger

ROWS = (("font", "الخط"), ("size", "حجم الخط"), ("align", "المحاذاة"), ("tcolor", "لون النص"), ("hl", "لون التحديد"), ("pos", "المكان"))


def _buttons(px, w, title):
    put(f"{px}{w}_back", gr.Button(f"↩ تراجع خطوة في {title}", size="sm", scale=2))
    put(f"{px}{w}_rst", gr.Button(f"↺ إعادة {title} للأصل", size="sm", scale=2))


def style_block(px, page):
    """One option per row, always in the same order: [the control] [↩ step back] [↺ reset to the original]."""
    gr.HTML("<div class='mini'>كل خيار في سطر: القيمة، ثم <b>↩ تراجع خطوة</b> (يلغي آخر تعديل في هذا الخيار فقط)، ثم <b>↺ إعادة</b> (يرجّعه لقيمة الملف الأصلي).</div>")
    with gr.Row(elem_classes="grow"):
        put(f"{px}font", gr.Dropdown(fonts(), value="", label="الخط والأسلوب", scale=4))
        _buttons(px, "font", "الخط")
    with gr.Row(elem_classes="grow"):
        put(f"{px}size", gr.Number(100 if page else 0, label="النسبة % من الحجم الأصلي (100 = كما هو)" if page else "الحجم بالنقطة (0 = الأصلي)", scale=4))
        _buttons(px, "size", "حجم الخط")
    with gr.Row(elem_classes="grow"):
        put(f"{px}align", gr.Dropdown(ALIGN_CHOICES, value="", label="محاذاة النص", scale=4))
        _buttons(px, "align", "المحاذاة")
    with gr.Row(elem_classes="grow"):
        with gr.Row(scale=4):
            put(f"{px}tOn", gr.Checkbox(False, label="غيّر لون النص"))
            put(f"{px}tc", gr.ColorPicker("#000000", label="لون النص"))
        _buttons(px, "tcolor", "لون النص")
    with gr.Row(elem_classes="grow"):
        with gr.Row(scale=4):
            put(f"{px}hOn", gr.Checkbox(False, label="تحديد يحيط بالكلام"))
            put(f"{px}hc", gr.ColorPicker(HL_DEFAULT, label="لون التحديد"))
        _buttons(px, "hl", "لون التحديد")
    with gr.Row(elem_classes="grow"):
        with gr.Row(scale=4):
            put(f"{px}dx", gr.Number(0, label="إزاحة أفقية (نقطة)"))
            put(f"{px}dy", gr.Number(0, label="إزاحة رأسية (نقطة)"))
            put(f"{px}step", gr.Number(5, label="خطوة السهم"))
        _buttons(px, "pos", "المكان")
    with gr.Row(elem_classes="arrows"):
        for k, t in (("left", "◀ يسار"), ("right", "يمين ▶"), ("up", "▲ فوق"), ("down", "▼ تحت")):
            put(f"{px}mv_{k}", gr.Button(t, size="sm"))
    if page:
        with gr.Row(elem_classes="grow"):
            put("bg_preset", gr.Dropdown(list(BG_PRESETS), value=None, label="خلفية الصفحة: قوالب جاهزة", scale=4))
            _buttons(px, "bg", "خلفية الصفحة")
        with gr.Row():
            put("bg_mode", gr.Radio([("الأصلية", "none"), ("لون ثابت", "solid"), ("تدرج", "gradient")], value="none", label="النوع"))
            put("bg_dir", gr.Dropdown([("عمودي", "vertical"), ("أفقي", "horizontal"), ("قطري", "diagonal")], value="vertical", label="اتجاه التدرج"))
            put("bg_c1", gr.ColorPicker("#ffffff", label="اللون الأول"))
            put("bg_c2", gr.ColorPicker("#cccccc", label="اللون الثاني"))
        put("b_page_all", gr.Button("⟲ إعادة تنسيق الصفحة كلها للأصل (الصفحة + كل فقراتها + الخلفية)", size="sm"))
        danger("pageall")


def _slot(i):
    with gr.Group(visible=False, elem_classes="slotcard") as g:
        put(f"s{i}_head", gr.HTML())
        with gr.Row():
            put(f"s{i}_ar", gr.Textbox(label="الترجمة العربية", lines=4, max_lines=16, interactive=True, elem_classes="arbox", rtl=True))
            put(f"s{i}_en", gr.Textbox(label="النص الأصلي", lines=4, max_lines=16, interactive=False, elem_classes="enbox"))
        with gr.Row():
            put(f"s{i}_ai", gr.Button("🤖 ترجم هذي الفقرة", size="sm"))
            put(f"s{i}_ocr", gr.Button("👁 اقرأ من الصورة", size="sm"))
            put(f"s{i}_num", gr.Button("🔢 رقّم الأسطر", size="sm"))
            put(f"s{i}_del", gr.Button("🗑 حذف الفقرة", size="sm"))
        with gr.Accordion("🎨 تنسيق هذي الفقرة (اضغط السهم)", open=False):
            style_block(f"s{i}_", False)
    put(f"s{i}_g", g)


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
    with gr.Accordion("🎨 تنسيق الصفحة كلها: خط، حجم، لون، تحديد، مكان، خلفية (اضغط السهم)", open=False):
        gr.HTML("<div class='mini'>يطبَّق على كل فقرات الصفحة. وتنسيق فقرة بعينها (تحت الفقرة) يغلب تنسيق الصفحة.</div>")
        style_block("p_", True)
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
    gr.HTML("<div class='step'><i>👁</i>معاينة الصفحة كما ستظهر في الملف النهائي</div><p class='hint'>تظهر المعاينة تلقائياً كلما انتقلت لصفحة. زر «معاينة التالية» ينقلك للصفحة التالية بفقراتها ومعاينتها.</p>")
    with gr.Row():
        put("b_pv_prev", gr.Button("◀ معاينة السابقة"))
        put("b_pv_cur", gr.Button("👁 حدّث معاينة هذي الصفحة", variant="primary"))
        put("b_pv_next", gr.Button("معاينة التالية ▶"))
    put("pv_info", gr.Markdown())
    put("pv_img", gr.Image(show_label=False, type="filepath", interactive=False))
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
