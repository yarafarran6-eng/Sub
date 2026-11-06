"""Shared pieces of the screen: explanation blocks, step headings, the login guard and the error handling."""
import functools
from pathlib import Path
import gradio as gr
from core import auth

CSS = (Path(__file__).parent / "style.css").read_text(encoding="utf-8")
THEME = gr.themes.Soft(primary_hue="indigo", secondary_hue="violet", neutral_hue="slate")


def opt(title, what, benefit, how):
    """A collapsed explanation block: the arrow shows/hides it."""
    return gr.HTML(
        f"<details class='opt'><summary><span>{title}</span></summary><div class='b'>"
        f"<p><b>ماذا يفعل:</b> {what}</p><p><b>الفائدة:</b> {benefit}</p><p><b>كيف أستخدمه:</b> {how}</p>"
        f"</div></details>", elem_classes="optwrap")


def step(n, title, hint=""):
    return gr.HTML(f"<div class='step'><i>{n}</i>{title}</div>" + (f"<p class='hint'>{hint}</p>" if hint else ""))


def guard():
    if auth.must_change():
        raise gr.Error("غيّر كلمة السر الأولية من تبويب الإعدادات أولاً", title="غيّر كلمة السر")


def safe(fn):
    """Any failure becomes a clear message in the side toast WITH its cause (not a bare red 'Error')."""
    @functools.wraps(fn)
    def wrap(*a, **k):
        try:
            return fn(*a, **k)
        except gr.Error:
            raise
        except Exception as e:
            raise gr.Error(f"{type(e).__name__}: {str(e)[:300]}", title="تعذّر تنفيذ الطلب")
    return wrap


def toast(msg, warn=False):
    (gr.Warning if warn else gr.Info)(msg)
