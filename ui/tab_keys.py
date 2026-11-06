"""Tab 1: add, test and manage the keys."""
import gradio as gr
from core import llm, modelpick, monitor
from core.keystore import (ADDRESS_CHOICES, PROVIDERS, add_key_generic, detect_base, delete_key, load_keys, mask, provider_from_base, update_key)
from core.pool import POOL, human, kname
from .common import guard, opt, step, safe

ROLE_CHOICES = [("ترجمة وتدقيق", "both"), ("ترجمة فقط", "translate"), ("تدقيق فقط", "edit")]

# ------------------------------------------------------------------ keys
def key_choices():
    return [(f"{kname(k)} · {mask(k['key'])} [{k['id']}]", k["id"]) for k in load_keys()]


def _models_text(ids, current):
    return "النماذج المتاحة عندهم: " + "، ".join(ids[:14]) + (" ..." if len(ids) > 14 else "")


def test_key(k):
    """Tests a key and ALWAYS says why it failed. Returns (ok, message)."""
    name, model = kname(k), k.get("model", "")
    base = k.get("base") or PROVIDERS[k["provider"]]["base"]
    try:
        llm.chat(k, [{"role": "user", "content": "Reply with the single word OK"}], 20, 0, "ping", 60)
        POOL.revive(k["id"])
        POOL.mark_verified(k["id"], True)
        return True, f"✅ «{name}» شغّال."
    except llm.RateLimited as e:
        if e.reason == "zero":
            reason = (f"الحصة المجانية لنموذج «{model or 'تلقائي'}» تساوي صفر عندهم، فهو غير متاح بدون دفع أو غير مفعّل لمفتاحك. "
                      f"جرّب «اختيار النموذج تلقائياً». رد الخدمة: {e.detail}")
            POOL.mark_verified(k["id"], False, reason)
            return False, f"❌ «{name}»: {reason}"
        POOL.revive(k["id"])
        POOL.mark_verified(k["id"], True)
        kind = "اليومي" if e.reason == "day" else "حد الدقيقة"
        return True, (f"⚠ «{name}» صحيح لكن الخدمة ردّت بأنه وصل الحد {kind}، ويرجع بعد {human(e.retry_after)}. "
                      f"رد الخدمة: {e.detail}")
    except llm.KeyDead as e:
        POOL.kill(k, str(e))
        return False, f"❌ «{name}»: المفتاح مرفوض أو بدون صلاحية. رد الخدمة: {e}"
    except llm.BadRequest as e:
        s_, low = str(e), str(e).lower()
        if s_.startswith("404") or "not found" in low or "does not exist" in low:
            ids, err = None, ""
            try:
                ids = llm.list_models(k["provider"], k.get("key", ""), base)
            except Exception as ex:
                err = str(ex)
            if ids and model not in ids:
                reason = f"اسم النموذج «{model}» غير موجود عند هذه الخدمة. " + _models_text(ids, model)
            elif ids is None:
                reason = f"العنوان أو اسم النموذج غير صحيح (404). رد الخدمة: {s_}. وتعذر جلب قائمة النماذج: {err}"
            else:
                reason = f"رد الخدمة: {s_}"
        elif s_.startswith("402") or any(w in low for w in ("quota", "billing", "insufficient", "credit", "balance", "payment")):
            reason = f"الرصيد أو الحصة غير كافية. رد الخدمة: {s_}"
        else:
            reason = f"الخدمة رفضت الطلب. رد الخدمة: {s_}"
        POOL.mark_verified(k["id"], False, reason)
        return False, f"❌ «{name}»: {reason}"
    except llm.Transient as e:
        POOL.mark_verified(k["id"], False, str(e))
        return False, f"❌ «{name}»: {e}"
    except Exception as e:
        reason = f"خطأ غير متوقع ({type(e).__name__}): {str(e)[:160]}"
        POOL.mark_verified(k["id"], False, reason)
        return False, f"❌ «{name}»: {reason}"


def auto_model(k):
    """Lets the site choose a working model for this key. Returns (ok, message)."""
    name = kname(k)
    res = modelpick.auto_pick(k)
    if res["ok"]:
        update_key(k["id"], model=res["model"])
        POOL.revive(k["id"])
        POOL.mark_verified(k["id"], True)
        shown = f"«{res['model']}»" if res["model"] else "(بدون اسم، الخدمة تختار بنفسها)"
        return True, (f"✅ «{name}» شغّال. اخترت له النموذج {shown} تلقائياً. "
                      "تقدر تغيّره من «إدارة مفتاح». لو خدمتك مدفوعة وتبي تتحكم بالتكلفة، اكتب النموذج بنفسك.")
    if res["kind"] == "key":
        POOL.kill(k, res["reason"])
    else:
        POOL.mark_verified(k["id"], False, res["reason"])
    return False, f"❌ «{name}»: {res['reason']}"


