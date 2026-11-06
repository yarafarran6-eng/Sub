"""Tab 5: user name, password, spending cap."""
import gradio as gr
from core import auth
from core.config import get_settings, update_settings
from .common import guard, opt, step


def save_budget(usd, reset):
    guard()
    s = update_settings(budget_usd=float(usd), **({"spent_usd": 0.0} if reset else {}))
    return f"السقف {s['budget_usd']}$ · المصروف {s['spent_usd']}$"


def change_username(name, pw):
    msg = auth.set_username(pw, name)
    ok = msg.startswith("تم") or msg.startswith("أُلغي")
    (gr.Info if ok else gr.Warning)(msg)
    return msg + ("\n\nمن الدخول القادم اكتب هذا الاسم." if msg.startswith("تم") else "")


def change_password(old, new):
    msg = auth.change(old, new)
    (gr.Info if msg.startswith("تم") else gr.Warning)(msg)
    return msg


def build():
    with gr.Tab("٥. الإعدادات"):
        step("أ", "اسم المستخدم", "الاسم اللي تكتبه في شاشة الدخول. لو تركته فارغاً يكفي كلمة السر للدخول.")
        opt("تغيير اسم المستخدم", "تختار اسماً (مثل «فيصل») يُطلب منك عند الدخول مع كلمة السر.",
            "يصعّب دخول غيرك. والاسم ما يفرّق بين الحروف الكبيرة والصغيرة.",
            "اكتب الاسم الجديد وكلمة السر الحالية للتأكيد ثم اضغط الزر. اترك الاسم فارغاً لإلغائه.")
        with gr.Row():
            un_new = gr.Textbox(label="اسم المستخدم الجديد", value=auth.username(), scale=2)
            un_pw = gr.Textbox(label="كلمة السر الحالية (للتأكيد)", type="password", scale=2)
        b_un = gr.Button("تغيير اسم المستخدم")
        un_msg = gr.Markdown()
        step("ب", "كلمة السر", "كلمة السر الأولية 2222، ولازم تغيّرها قبل الاستخدام.")
        opt("تغيير كلمة السر", "يغيّر كلمة الدخول للموقع.", "يمنع غيرك من استخدام مفاتيحك.",
            "اكتب الحالية ثم الجديدة (6 خانات فأكثر).")
        with gr.Row():
            pw_old = gr.Textbox(label="الحالية", type="password")
            pw_new = gr.Textbox(label="الجديدة", type="password")
        b_pw = gr.Button("تغيير كلمة السر")
        pw_msg = gr.Markdown()
        step("ج", "سقف الصرف")
        opt("سقف الصرف", "أقصى مبلغ بالدولار يصرفه الموقع من المفاتيح المدفوعة.",
            "يوقف المدفوع تلقائياً عند الوصول، ويكمل بالمجاني.", "5 ريال تقريباً 1.33 دولار. علّم «صفّر العداد» لتبدأ حساباً جديداً.")
        bud = gr.Number(get_settings()["budget_usd"], show_label=False)
        reset = gr.Checkbox(False, label="صفّر عداد الصرف")
        b_bud = gr.Button("حفظ")
        bud_msg = gr.Markdown()
    b_un.click(change_username, [un_new, un_pw], un_msg)
    b_pw.click(change_password, [pw_old, pw_new], pw_msg)
    b_bud.click(save_budget, [bud, reset], bud_msg)
