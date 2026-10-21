"""Generate the Stage32 Astra calibration target: 9x6 inner corners (10x7 squares), 35.0 mm squares, A3 landscape, vector PDF.
Printed at 100% the pattern is exactly 350.0 x 245.0 mm. Two 100.0 mm check bars let the owner verify the print scale."""
import sys
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

COLS, ROWS, SQ = 10, 7, 35.0           # squares; inner corners = 9 x 6
out = sys.argv[1] if len(sys.argv) > 1 else 'atlas_astra_checkerboard_9x6_35mm_A3.pdf'
W, H = landscape(A3)                   # 420 x 297 mm
pw, ph = COLS * SQ * mm, ROWS * SQ * mm
x0, y0 = (W - pw) / 2, (H - ph) / 2
c = canvas.Canvas(out, pagesize=(W, H))
c.setTitle('ATLAS Astra calibration target 9x6 inner corners, 35 mm squares'); c.setAuthor('ATLAS Stage32')
c.setFillColorRGB(0, 0, 0); c.setStrokeColorRGB(0, 0, 0)
for r in range(ROWS):
    for q in range(COLS):
        if (r + q) % 2 == 0:
            c.rect(x0 + q * SQ * mm, y0 + (ROWS - 1 - r) * SQ * mm, SQ * mm, SQ * mm, stroke=0, fill=1)
# scale check bars in the corners, well away from the pattern's white border
c.setLineWidth(0.6)
for bx, by in ((8 * mm, 8 * mm), (W - 108 * mm, H - 10 * mm)):
    c.line(bx, by, bx + 100 * mm, by); c.line(bx, by - 2 * mm, bx, by + 2 * mm); c.line(bx + 100 * mm, by - 2 * mm, bx + 100 * mm, by + 2 * mm)
c.setFont('Helvetica', 7); c.setFillColorRGB(0.35, 0.35, 0.35)
c.drawString(8 * mm, 11 * mm, '100.0 mm check bar - measure it; reprint if not 100.0 +/- 0.5 mm')
c.drawRightString(W - 8 * mm, H - 7 * mm, 'ATLAS Astra target: 9 x 6 inner corners, 35.0 mm squares. A3 at 100% (Actual size), matte.')
c.showPage(); c.save()
print(out, 'pattern %.1f x %.1f mm on %.0f x %.0f mm page; margins %.1f / %.1f mm' % (COLS * SQ, ROWS * SQ, W / mm, H / mm, x0 / mm, y0 / mm))
