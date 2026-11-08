"""Tab 5: user name, password, spending cap."""
import gradio as gr
from core import auth, priority
from core.keystore import load_keys
from core.pool import kname
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


N_PRIO = 40          # slots that exist; only as many as your AIs are shown


def _shown():
    return max(1, min(N_PRIO, len(load_keys())))


def _key_opts():
    return [("— بدون —", "")] + [(f"{kname(k)} · {k.get('model') or 'نموذج تلقائي'}", k["id"]) for k in load_keys()]


def _prio_values(role):
    cur = priority.get_order(role)
    return [(cur[i] if i < len(cur) else "") for i in range(N_PRIO)]


def save_priority(*vals):
    """vals = N_PRIO slots of translating then N_PRIO slots of checking."""
    tr = priority.set_order("translate", list(vals[:N_PRIO]))
    ed = priority.set_order("edit", list(vals[N_PRIO:]))
    gr.Info(f"حُفظ الترتيب: الترجمة {len(tr)} ذكاء، التدقيق {len(ed)} ذكاء.", title="✅ حُفظ ترتيب الأولوية")
    return f"حُفظ: الترجمة {len(tr)} · التدقيق {len(ed)}"


def refresh_priority():
    opts = _key_opts()
    n = _shown()
    return [gr.update(choices=opts, value=v, visible=i % N_PRIO < n) for i, v in enumerate(_prio_values("translate") + _prio_values("edit"))]


def build():
    with gr.Tab("٦. الإعدادات") as tab:
        step("أ", "ترتيب أولوية الذكاء الاصطناعي", "رتّب الذكاءات اللي أضفتها: الأول يشتغل، وإذا انتهى حده يتحول تلقائياً للثاني ثم الثالث. ترتيب للترجمة وترتيب للتدقيق.")
        opt("ترتيب الأولوية", "تحدد من يترجم أولاً ومن يدقق أولاً، ومن يكمل لو انتهى حد الأول (حد يومي أو بالدقيقة).",
            "ما تتوقف الترجمة لأن مفتاحاً واحداً خلص، وتقدر تحط الأقوى أول والاحتياطي بعده.",
            "اختر في كل خانة ذكاءً (الأولوية 1 هي الأعلى) واضغط «حفظ الترتيب». عدد الخانات يساوي عدد مفاتيحك، وتزيد لما تضيف مفتاح (تحدّث لما تفتح هذا التبويب). اترك اللي ما تبيه «بدون». "
            "المفاتيح اللي ما حطيتها في القائمة تُستخدم فقط كحل أخير لو انتهت كل مفاتيحك المرتبة.")
        prio = []
        with gr.Row():
            for role, title in (("translate", "🔤 ترتيب الترجمة"), ("edit", "🔍 ترتيب التدقيق")):
                with gr.Column():
                    gr.Markdown(f"**{title}**")
                    for i, v in enumerate(_prio_values(role)):
                        prio.append(gr.Dropdown(_key_opts(), value=v, label=f"الأولوية {i + 1}", interactive=True, visible=i < _shown()))
        b_prio = gr.Button("💾 حفظ الترتيب", variant="primary")
        prio_msg = gr.Markdown()
        step("ب", "اسم المستخدم", "الاسم اللي تكتبه في شاشة الدخول. لو تركته فارغاً يكفي كلمة السر للدخول.")
        opt("تغيير اسم المستخدم", "تختار اسماً (مثل «فيصل») يُطلب منك عند الدخول مع كلمة السر.",
            "يصعّب دخول غيرك. والاسم ما يفرّق بين الحروف الكبيرة والصغيرة.",
            "اكتب الاسم الجديد وكلمة السر الحالية للتأكيد ثم اضغط الزر. اترك الاسم فارغاً لإلغائه.")
        with gr.Row():
            un_new = gr.Textbox(label="اسم المستخدم الجديد", value=auth.username(), scale=2)
            un_pw = gr.Textbox(label="كلمة السر الحالية (للتأكيد)", type="password", scale=2)
        b_un = gr.Button("تغيير اسم المستخدم")
        un_msg = gr.Markdown()
        step("ج", "كلمة السر", "كلمة السر الأولية 2222، ولازم تغيّرها قبل الاستخدام.")
        opt("تغيير كلمة السر", "يغيّر كلمة الدخول للموقع.", "يمنع غيرك من استخدام مفاتيحك.",
            "اكتب الحالية ثم الجديدة (6 خانات فأكثر).")
        with gr.Row():
            pw_old = gr.Textbox(label="الحالية", type="password")
            pw_new = gr.Textbox(label="الجديدة", type="password")
        b_pw = gr.Button("تغيير كلمة السر")
        pw_msg = gr.Markdown()
        step("د", "سقف الصرف")
        opt("سقف الصرف", "أقصى مبلغ بالدولار يصرفه الموقع من المفاتيح المدفوعة.",
            "يوقف المدفوع تلقائياً عند الوصول، ويكمل بالمجاني.", "5 ريال تقريباً 1.33 دولار. علّم «صفّر العداد» لتبدأ حساباً جديداً.")
        bud = gr.Number(get_settings()["budget_usd"], show_label=False)
        reset = gr.Checkbox(False, label="صفّر عداد الصرف")
        b_bud = gr.Button("حفظ")
        bud_msg = gr.Markdown()
    b_prio.click(save_priority, prio, prio_msg)
    tab.select(refresh_priority, None, prio)
    b_un.click(change_username, [un_new, un_pw], un_msg)
    b_pw.click(change_password, [pw_old, pw_new], pw_msg)
    b_bud.click(save_budget, [bud, reset], bud_msg)