def fetch_models_ui(addr, key):
    addr = (addr or "").strip()
    if not addr:
        return gr.update(), "❌ اختر الخدمة أو اكتب عنوانها أولاً."
    try:
        ids = llm.list_models(provider_from_base(addr), (key or "").strip(), addr)
    except llm.KeyDead as e:
        return gr.update(), f"❌ المفتاح مرفوض. رد الخدمة: {e}"
    except Exception as e:
        return gr.update(), f"❌ تعذر جلب القائمة: {e}. تقدر تكتب اسم النموذج بيدك."
    if not ids:
        return gr.update(), "ما رجعت الخدمة أي نموذج. اكتب اسم النموذج بيدك."
    return gr.update(choices=ids, value=None), f"✅ وجدت {len(ids)} نموذج. اختر واحداً من خانة النموذج."


def fetch_models_for_key(kid):
    k = next((x for x in load_keys() if x["id"] == kid), None)
    if not k:
        raise gr.Error("اختر مفتاحاً من القائمة")
    return fetch_models_ui(k.get("base") or PROVIDERS[k["provider"]]["base"], k.get("key", ""))


def on_key_change(key, addr):
    base = detect_base(key)
    if base and not (addr or "").strip():
        return gr.update(value=base)
    return gr.update()


def add_key_ui(name, key, addr, model, role, paid, pin, pout, rpm, dreq, dtok):
    guard()
    addr, key = (addr or "").strip(), (key or "").strip()
    if not addr:
        raise gr.Error("اختر الخدمة من القائمة، أو الصق عنوانها")
    if not addr.startswith("http"):
        raise gr.Error("العنوان لازم يبدأ بـ http أو https")
    if "رقم_الحساب" in addr:
        raise gr.Error("بدّل «رقم_الحساب» في العنوان برقم حسابك الحقيقي (تلقاه في لوحة Cloudflare)")
    warn = ""
    det = detect_base(key)
    if det and det.rstrip("/") != addr.rstrip("/"):
        warn = "\n\n⚠ شكل المفتاح يدل على خدمة ثانية غير العنوان اللي اخترته. لو فشل الاختبار فهذا غالباً السبب."
    entry = add_key_generic(name, key, addr, (model or "").strip(), role, paid, pin, pout, rpm, dreq, dtok)
    if (model or "").strip():
        ok, msg = test_key(entry)
    else:
        ok, msg = auto_model(entry)
    return "", "", key_panel(), gr.update(choices=key_choices()), msg + warn


def key_panel():
    return monitor.keys_html()


def key_action(kid, what, newval=""):
    guard()
    if not kid:
        raise gr.Error("اختر مفتاحاً من القائمة")
    k = next((x for x in load_keys() if x["id"] == kid), None)
    msg = "تم"
    if what == "delete":
        if k and k.get("env"):
            msg = "هذا المفتاح قادم من إعدادات الاستضافة، احذفه من هناك."
        else:
            delete_key(kid)
            msg = "🗑 حُذف المفتاح."
    elif what in ("toggle", "rename", "model", "role") and k and k.get("env"):
        msg = "هذا المفتاح قادم من إعدادات الاستضافة، عدّله من هناك."
    elif what == "toggle" and k:
        update_key(kid, enabled=not k.get("enabled"))
        POOL.revive(kid)
        msg = "تم التفعيل." if not k.get("enabled") else "تم الإيقاف المؤقت."
    elif what == "test" and k:
        ok, msg = test_key(k)
    elif what == "rename" and k:
        if not (newval or "").strip():
            raise gr.Error("اكتب الاسم الجديد")
        update_key(kid, label=newval.strip())
        msg = f"✏ صار الاسم «{newval.strip()}»."
    elif what == "role" and k:
        if newval not in ("both", "translate", "edit"):
            raise gr.Error("اختر الاستخدام الجديد من القائمة")
        update_key(kid, role=newval)
        msg = "✔ صار استخدام «" + kname(k) + "»: " + monitor.ROLE_AR[newval] + "."
    elif what == "auto" and k:
        ok, msg = auto_model(k)
    elif what == "model" and k:
        if not (newval or "").strip():
            raise gr.Error("اختر النموذج الجديد أو اكتب اسمه، أو اضغط «اختيار النموذج تلقائياً»")
        update_key(kid, model=newval.strip())
        POOL.revive(kid)
        ok, msg = test_key(next(x for x in load_keys() if x["id"] == kid))
        msg = "غيّرت النموذج. " + msg
    return key_panel(), gr.update(choices=key_choices(), value=None if what == "delete" else kid), msg


