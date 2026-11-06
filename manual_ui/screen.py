"""The manual translation screen: a bar that is always visible, four tabs, and the wiring of every button."""
import gradio as gr
from . import h_files, h_output, h_pages, h_text, panel, screen_edit, screen_export, screen_file, screen_pages
from .consts import SLOTS
from .reg import C, R, put
from .view import file_choices, view
from .widgets import danger

HIDE = lambda: gr.update(visible=False)


def build():
    put("pid", gr.State("")), put("did", gr.State("")), put("cur", gr.State(0)), put("grp", gr.State(0)), put("pv", gr.State(-1))
    # ---- the bar that never leaves the screen
    put("curbar", gr.HTML("<div class='curbar'>لا يوجد ملف مفتوح. ابدأ من تبويب «الملف».</div>"))
    with gr.Row():
        put("last", gr.Markdown("لا توجد تغييرات للتراجع عنها"))
        put("b_undo", gr.Button("↩ تراجع عن آخر تغيير (أي نوع)", size="sm"))
        put("b_resetall", gr.Button("⟲ إعادة المسودة كلها للبداية", size="sm"))
        put("saved", gr.Markdown())
    danger("resetall")
    with gr.Tabs() as tabs:
        with gr.Tab("١. الملف", id="file"):
            screen_file.build()
        with gr.Tab("٢. الترجمة", id="edit"):
            screen_edit.build()
        with gr.Tab("٣. الصفحات", id="pages"):
            screen_pages.build()
        with gr.Tab("٤. المعاينة والملف النهائي", id="export"):
            screen_export.build()
    _wire(tabs)
    return {"files_sel": C["files_sel"], "refresh": lambda: gr.update(choices=file_choices())}


