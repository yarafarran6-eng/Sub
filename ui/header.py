"""The top banner and the warning/ready strip."""
from core import auth, jobs
from core.config import get_settings
from core.keystore import load_keys

def hero_html():
    ks = [k for k in load_keys() if k.get("enabled")]
    s = get_settings()
    js = jobs.list_jobs()
    run = sum(1 for m in js if m.get("status") == "running")
    return ("<div class='hero'><div><h1>مترجم الروايات</h1>"
            "<p>ارفع الملف، وخلّ المفاتيح تترجم بالتوازي، وراجع الناتج قبل التصدير.</p></div>"
            f"<div class='chips'><span class='hchip'>🔑 مفاتيح مفعّلة: {len(ks)}</span>"
            f"<span class='hchip'>📚 ملفات: {len(js)}{f' (يعمل {run})' if run else ''}</span>"
            f"<span class='hchip'>💰 المصروف: {s['spent_usd']:.3f}$ من {s['budget_usd']}$</span></div></div>")


def banner_html():
    if auth.must_change():
        return "<div class='warnbox'>⚠ غيّر كلمة السر الأولية (2222) من تبويب «٦. الإعدادات» قبل أي شي.</div>"
    if not [k for k in load_keys() if k.get("enabled")]:
        return "<div class='warnbox'>⚠ ما أضفت أي مفتاح. افتح تبويب «١. المفاتيح» وأضف مفتاحاً واحداً على الأقل.</div>"
    return "<div class='okbox'>✓ جاهز. ارفع ملفاً من تبويب «٢. الترجمة».</div>"