def test_all():
    guard()
    out = []
    for k in load_keys():
        if k.get("enabled"):
            ok, m = test_key(k)
            out.append(f"- {m}")
    return key_panel(), "\n".join(out) or "ما فيه مفاتيح"


def build():
    """Draws the tab and returns the parts other tabs refresh."""
    with gr.Tab("١. المفاتيح"):
        step("أ", "أضف مفتاحاً", "تعطي الموقع: اسماً تختاره، والمفتاح، وعنوان الخدمة، وهو يختار النموذج بنفسه. أي خدمة تدعم الطريقة المعيارية (OpenAI) تشتغل، مو بس اللي في القائمة. المفاتيح تُحفظ على جهازك فقط.")
        opt("الاسم", "اسم تختاره أنت عشان تعرف المفتاح، مثل «سيارة» أو «فيصل» أو «جيميني الأول».",
            "يظهر في الجداول والتنبيهات، وما له علاقة باسم النموذج.", "اكتب أي اسم. لو تركته فارغاً يسمّيه الموقع باسم عنوان الخدمة.")
        k_name = gr.Textbox(show_label=False, placeholder="مثال: سيارة، فيصل، جيميني الأول")
        opt("المفتاح", "الرمز السري اللي تعطيك إياه الخدمة.", "بدونه ما تقبل الخدمة الطلبات (إلا الخدمات المحلية).",
            "الصقه هنا. لو الخدمة محلية بدون مفتاح، مثل Ollama، اتركه فارغاً.")
        k_key = gr.Textbox(show_label=False, type="password", placeholder="الصق المفتاح هنا (اتركه فارغاً للخدمات المحلية)")
        opt("عنوان الخدمة", "الرابط اللي يرسل له الموقع الطلبات.",
            "تستخدم أي شركة أو برنامج محلي، مو بس القائمة.",
            "اختر من القائمة، أو الصق عنوان أي خدمة من صفحة وثائقها (يبدأ بـ https). لـ Ollama اختر «Ollama (على جهازك)». لو المفتاح معروف الشكل يتعبى العنوان لحاله.")
        k_addr = gr.Dropdown(ADDRESS_CHOICES, value=None, allow_custom_value=True, show_label=False,
                             elem_classes="ltr", info="اختر من القائمة أو الصق أي عنوان")
        with gr.Accordion("خيارات إضافية", open=False):
            opt("النموذج (اختياري)", "اسم «العقل» اللي يترجم عند هذه الخدمة.",
                "لو تركته فارغاً يختار الموقع بنفسه: يسأل الخدمة عن قائمتها ويجرّب لين يلقى نموذجاً يشتغل، وإذا الخدمة ما تعرض قائمة يرسل الطلب بدون اسم نموذج.",
                "اتركه فارغاً. اكتبه فقط لو تبي نموذجاً معيناً، أو خدمتك مدفوعة وتبي تتحكم بالتكلفة. وتقدر تضغط «جلب النماذج المتاحة» لتختار من قائمتهم.")
            k_model = gr.Dropdown([], value=None, allow_custom_value=True, show_label=False, elem_classes="ltr")
            b_fetch = gr.Button("جلب النماذج المتاحة من الخدمة")
            opt("الاستخدام", "يحدد هل المفتاح يشارك في الترجمة أو المراجعة أو الاثنين.",
                "تخصص المفتاح الأقوى للتدقيق والبقية للترجمة.", "اتركه «ترجمة وتدقيق» لو ما عندك سبب ثاني.")
            k_role = gr.Dropdown(ROLE_CHOICES, value="both", show_label=False)
            opt("حد الطلبات بالدقيقة", "كم طلب يرسل الموقع لهذا المفتاح كل دقيقة كحد أعلى.",
                "يمنع الوصول للحد بسرعة. ولو وصل الحد فعلاً، الموقع ينتظر ويحوّل لمفتاح ثاني.",
                "اتركه 0 ليختار الموقع قيمة مناسبة، أو اكتب الرقم اللي تعرفه من حد خدمتك.")
            k_rpm = gr.Number(0, show_label=False, precision=0)
            opt("حدودك اليومية (اختياري)", "لو تعرف الحد اليومي لهذا المفتاح من صفحة الخدمة، اكتبه هنا.",
                "الموقع يحسب لك كم المتبقي منه اليوم. بدونه يعرض فقط ما تعلنه الخدمة (إن أعلنت) وعدّاد البرنامج.",
                "اكتب عدد الطلبات اليومية وعدد التوكنات اليومية، أو اتركهما 0 إن كنت ما تعرفهما.")
            with gr.Row():
                k_dreq = gr.Number(0, label="الحد اليومي للطلبات", precision=0)
                k_dtok = gr.Number(0, label="الحد اليومي للتوكنات", precision=0)
            opt("مفتاح مدفوع", "تعلّم الموقع إن هذا المفتاح يخصم من رصيدك.",
                "الموقع يحسب الصرف ويوقف المدفوع عند السقف، ويستخدم المجاني أولاً. (الاختيار التلقائي للنموذج لا يعرف الأسعار.)",
                "علّمه فقط لو مفتاحك مدفوع، واكتب الأسعار من صفحة أسعار الخدمة.")
            k_paid = gr.Checkbox(False, label="هذا المفتاح مدفوع")
            with gr.Row(visible=False) as price_row:
                k_pin = gr.Number(0, label="سعر الإدخال بالدولار لكل مليون توكن")
                k_pout = gr.Number(0, label="سعر الإخراج بالدولار لكل مليون توكن")
        b_addk = gr.Button("إضافة المفتاح واختباره", variant="primary")
        kmsg = gr.Markdown()
        step("ب", "مفاتيحك وحالتها الآن", "الحالة تتحدث لحظياً، وأي فشل يظهر معه سببه.")
        kpanel = gr.HTML(key_panel)
        opt("إدارة مفتاح", "اختر مفتاحاً ثم اختبره، أوقفه مؤقتاً، غيّر اسمه أو نموذجه، أو احذفه.",
            "تصلح مفتاحاً فشل بدون ما تعيد إضافته.", "اختر المفتاح من القائمة ثم اضغط الزر المناسب.")
        ksel = gr.Dropdown(key_choices(), show_label=False, value=None, interactive=True)
        with gr.Row():
            b_test = gr.Button("اختبار")
            b_tog = gr.Button("تفعيل / إيقاف")
            b_delk = gr.Button("حذف")
            b_testall = gr.Button("اختبار الكل")
        with gr.Row():
            k_newname = gr.Textbox(show_label=False, placeholder="الاسم الجديد", scale=3)
            b_rename = gr.Button("تغيير الاسم", scale=1)
        with gr.Row():
            k_newmodel = gr.Dropdown([], value=None, allow_custom_value=True, show_label=False,
                                     info="النموذج الجديد (اكتبه أو اجلب القائمة)", elem_classes="ltr", scale=3)
            b_fetch2 = gr.Button("جلب نماذج هذا المفتاح", scale=1)
            b_model = gr.Button("تغيير النموذج", scale=1)
        b_auto = gr.Button("اختيار النموذج تلقائياً لهذا المفتاح")
        opt("تغيير وظيفة المفتاح", "تحويل المفتاح بين الترجمة والتدقيق في أي وقت.",
            "تخصص المفاتيح الأقوى للتدقيق أو للترجمة حسب ما تحتاج، بدون حذف وإعادة إضافة.",
            "اختر المفتاح من الأعلى، ثم اختر الوظيفة الجديدة واضغط الزر.")
        with gr.Row():
            k_newrole = gr.Dropdown(ROLE_CHOICES, value="both", show_label=False, scale=3)
            b_role = gr.Button("تغيير الاستخدام", scale=1)
    k_key.change(on_key_change, [k_key, k_addr], k_addr)
    k_paid.change(lambda v: gr.update(visible=v), k_paid, price_row)
    b_fetch.click(fetch_models_ui, [k_addr, k_key], [k_model, kmsg])
    b_fetch2.click(fetch_models_for_key, ksel, [k_newmodel, kmsg])
    b_addk.click(add_key_ui, [k_name, k_key, k_addr, k_model, k_role, k_paid, k_pin, k_pout, k_rpm, k_dreq, k_dtok],
                 [k_key, k_name, kpanel, ksel, kmsg])
    b_test.click(lambda k: key_action(k, "test"), ksel, [kpanel, ksel, kmsg])
    b_tog.click(lambda k: key_action(k, "toggle"), ksel, [kpanel, ksel, kmsg])
    b_delk.click(lambda k: key_action(k, "delete"), ksel, [kpanel, ksel, kmsg])
    b_rename.click(lambda k, n: key_action(k, "rename", n), [ksel, k_newname], [kpanel, ksel, kmsg])
    b_model.click(lambda k, m: key_action(k, "model", m), [ksel, k_newmodel], [kpanel, ksel, kmsg])
    b_auto.click(lambda k: key_action(k, "auto"), ksel, [kpanel, ksel, kmsg])
    b_role.click(lambda k, r: key_action(k, "role", r), [ksel, k_newrole], [kpanel, ksel, kmsg])
    b_testall.click(test_all, None, [kpanel, kmsg])
    return {"ksel": ksel, "kpanel": kpanel}
