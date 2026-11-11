import os
from pathlib import Path
from core import builder

SLOTS = int(os.getenv("SUB_SLOTS", "15"))          # paragraphs shown at once on one page
HL_DEFAULT = "#fff2a8"
DROP_JS = (Path(__file__).resolve().parent.parent / "core" / "dropzone.js").read_text(encoding="utf-8")
PASTE_JS = (Path(__file__).resolve().parent.parent / "core" / "paste.js").read_text(encoding="utf-8")
GARBLED_MSG = ("⚠ نص هذه الفقرة غير مقروء (ترميز خط الملف الأصلي). اقرأه من «صورة الصفحة الأصلية» تحت، "
               "أو اضغط «👁 اقرأ من الصورة» ليقرأه الذكاء الاصطناعي (تُرسل صورة الفقرة للخدمة).")
ALIGN_CHOICES = [("افتراضي (مثل الأصل)", ""), ("يمين", "right"), ("وسط", "center"), ("يسار", "left"), ("ضبط الجانبين", "justify")]
DELTA = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}
BG_PRESETS = {
    "بدون تغيير (الخلفية الأصلية)": ("none", "#ffffff", "#cccccc", "vertical"),
    "أبيض": ("solid", "#ffffff", "#ffffff", "vertical"), "كريمي": ("solid", "#fdf6e3", "#fdf6e3", "vertical"),
    "ورقي قديم": ("solid", "#f4ecd8", "#f4ecd8", "vertical"), "أصفر فاتح": ("solid", "#fff9c4", "#fff9c4", "vertical"),
    "وردي فاتح": ("solid", "#fde2e4", "#fde2e4", "vertical"), "أخضر فاتح": ("solid", "#e3f6e8", "#e3f6e8", "vertical"),
    "أزرق فاتح": ("solid", "#e1effa", "#e1effa", "vertical"), "رمادي فاتح": ("solid", "#eeeeee", "#eeeeee", "vertical"),
    "رمادي داكن": ("solid", "#2b2b2b", "#2b2b2b", "vertical"), "أسود": ("solid", "#000000", "#000000", "vertical"),
    "كحلي": ("solid", "#14213d", "#14213d", "vertical"), "بني": ("solid", "#3e2f23", "#3e2f23", "vertical"),
    "تدرج: غروب": ("gradient", "#ffb88c", "#de6262", "vertical"), "تدرج: محيط": ("gradient", "#2193b0", "#6dd5ed", "vertical"),
    "تدرج: ليلي": ("gradient", "#0f2027", "#2c5364", "vertical"), "تدرج: نعناع": ("gradient", "#d4fc79", "#96e6a1", "vertical"),
    "تدرج: وردي هادئ": ("gradient", "#fbc2eb", "#a6c1ee", "diagonal"), "تدرج: ذهبي": ("gradient", "#f6d365", "#fda085", "diagonal"),
    "تدرج: رمادي": ("gradient", "#bdc3c7", "#2c3e50", "vertical"), "تدرج: كريمي دافئ": ("gradient", "#fdfbfb", "#ebedee", "diagonal"),
}


def fonts():
    return [("افتراضي", "")] + builder.font_labels()
