"""Tab 5: user name, password, spending cap."""
import gradio as gr
from core import auth, priority, updater
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


def _list(paths, n=12):
    return "".join(f"<li><code>{p}</code></li>" for p in paths[:n]) + (f"<li>… و{len(paths) - n} ملف آخر</li>" if len(paths) > n else "")


def do_check():
    guard()
    try:
        r = updater.check()
    except updater.UpdateError as e:
        gr.Warning(str(e), title="تعذّر الفحص")
        return f"<div class='bad'>⚠ {e}</div>", gr.update(), gr.update(visible=False)
    latest = f"آخر تحديث على GitHub: «{r['latest']['message']}» ({r['latest']['date']})"
    if r["up_to_date"]:
        return f"<div class='ok'>✅ نسختك هي الأحدث. {latest}</div>", gr.update(interactive=True), gr.update(visible=False)
    n = len(r["changed"]) + len(r["new"])
    body = (f"<div class='warn'>⬇ في تحديث جاهز: {n} ملف ({len(r['changed'])} يتغيّر، {len(r['new'])} جديد). {latest}"
            f"<ul>{_list(r['new'] + r['changed'])}</ul><p>مجلد بياناتك (المفاتيح والملفات والمحادثات) ما ينلمس.</p></div>")
    return body, gr.update(interactive=True), gr.update(visible=False)


def do_update():
    guard()
    try:
        res = updater.apply()
    except updater.UpdateError as e:
        gr.Warning(str(e), title="فشل التحديث")
        return f"<div class='bad'>⚠ فشل التحديث: {e}. ما انكتب شي ناقص، تقدر تجرب مرة ثانية.</div>", gr.update(visible=False)
    if not res["written"]:
        return "<div class='ok'>✅ نسختك هي الأحدث، ما فيه شي يتحدّث.</div>", gr.update(visible=False)
    gr.Info(f"تحدّث {len(res['written'])} ملف", title="✅ تم التحديث")
    extra = f"<p>{res['pip']}</p>" if res["pip"] else ""
    return (f"<div class='ok'>✅ تحدّث {len(res['written'])} ملف. التغييرات تظهر بعد إعادة التشغيل.{extra}</div>",
            gr.update(visible=res["needs_restart"]))


def do_restart():
    guard()
    gr.Info("الموقع يعيد التشغيل، الصفحة تتحدث لحالها بعد لحظات. إذا طلب منك الدخول اكتب كلمة السر.", title="🔄 إعادة التشغيل")
    updater.restart()
    return "<div class='warn'>🔄 جاري إعادة التشغيل... انتظر قليلاً.</div>"


RELOAD_JS = """() => { setTimeout(() => { const t = setInterval(() => { fetch('/', {cache: 'no-store'}).then(r => { if (r.ok) { clearInterval(t); location.reload(); } }).catch(() => {}); }, 2000); }, 6000); }"""


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
        step("هـ", "تحديث الموقع", "طريقتين للتحديث، وبياناتك (المفاتيح والملفات والمحادثات) ما تنلمس في الاثنين.")
        opt("تحديث الموقع", "ينزّل آخر نسخة من GitHub ويبدّل الملفات اللي تغيّرت فقط.",
            "تتحدث بدون ما تقفل الموقع. والطريقة الثانية (ملف update.bat) تنفع لو الموقع ما اشتغل.",
            "الطريقة الأولى: اضغط «تحقق» ثم «حدّث الآن» ثم «أعد التشغيل». "
            "الطريقة الثانية: اقفل الموقع، شغّل update.bat، ثم start.bat. لا تستخدم الطريقتين في نفس الوقت.")
        with gr.Row():
            b_chk = gr.Button("🔍 تحقق من وجود تحديث")
            b_upd = gr.Button("⬇ حدّث الآن", variant="primary")
            b_rst = gr.Button("🔄 أعد تشغيل الموقع الآن", visible=False)
        upd_msg = gr.HTML()
    b_chk.click(do_check, None, [upd_msg, b_upd, b_rst])
    b_upd.click(do_update, None, [upd_msg, b_rst])
    b_rst.click(do_restart, None, upd_msg, js=RELOAD_JS)
    b_prio.click(save_priority, prio, prio_msg)
    tab.select(refresh_priority, None, prio)
    b_un.click(change_username, [un_new, un_pw], un_msg)
    b_pw.click(change_password, [pw_old, pw_new], pw_msg)
    b_bud.click(save_budget, [bud, reset], bud_msg)
