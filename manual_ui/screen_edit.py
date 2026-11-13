"""Tab «الترجمة»: page navigation, the page's style at the top, the paragraphs (each with its own style arrow), the live preview below."""
import gradio as gr
from core import priority
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
    with gr.Group(visible=False, elem_classes="slotcard", elem_id=f"slot_{i}") as g:
        put(f"s{i}_head", gr.HTML())
        with gr.Row():
            put(f"s{i}_ar", gr.Textbox(label="الترجمة العربية", lines=4, max_lines=16, interactive=True, elem_classes="arbox", rtl=True))
            put(f"s{i}_en", gr.Textbox(label="النص الأصلي", lines=4, max_lines=16, interactive=False, elem_classes="enbox"))
        with gr.Row():
            put(f"s{i}_ai", gr.Button("🤖 ترجم هذي الفقرة", size="sm"))
            put(f"s{i}_rev", gr.Button("🔍 دقّق ترجمتي", size="sm"))
            put(f"s{i}_ocr", gr.Button("👁 اقرأ من الصورة", size="sm"))
            put(f"s{i}_num", gr.Button("🔢 رقّم الأسطر", size="sm"))
            put(f"s{i}_del", gr.Button("🗑 حذف الفقرة", size="sm"))
            put(f"s{i}_sty", gr.Button("🎨 تنسيق: خط، لون، مكان", size="sm", elem_id=f"sty_{i}"))
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
    with gr.Accordion("🎨 تنسيق الفقرة: يظهر تحت الفقرة اللي تضغط زر «🎨 تنسيق» تحتها", open=False, elem_id="q_panel") as qacc:
        put("q_n", gr.Number(1, label="رقم الفقرة (الأرقام ظاهرة فوق كل فقرة)", precision=0, minimum=1))
        style_block("q_", False)
    put("q_acc", qacc)
    with gr.Accordion("🗂 إدارة هذي الصفحة: نقل · حذف · استبدال بصورة", open=False):
        with gr.Group(elem_classes="pcard"):
            gr.HTML("<div class='pc-t'>↕ نقل الصفحة</div><div class='pc-d'>اكتب رقم المكان الجديد للصفحة، ثم اضغط «انقل».</div>")
            with gr.Row(equal_height=True):
                put("cp_to", gr.Number(1, show_label=False, container=False, precision=0, minimum=1, scale=1, min_width=120))
                put("b_cp_move", gr.Button("انقل", scale=2))
        with gr.Group(elem_classes="pcard"):
            gr.HTML("<div class='pc-t'>🗑 حذف الصفحة</div><div class='pc-d'>تنحذف من الملف النهائي، وتقدر ترجعها بزر «تراجع» فوق.</div>")
            put("b_cp_del", gr.Button("احذف هذي الصفحة", variant="stop"))
            danger("cpdel")
        with gr.Group(elem_classes="pcard"):
            gr.HTML("<div class='pc-t'>🖼 استبدالها بصورة من جهازك</div><div class='pc-d'>أعطني الصورة بأي طريقة من الثلاث، ثم اضغط «استبدل». الصورة تتغير بحجم صفحات الكتاب.</div>")
            put("cp_file", gr.State(None))
            put("cp_up", gr.UploadButton("١. اختر صورة من جهازك", file_types=[".png", ".jpg", ".jpeg", ".webp"], elem_id="cp_up"))
            gr.HTML("<button type='button' id='cp_paste_btn' class='dz-btn'>٢. الصق صورة منسوخة (أو اضغط Ctrl+V)</button>"
                    "<div id='cp_zone' class='dz' tabindex='0'><b>٣. اسحب الصورة وأفلتها هنا</b>"
                    "<div class='dz-msg'>من مجلد أو من سطح المكتب</div></div>")
            put("cp_name", gr.Markdown("لم تختر صورة بعد", elem_classes="pc-name"))
            put("cp_prev", gr.Image(show_label=False, interactive=False, height=170, visible=False, container=False))
            put("b_cp_rep", gr.Button("استبدل هذي الصفحة بالصورة", variant="primary"))
            danger("cprep")
    with gr.Accordion("🟥 صناديق التحديد من الملف الأصلي: لون · حذف · تحريك · حجم", open=False):
        gr.HTML("<div class='mini'>الصناديق الملوّنة اللي حول الكلام في الصفحة الأصلية. 1) اضغط «أظهر الصناديق» 2) اختر رقم الصندوق من القائمة (الأرقام الزرقاء في الصورة) 3) غيّر ما تبغى واضغط «طبّق». النتيجة تظهر في المعاينة تحت.</div>")
        put("b_bx_show", gr.Button("أظهر الصناديق", variant="primary"))
        put("bx_info", gr.Markdown())
        put("bx_img", gr.Image(show_label=False, type="filepath", interactive=False))
        put("bx_pick", gr.Dropdown([], value=None, label="الصندوق"))
        with gr.Row():
            put("bx_con", gr.Checkbox(False, label="غيّر لونه"))
            put("bx_c", gr.ColorPicker("#c0504d", label="اللون الجديد"))
        with gr.Row():
            put("bx_dx", gr.Number(0, label="حرّك يمين/يسار (نقطة)"))
            put("bx_dy", gr.Number(0, label="حرّك فوق/تحت (نقطة)"))
            put("bx_dw", gr.Number(0, label="زِد العرض (نقطة)"))
            put("bx_dh", gr.Number(0, label="زِد الارتفاع (نقطة)"))
        with gr.Row():
            put("b_bx_apply", gr.Button("طبّق على هذا الصندوق", variant="primary"))
            put("b_bx_del", gr.Button("احذف الصندوق", variant="stop"))
            put("b_bx_rst", gr.Button("رجّعه مثل الأصل"))
    with gr.Accordion("🤖 الذكاء الاصطناعي: من يترجم ومن يدقق (ينطبق على أزرار الترجمة والتدقيق تحت)", open=False):
        gr.HTML("<div class='mini'>إذا تركتهم على «حسب ترتيب الأولوية» يمشي على الترتيب اللي ضبطته في الإعدادات. تقدر تختار ذكاءً بعينه، وإذا انتهى حده يكمل على الترتيب (لو علّمت الخانة). التنبيه الجانبي يعرض اسم الذكاء والمدة التقريبية والمتبقي من حده.</div>")
        with gr.Row():
            put("ai_model", gr.Dropdown(priority.choices("translate"), value="auto", label="الذي يترجم", scale=3))
            put("ai_fb", gr.Checkbox(True, label="إذا انتهى حده كمّل على ترتيب الأولوية", scale=2))
        with gr.Row():
            put("ai_mode", gr.Radio([("ترجمة فقط", "only"), ("ترجمة ثم تدقيق", "review")], value="only", label="عند الضغط على «ترجم»", scale=2))
            put("ai_checker", gr.Dropdown(priority.choices("edit"), value="auto", label="الذي يدقق", scale=3))
            put("ai_cfb", gr.Checkbox(True, label="إذا انتهى حد المدقق كمّل على ترتيب الأولوية", scale=2))
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
            put("b_rev_page", gr.Button("🔍 دقّق ترجمات الصفحة"))
            put("b_ocr_page", gr.Button("👁 اقرأ الفقرات غير المقروءة"))
            put("b_save", gr.Button("💾 حفظ الصفحة"))
    gr.HTML("<div class='step'><i>👁</i>معاينة الصفحة كما ستظهر في الملف النهائي</div><p class='hint'>تظهر المعاينة تلقائياً كلما انتقلت لصفحة. زر «معاينة التالية» ينقلك للصفحة التالية بفقراتها ومعاينتها.</p>")
    with gr.Row():
        put("b_pv_prev", gr.Button("◀ معاينة السابقة"))
        put("b_pv_cur", gr.Button("👁 حدّث معاينة هذي الصفحة", variant="primary"))
        put("b_pv_next", gr.Button("معاينة التالية ▶"))
    put("pv_info", gr.Markdown())
    put("pv_img", gr.Image(show_label=False, type="filepath", interactive=False, elem_id="pv_img"))
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
