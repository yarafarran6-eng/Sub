"""Tab 5: chat with the AIs about anything. Pick one, switch any time; when its limit ends the next one in your priority answers."""
import time
import gradio as gr
from core import llm, priority
from core.keystore import load_keys
from core.pool import AllBusy, NoKeys, POOL, call, kname, use_route
from .common import guard, safe

SYSTEM = "You are a helpful assistant. Answer in the language the user writes in (Arabic unless they write another language), clearly and simply."


def remaining_html():
    """A small table: every AI and what is left of its limit now."""
    rows = []
    now = time.time()
    for s in POOL.status():
        k = s["k"]
        r = POOL._rt(k["id"])
        if not k.get("enabled"):
            continue
        st = "ينتظر تجدد الحد" if r["cool"] > now else ("مرفوض" if r["dead"] else "جاهز")
        rows.append(f"<tr><td><b>{kname(k)}</b><div class='sub'>{k.get('model') or 'تلقائي'}</div></td><td>{st}</td><td>{priority.brief_limit(k)}</td></tr>")
    if not rows:
        return "<div class='empty'>ما أضفت أي مفتاح بعد. أضف من تبويب المفاتيح.</div>"
    return "<div class='tbl'><table><thead><tr><th>الذكاء</th><th>الحالة</th><th>المتبقي</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"


@safe
def send(history, text, model, fb):
    guard()
    text = (text or "").strip()
    if not text:
        raise gr.Error("اكتب رسالتك أولاً", title="الرسالة فاضية")
    history = list(history or []) + [{"role": "user", "content": text}]
    msgs = [{"role": "system", "content": SYSTEM}] + [{"role": m["role"], "content": m["content"] if isinstance(m["content"], str) else str(m["content"])}
                                                       for m in history[-24:]]
    route = priority.new_route("translate", model or priority.AUTO, bool(fb), max_wait=45)
    if not model or model == priority.AUTO:             # chat may use any key, in the translating priority order
        route = {**route, "order": priority.order_for("translate") or priority.order_for("edit")}
    try:
        with use_route(route):
            meta = {}
            answer = call(msgs, role="any", max_tokens=2048, temperature=0.7, task="chat", meta=meta)
    except NoKeys as e:
        history.pop()
        raise gr.Error(str(e), title="ما فيه ذكاء يرد الآن")
    k = next((x for x in load_keys() if x["id"] == meta.get("key_id")), None)
    note = f"\n\n<sub>— {meta.get('name', '?')} ({meta.get('model') or 'تلقائي'}) · {meta.get('secs', 0):.1f} ثانية" + (f" · {priority.brief_limit(k)}" if k else "") + "</sub>"
    history.append({"role": "assistant", "content": answer + note})
    if len({c["id"] for c in route["calls"]}) > 1:
        gr.Info("انتهى حد الذكاء السابق، فرد عليك التالي في ترتيب الأولوية.", title="🔁 تحوّل تلقائي")
    return history, "", remaining_html()


def choices():
    return priority.choices("any", True, "حسب ترتيب الأولوية في الإعدادات")


def build():
    with gr.Tab("٥. 💬 تحدث مع الذكاء الاصطناعي") as tab:
        gr.HTML("<div class='step'><i>💬</i>تحدث مع الذكاء الاصطناعي في أي موضوع</div>"
                "<p class='hint'>اختر الذكاء اللي تبي تكلمه، وتقدر تبدّل بينهم في أي رسالة. إذا انتهى حد الذكاء يرد عليك التالي في ترتيب الأولوية (من الإعدادات). تحت المحادثة جدول المتبقي لكل ذكاء.</p>")
        with gr.Row():
            model = gr.Dropdown(choices(), value="auto", label="أكلم", scale=3)
            fb = gr.Checkbox(True, label="إذا انتهى حده كمّل بترتيب الأولوية", scale=2)
        chat = gr.Chatbot(height=460, rtl=True, show_label=False, render_markdown=True, sanitize_html=True)
        box = gr.Textbox(placeholder="اكتب رسالتك ثم Enter أو زر إرسال", show_label=False, lines=2, rtl=True)
        with gr.Row():
            b_send = gr.Button("إرسال", variant="primary", scale=3)
            b_clear = gr.Button("🧹 محادثة جديدة", scale=1)
        gr.Markdown("### المتبقي من حد كل ذكاء")
        left = gr.HTML(remaining_html())
    b_send.click(send, [chat, box, model, fb], [chat, box, left])
    box.submit(send, [chat, box, model, fb], [chat, box, left])
    b_clear.click(lambda: ([], ""), None, [chat, box])
    tab.select(lambda: (gr.update(choices=choices()), remaining_html()), None, [model, left])
    return {"model": model, "left": left}
