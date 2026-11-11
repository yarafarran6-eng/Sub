"""The manual translation screen: a bar that is always visible, four tabs, and the wiring of every button."""
import gradio as gr
from . import h_boxes, h_files, h_output, h_pages, h_text, panel, screen_edit, screen_export, screen_file, screen_pages
from .consts import SLOTS
from .reg import C, R, put
from .view import file_choices, view
from .widgets import danger

HIDE = lambda: gr.update(visible=False)


def build():
    put("pid", gr.State("")), put("did", gr.State("")), put("cur", gr.State(0)), put("grp", gr.State(0))
    # ---- the bar that never leaves the screen
    put("curbar", gr.HTML("<div class='curbar'>لا يوجد ملف مفتوح. ابدأ من تبويب «الملف».</div>"))
    with gr.Group(elem_classes="undobar"):
        gr.HTML("<div class='ub-t'>هذي الصفحة فقط</div>")
        with gr.Row():
            put("b_undo_pg", gr.Button("↩ تراجع عن آخر تغيير في هذه الصفحة", size="sm"))
            put("b_reset_pg", gr.Button("⟲ أعد هذه الصفحة للأصل", size="sm"))
        danger("resetpg", "نعم، متأكد، احذف تعديلات الصفحة")
        gr.HTML("<div class='ub-t'>الملف كله</div>")
        with gr.Row():
            put("b_undo", gr.Button("↩ تراجع عن آخر تغيير (أي صفحة)", size="sm"))
            put("b_resetall", gr.Button("⟲ أعد المسودة كلها للبداية", size="sm"))
        danger("resetall", "نعم، متأكد، احذف كل التعديلات")
        with gr.Row():
            put("last", gr.Markdown("لا توجد تغييرات للتراجع عنها"))
            put("saved", gr.Markdown())
    with gr.Tabs() as tabs:
        with gr.Tab("١. الملف", id="file"):
            screen_file.build()
        with gr.Tab("٢. الترجمة", id="edit"):
            screen_edit.build()
        with gr.Tab("٣. الصفحات", id="pages"):
            screen_pages.build()
        with gr.Tab("٤. الملف النهائي", id="export"):
            screen_export.build()
    _wire(tabs)
    def refresh():
        from core import priority
        return gr.update(choices=file_choices()), gr.update(choices=priority.choices("translate")), gr.update(choices=priority.choices("edit"))

    return {"files_sel": C["files_sel"], "refresh": refresh, "refresh_outs": [C["files_sel"], C["ai_model"], C["ai_checker"]]}


