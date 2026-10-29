import sys
from reportlab.lib.pagesizes import A5
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image
out = sys.argv[1]
c = canvas.Canvas(out, pagesize=A5)
W, H = A5
img = Image.new("RGB", (300, 160), (200, 120, 60)); img.save("/tmp/sample_img.png")
for p in range(1, 4):
    c.setFont("Helvetica-Bold", 20); c.drawCentredString(W/2, H-60, f"Chapter {p}")
    c.setFont("Helvetica", 10.5)
    y = H - 100
    for para in range(3):
        words = ("Alice walked slowly down the old road, thinking about what her brother had said the night before. " * 3).split()
        line = ""
        for w in words:
            if c.stringWidth(line + " " + w, "Helvetica", 10.5) > W - 100:
                c.drawString(50, y, line.strip()); y -= 14; line = w
            else:
                line += " " + w
        c.drawString(50, y, line.strip()); y -= 24
    if p == 2:
        c.drawImage(ImageReader("/tmp/sample_img.png"), 60, 40, width=220, height=117)
    c.showPage()
c.save()
