"""«النسخة المخففة»: نسخة تُعطى لشخص ثاني. نفس الكود ونفس التحديثات، لكن تبويب الترجمة الآلية مخفي
وأوامر الذكاء الاصطناعي في المراجعة غير ظاهرة. تُفعَّل بملف data/edition.txt فيه الكلمة lite
(مجلد data ما يلمسه التحديث، فتبقى النسخة مخففة بعد كل تحديث)."""
import os

from .config import DATA


def is_lite():
    if os.getenv("SUB_EDITION", "").strip().lower() == "lite":
        return True
    try:
        return (DATA / "edition.txt").read_text(encoding="utf-8-sig").strip().lower() == "lite"
    except OSError:
        return False