def _wire(tabs):
    ALL = list(C.values())
    S = [C["pid"], C["did"], C["cur"], C["grp"]]
    ARS = [C[f"s{i}_ar"] for i in range(SLOTS)]
    AIS = [C[k] for k in ("ai_model", "ai_fb", "ai_mode", "ai_checker", "ai_cfb")]
    # the picture of the page arrives as a SECOND step after the action, so clicks answer at once and the picture follows
    P = lambda ev: ev.then(h_text.pv_now, S, [C["pv_img"], C["pv_info"]], show_progress="hidden")
    go_edit = lambda ev: P(ev.then(lambda: gr.Tabs(selected="edit"), None, tabs))

    def ask(btn, name, fn, inputs):
        btn.click(fn, inputs, [C[name + "_g"], C[name + "_q"]])

    def yes(name, fn, inputs):
        P(C[name + "_yes"].click(fn, inputs, ALL)).then(HIDE, None, C[name + "_g"])

    # ---- file tab
    go_edit(C["b_new"].click(h_files.new_file, C["file_in"], ALL))
    go_edit(C["b_open"].click(h_files.open_sel, C["files_sel"], ALL))
    ask(C["b_delfile"], "delfile", h_files.ask_delete_file, [C["pid"], C["files_sel"]])
    yes("delfile", h_files.delete_file, S + [C["files_sel"]])
    P(C["dsel"].input(h_files.switch_draft, [C["pid"], C["dsel"]], ALL))
    P(C["b_dnew"].click(h_files.new_draft, C["pid"], ALL))
    P(C["b_dcopy"].click(h_files.copy_draft, [C["pid"], C["did"]], ALL))
    P(C["b_dren"].click(h_files.rename_draft, [C["pid"], C["did"], C["dname"]], ALL))
    ask(C["b_ddel"], "deldraft", h_files.ask_delete_draft, C["pid"])
    yes("deldraft", h_files.delete_draft, [C["pid"], C["did"]])
    P(C["b_undo"].click(h_files.undo, S, ALL))
    P(C["b_undo_pg"].click(h_files.undo_page, S, ALL))
    ask(C["b_reset_pg"], "resetpg", h_files.ask_reset_page, [C["pid"], C["did"], C["cur"]])
    yes("resetpg", h_files.reset_page, S)
    ask(C["b_resetall"], "resetall", h_files.ask_reset_all, C["pid"])
    yes("resetall", h_files.reset_all, [C["pid"], C["did"]])

    # ---- navigation
    NAV = S + [C["page"]]
    for key, how in (("b_prev", "prev"), ("b_next", "next"), ("b_go", "go"), ("b_todo", "todo")):
        P(C[key].click(lambda *a, how=how: h_text.nav(*a[:5], how, *a[5:]), NAV + ARS, ALL))
    P(C["chap"].input(lambda pid, did, cur, grp, ch, *a: h_text.nav(pid, did, cur, grp, ch, "chap", *a), S + [C["chap"]] + ARS, ALL))
    C["b_grp_prev"].click(lambda pid, did, cur, grp, *a: h_text.group(pid, did, cur, grp, -1, *a), S + ARS, ALL)
    C["b_grp_next"].click(lambda pid, did, cur, grp, *a: h_text.group(pid, did, cur, grp, 1, *a), S + ARS, ALL)
    C["b_save"].click(h_text.save_page, S + ARS, C["saved"])

    # ---- paragraphs
    for i in range(SLOTS):
        ar = C[f"s{i}_ar"]
        ar.blur(lambda pid, did, cur, grp, t, i=i: h_text.blur(pid, did, cur, grp, t, i), S + [ar], C["saved"])
        C[f"s{i}_ai"].click(lambda pid, did, cur, grp, *a, i=i: h_text.ai_slot(pid, did, cur, grp, i, *a), S + AIS, ar)
        C[f"s{i}_rev"].click(lambda pid, did, cur, grp, *a, i=i: h_text.review_slot(pid, did, cur, grp, i, *a), S + AIS, ar)
        C[f"s{i}_ocr"].click(lambda pid, did, cur, grp, i=i: h_text.ocr_slot(pid, did, cur, grp, i), S, C[f"s{i}_en"])
        C[f"s{i}_num"].click(lambda pid, did, cur, grp, t, i=i: h_text.number_lines(pid, did, cur, grp, t, i), S + [ar], ar)
        P(C[f"s{i}_del"].click(lambda pid, did, cur, grp, i=i: h_text.slot_delete(pid, did, cur, grp, i), S, ALL))
    P(C["b_ai_page"].click(h_text.ai_page, S + [C["ai_keep"]] + AIS, ALL))
    P(C["b_rev_page"].click(h_text.review_page, S + AIS, ALL))
    P(C["b_ocr_page"].click(h_text.ocr_page, S, ALL))
    P(C["b_add"].click(h_text.add_para, S + [C["add_after"]], ALL))
    C["style"].blur(h_text.ai_cfg, [C["pid"], C["did"], C["ctx"], C["style"]], C["saved"])
    C["ctx"].blur(h_text.ai_cfg, [C["pid"], C["did"], C["ctx"], C["style"]], C["saved"])
    C["b_ctx"].click(h_text.ai_ctx, [C["pid"], C["did"]], C["ctx"])

    # ---- style blocks: the page one (px "p_") and one under every paragraph (px "s<i>_")
    CT = ("font", "size", "align", "tOn", "tc", "hOn", "hc", "dx", "dy")
    BG = [C[k] for k in ("bg_mode", "bg_c1", "bg_c2", "bg_dir")]
    blocks = [("p_", panel.PAGE, lambda grp: 1)] + [(f"s{i}_", panel.PARA, lambda grp, i=i: int(grp) * SLOTS + i + 1) for i in range(SLOTS)]
    for px, scope, pn in blocks:
        ctl = [C[px + k] for k in CT]
        extra = BG if scope == panel.PAGE else []
        dummy = (lambda: ("none", "#ffffff", "#cccccc", "vertical"))
        if scope == panel.PAGE:
            fn_apply = lambda pid, did, cur, grp, *v: panel.apply(pid, did, cur, grp, panel.PAGE, 1, *v)
        else:
            fn_apply = lambda pid, did, cur, grp, *v, pn=pn: panel.apply(pid, did, cur, grp, panel.PARA, pn(grp), *v, "none", "#ffffff", "#cccccc", "vertical")
        OUT = ctl + extra + [C["last"], C["saved"]]
        for c in ctl + extra:
            c.input(fn_apply, S + ctl + extra, OUT)
        for w in ("font", "size", "align", "tcolor", "hl", "pos") + (("bg",) if scope == panel.PAGE else ()):
            C[f"{px}{w}_rst"].click(lambda pid, did, cur, grp, w=w, px=px, scope=scope, pn=pn: panel.reset(pid, did, cur, grp, scope, pn(grp), w, px), S, OUT)
            C[f"{px}{w}_back"].click(lambda pid, did, cur, grp, w=w, px=px, scope=scope, pn=pn: panel.stepback(pid, did, cur, grp, scope, pn(grp), w, px), S, OUT)
        for k in ("left", "right", "up", "down"):
            C[f"{px}mv_{k}"].click(lambda pid, did, cur, grp, step, k=k, px=px, scope=scope, pn=pn: panel.move(pid, did, cur, grp, scope, pn(grp), k, step, px),
                                   S + [C[px + "step"]], OUT)
    C["bg_preset"].input(lambda pid, did, cur, grp, name: panel.preset(pid, did, cur, grp, panel.PAGE, 1, name), S + [C["bg_preset"]], [C[k] for k in ("bg_mode", "bg_c1", "bg_c2", "bg_dir", "last")])
    ask(C["b_page_all"], "pageall", lambda pid: (gr.update(visible=True), "هل أنت متأكد؟ ستفقد كل تنسيقات هذي الصفحة (خطوط وأحجام وألوان وخلفية ومواضع كل فقراتها) وترجع مثل الأصل. ترجماتك تبقى. تقدر تتراجع بزر «تراجع» بعد التنفيذ."), C["pid"])
    yes("pageall", panel.reset_everything, S)

    # ---- pages tab
    P(C["b_range"].click(h_pages.set_range, S + [C[k] for k in ("r_on", "r_a", "r_b", "r_out")], ALL))
    ask(C["b_delpage"], "delpage", h_pages.ask_delete, [C["pid"], C["did"], C["pg_target"]])
    yes("delpage", h_pages.delete, [C["pid"], C["did"], C["pg_target"]])
    P(C["b_move"].click(h_pages.move, [C["pid"], C["did"], C["pg_target"], C["mv_to"]], ALL))
    P(C["b_swap"].click(h_pages.swap, [C["pid"], C["did"], C["pg_target"], C["sw_with"]], ALL))
    INS = [C["pid"], C["did"], C["ins_op"], C["pg_target"], C["ins_file"], C["ins_page"], C["ins_sure"]]
    P(C["b_ins"].click(lambda *a: h_pages.insert(*a, False), INS, ALL))
    P(C["b_blank"].click(lambda pid, did, op, tg, f, p, s: h_pages.insert(pid, did, op, tg, None, 1, s, True), INS, ALL))
    P(C["b_peek"].click(h_pages.peek, [C["pid"], C["did"], C["pg_target"]], ALL))

    # ---- manage the page that is open in the translation tab
    C["b_bx_show"].click(h_boxes.show, [C["pid"], C["did"], C["cur"]], [C["bx_img"], C["bx_pick"], C["bx_info"]])
    P(C["b_bx_apply"].click(h_boxes.apply, [C["pid"], C["did"], C["cur"], C["bx_pick"], C["bx_con"], C["bx_c"], C["bx_dx"], C["bx_dy"], C["bx_dw"], C["bx_dh"]], ALL))
    P(C["b_bx_del"].click(h_boxes.remove, [C["pid"], C["did"], C["cur"], C["bx_pick"]], ALL))
    P(C["b_bx_rst"].click(h_boxes.restore, [C["pid"], C["did"], C["cur"], C["bx_pick"]], ALL))
    P(C["b_cp_move"].click(h_pages.cur_move, [C["pid"], C["did"], C["cur"], C["cp_to"]], ALL))
    ask(C["b_cp_del"], "cpdel", h_pages.cur_ask_delete, [C["pid"], C["did"], C["cur"]])
    yes("cpdel", h_pages.cur_delete, [C["pid"], C["did"], C["cur"]])
    C["cp_up"].upload(h_pages.cur_pick, C["cp_up"], [C["cp_file"], C["cp_name"], C["cp_prev"]])
    ask(C["b_cp_rep"], "cprep", h_pages.cur_ask_replace, [C["pid"], C["did"], C["cur"], C["cp_file"]])
    P(C["cprep_yes"].click(h_pages.cur_replace, [C["pid"], C["did"], C["cur"], C["cp_file"]], ALL)) \
        .then(HIDE, None, C["cprep_g"]).then(lambda: (None, "لم تختر صورة بعد", gr.update(value=None, visible=False)), None, [C["cp_file"], C["cp_name"], C["cp_prev"]])

    # ---- preview (under the paragraphs) + final file
    C["b_pv_cur"].click(h_output.preview, S + ARS, [C["pv_img"], C["pv_info"]])
    P(C["b_pv_prev"].click(lambda *a: h_text.nav(*a[:5], "prev", *a[5:]), NAV + ARS, ALL))
    P(C["b_pv_next"].click(lambda *a: h_text.nav(*a[:5], "next", *a[5:]), NAV + ARS, ALL))
    C["b_build"].click(h_output.build, S + ARS, C["out"])
    C["font"].input(h_output.default_font, [C["pid"], C["did"], C["font"]], C["saved"])
