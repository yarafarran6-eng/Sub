"""مترجم الروايات: the entry point. The screen itself lives in `ui/` (the automatic tabs) and `manual_ui/` (the manual editor)."""
import os
from pathlib import Path
import gradio as gr
from core import auth, jobs, launch, monitor
from manual_ui import screen as manual_screen
from manual_ui.consts import DROP_JS, PASTE_JS
from ui import tab_chat, tab_keys, tab_review, tab_settings, tab_translate
from ui.common import CSS, THEME
from ui.header import banner_html, hero_html


ICONS_JS = (Path(__file__).parent / "core" / "icons.js").read_text(encoding="utf-8")
JS = "() => { (" + PASTE_JS.strip().rstrip(";") + ")();\n(" + DROP_JS.strip().rstrip(";") + ")();\n" + tab_chat.CHAT_JS + "\n" + ICONS_JS + " }"   # page scripts: numbered paste + chat list menu


def tick(jid):
    return hero_html(), banner_html(), monitor.jobs_html(), monitor.monitor_html(jid), monitor.keys_html(), monitor.events_html()


with gr.Blocks(title="مترجم الروايات") as demo:
    hero = gr.HTML(hero_html)
    banner = gr.HTML(banner_html)
    with gr.Tabs():
        keys = tab_keys.build()
        trans = tab_translate.build()
        with gr.Tab("٣. ✍ المحرر اليدوي") as tab_manual:
            man = manual_screen.build()
        rev = tab_review.build()
        tab_chat.build()
        tab_settings.build()

    timer = gr.Timer(2)
    timer.tick(tick, trans["jsel"], [hero, banner, trans["jlist"], trans["mon"], trans["kmon"], trans["ev"]])
    timer.tick(monitor.keys_html, None, keys["kpanel"])
    job_choices = tab_translate.job_choices
    from ui.tab_keys import key_choices
    demo.load(lambda: (gr.update(choices=job_choices()), gr.update(choices=tab_review.review_choices()), gr.update(choices=key_choices()), *man["refresh"]()),
              None, [trans["jsel"], rev["rsel"], keys["ksel"]] + man["refresh_outs"])
    rev["tab"].select(lambda: gr.update(choices=tab_review.review_choices()), None, rev["rsel"])
    tab_manual.select(man["refresh"], None, man["refresh_outs"])

if __name__ == "__main__":
    port = int(os.getenv("PORT", "7860"))
    if os.getenv("OPEN_BROWSER"):                       # started from the desktop shortcut / start.bat
        if launch.port_open(port):                      # already running: just show the window, do not start a second copy
            launch.open_site(f"http://127.0.0.1:{port}")
            raise SystemExit(0)
        launch.open_when_ready(port)
    jobs.recover()
    kw = dict(server_name=os.getenv("HOST") or ("0.0.0.0" if os.getenv("SPACE_ID") else "127.0.0.1"),
              server_port=int(os.getenv("PORT", "7860")), auth=auth.check, css=CSS, js=JS, max_file_size="200mb", show_error=True,
              favicon_path=str(Path(__file__).parent / "assets" / "logo.ico"))
    try:
        demo.queue(default_concurrency_limit=8).launch(theme=THEME, **kw)
    except TypeError:
        demo.queue(default_concurrency_limit=8).launch(**kw)
