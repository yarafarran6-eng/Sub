"""The offline reader (no AI): reads a rendered English paragraph exactly; skipped when no engine is installed."""
import sys, os, io, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import ocr_local
if not ocr_local.available():
    print("OCR LOCAL SKIPPED (no engine installed)"); raise SystemExit
from PIL import Image, ImageDraw, ImageFont
im = Image.new("RGB", (900, 160), "white"); dr = ImageDraw.Draw(im); f = ImageFont.truetype("DejaVuSans.ttf", 30)
dr.text((20, 20), "Tanya walked slowly down the old road,", font=f, fill="black"); dr.text((20, 70), "thinking about what her brother had said.", font=f, fill="black")
b = io.BytesIO(); im.save(b, "PNG")
t = ocr_local.read_image(b.getvalue())
assert t == "Tanya walked slowly down the old road, thinking about what her brother had said.", t
assert ocr_local._join(["こんにちは", "世界"]) == "こんにちは世界"
print("OCR LOCAL OK", ocr_local.available())
