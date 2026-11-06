"""Small building blocks used by every part of the manual screen."""
import gradio as gr
from .reg import put


def danger(name):
    """A confirmation box that sits RIGHT UNDER the button that asked for it (hidden until asked).
    Registers name_g / name_q / name_yes / name_no. The caller wires: ask button -> [name_g, name_q], name_yes -> the real action."""
    with gr.Group(visible=False, elem_classes="confirm") as g:
        q = gr.Markdown()
        with gr.Row():
            yes = gr.Button("نعم، نفّذ", variant="stop", size="sm")
            no = gr.Button("لا، إلغاء", size="sm")
    put(name + "_g", g), put(name + "_q", q), put(name + "_yes", yes), put(name + "_no", no)
    no.click(lambda: gr.update(visible=False), None, g)
    return g


def option_buttons(name, title):
    """The two buttons under every option of the style panel, each saying exactly what it does."""
    with gr.Row():
        back = gr.Button(f"↩ تراجع خطوة واحدة في {title}", size="sm")
        rst = gr.Button(f"↺ إعادة {title} لقيمة الأصل", size="sm")
    put(f"{name}_back", back), put(f"{name}_rst", rst)