def _wire(tabs):
    ALL = list(C.values())
    S = [C["pid"], C["did"], C["cur"], C["grp"]]
    ARS = [C[f"s{i}_ar"] for i in range(SLOTS)]
    go_edit = lambda ev: ev.then(lambda: gr.Tabs(selected="edit"), None, tabs)

    def ask(btn, name, fn, inputs):
        btn.click(fn, inputs, [C[name + "_g"], C[name + "_q"]])

    def yes(name, fn, inputs):
        C[name + "_yes"].click(fn, inputs, ALL).then(HIDE, None, C[name + "_g"])

    # ---- file tab
    go_edit(C["b_new"].click(h_files.new_file, C["file_in"], ALL))
    go_edit(C["b_open"].click(h_files.open_sel, C["files_sel"], ALL))
    ask(C["b_delfile"], "delfile", h_files.ask_delete_file, [C["pid"], C["files_sel"]])
    yes("delfile", h_files.delete_file, S + [C["files_sel"]])
    C["dsel"].input(h_files.switch_draft, [C["pid"], C["dsel"]], ALL)
    C["b_dnew"].click(h_files.new_draft, C["pid"], ALL)
    C["b_dcopy"].click(h_files.copy_draft, [C["pid"], C["did"]], ALL)
    C["b_dren"].click(h_files.rename_draft, [C["pid"], C["did"], C["dname"]], ALL)
    ask(C["b_ddel"], "deldraft", h_files.ask_delete_draft, C["pid"])
    yes("deldraft", h_files.delete_draft, [C["pid"], C["did"]])
    C["b_undo"].click(h_files.undo, S, ALL)
    ask(C["b_resetall"], "resetall", h_files.ask_reset_all, C["pid"])
    yes("resetall", h_files.reset_all, [C["pid"], C["did"]])

    # ---- navigation
    NAV = S + [C["page"]]
    for key, how in (("b_prev", "prev"), ("b_next", "next"), ("b_go", "go"), ("b_todo", "todo")):
        C[key].click(lambda *a, how=how: h_text.nav(*a[:5], how, *a[5:]), NAV + ARS, ALL)
    C["chap"].input(lambda pid, did, cur, grp, ch, *a: h_text.nav(pid, did, cur, grp, ch, "chap", *a), S + [C["chap"]] + ARS, ALL)
    C["b_grp_prev"].click(lambda pid, did, cur, grp, *a: h_text.group(pid, did, cur, grp, -1, *a), S + ARS, ALL)
    C["b_grp_next"].click(lambda pid, did, cur, grp, *a: h_text.group(pid, did, cur, grp, 1, *a), S + ARS, ALL)
    C["b_save"].click(h_text.save_page, S + ARS, ALL)

    # ---- paragraphs
    for i in range(SLOTS):
        ar = C[f"s{i}_ar"]
        ar.blur(lambda pid, did, cur, grp, t, i=i: h_text.blur(pid, did, cur, grp, t, i), S + [ar], ALL)
        C[f"s{i}_ai"].click(lambda pid, did, cur, grp, i=i: h_text.ai_slot(pid, did, cur, grp, i), S, ALL)
        C[f"s{i}_ocr"].click(lambda pid, did, cur, grp, i=i: h_text.ocr_slot(pid, did, cur, grp, i), S, ALL)
        C[f"s{i}_num"].click(lambda pid, did, cur, grp, t, i=i: h_text.number_lines(pid, did, cur, grp, t, i), S + [ar], ALL)
        C[f"s{i}_del"].click(lambda pid, did, cur, grp, i=i: h_text.slot_delete(pid, did, cur, grp, i), S, ALL)
        C[f"s{i}_style"].click(lambda pid, did, cur, grp, i=i: panel.pick_para(pid, did, cur, grp, int(grp) * SLOTS + i + 1), S, ALL)
    C["b_ai_page"].click(h_text.ai_page, S + [C["ai_keep"]], ALL)
    C["b_ocr_page"].click(h_text.ocr_page, S, ALL)
    C["b_add"].click(h_text.add_para, S + [C["add_after"]], ALL)
    C["style"].blur(h_text.ai_cfg, [C["pid"], C["did"], C["ctx"], C["style"]], ALL)
    C["ctx"].blur(h_text.ai_cfg, [C["pid"], C["did"], C["ctx"], C["style"]], ALL)
    C["b_ctx"].click(h_text.ai_ctx, [C["pid"], C["did"]], ALL)

    # ---- the style panel
    SC = S + [C["p_scope"], C["p_num"]]
    ctl = [C[k] for k in ("p_font", "p_size", "p_align", "p_tOn", "p_tc", "p_hOn", "p_hc", "p_dx", "p_dy", "bg_mode", "bg_c1", "bg_c2", "bg_dir")]
    for c in ctl:
        c.input(panel.apply, SC + ctl, ALL)
    C["p_scope"].input(panel.load, SC, ALL)
    C["p_num"].input(panel.load, SC, ALL)
    for w in ("font", "size", "align", "tcolor", "hl", "pos", "bg"):
        C[f"{w}_rst"].click(lambda *a, w=w: panel.reset(*a, w), SC, ALL)
        C[f"{w}_back"].click(lambda *a, w=w: panel.stepback(*a, w), SC, ALL)
    for k in ("left", "right", "up", "down"):
        C[f"mv_{k}"].click(lambda *a, k=k: panel.move(*a[:-1], k, a[-1]), SC + [C["p_step"]], ALL)
    C["bg_preset"].input(lambda *a: panel.preset(*a), SC + [C["bg_preset"]], ALL)
    ask(C["b_page_all"], "pageall", lambda pid: (gr.update(visible=True), "هل ترجّع تنسيق الصفحة كلها (خطوط وأحجام وألوان وخلفية ومواضع كل فقراتها) للأصل؟ تقدر تتراجع بعدها."), C["pid"])
    yes("pageall", panel.reset_everything, SC)

    # ---- pages tab
    C["b_range"].click(h_pages.set_range, S + [C[k] for k in ("r_on", "r_a", "r_b", "r_out")], ALL)
    ask(C["b_delpage"], "delpage", h_pages.ask_delete, [C["pid"], C["did"], C["pg_target"]])
    yes("delpage", h_pages.delete, [C["pid"], C["did"], C["pg_target"]])
    C["b_move"].click(h_pages.move, [C["pid"], C["did"], C["pg_target"], C["mv_to"]], ALL)
    C["b_swap"].click(h_pages.swap, [C["pid"], C["did"], C["pg_target"], C["sw_with"]], ALL)
    INS = [C["pid"], C["did"], C["ins_op"], C["pg_target"], C["ins_file"], C["ins_page"], C["ins_sure"]]
    C["b_ins"].click(lambda *a: h_pages.insert(*a, False), INS, ALL)
    C["b_blank"].click(lambda pid, did, op, tg, f, p, s: h_pages.insert(pid, did, op, tg, None, 1, s, True), INS, ALL)
    C["b_peek"].click(h_pages.peek, [C["pid"], C["did"], C["pg_target"]], ALL)

    # ---- preview + final file
    PV = S + [C["pv"]]
    for key, how in (("b_pv_cur", "cur"), ("b_pv_prev", "prev"), ("b_pv_next", "next")):
        C[key].click(lambda pid, did, cur, grp, pv, *a, how=how: h_output.preview(pid, did, cur, grp, pv, how, *a), PV + ARS, ALL)
    go_edit(C["b_pv_edit"].click(lambda pid, did, cur, grp, pv: view(pid, did, int(pv) if pv is not None and int(pv) >= 0 else int(cur), 0, "✍ انتقلت لتحرير الصفحة المعروضة."), PV, ALL))
    C["b_build"].click(h_output.build, S + ARS, ALL)
    C["font"].input(h_output.default_font, [C["pid"], C["did"], C["font"]], ALL)
