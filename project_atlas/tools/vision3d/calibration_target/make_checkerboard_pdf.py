"""Generate the Stage32 Astra calibration target: 9x6 inner corners (10x7 squares), vector PDF, printed at 100 % (Actual size).

  python3 make_checkerboard_pdf.py                          # A3 landscape, 35.0 mm squares -> 350.0 x 245.0 mm (original target)
  python3 make_checkerboard_pdf.py --page A4 --square-mm 25 # A4 landscape, 25.0 mm squares -> 250.0 x 175.0 mm (owner's 21 Oct choice)

The square size printed here is the DESIGN value. Calibration never uses it: the capture tools require --square-mm, which must be
the owner's MEASURED value from the physical print (9 squares across, divided by 9). Two 100.0 mm check bars verify print scale."""
import argparse
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

COLS, ROWS = 10, 7                     # squares; inner corners = 9 x 6
PAGES = {'A3': landscape(A3), 'A4': landscape(A4)}


def build(out, page='A3', sq=35.0):
    W, H = PAGES[page]
    pw, ph = COLS * sq * mm, ROWS * sq * mm
    x0, y0 = (W - pw) / 2, (H - ph) / 2
    if x0 < 15 * mm or y0 < 15 * mm:
        raise ValueError('pattern leaves less than 15 mm white border on %s; use smaller squares' % page)
    c = canvas.Canvas(out, pagesize=(W, H))
    c.setTitle('ATLAS Astra calibration target 9x6 inner corners, %.1f mm squares, %s' % (sq, page)); c.setAuthor('ATLAS Stage32')
    c.setFillColorRGB(0, 0, 0); c.setStrokeColorRGB(0, 0, 0)
    for r in range(ROWS):
        for q in range(COLS):
            if (r + q) % 2 == 0:
                c.rect(x0 + q * sq * mm, y0 + (ROWS - 1 - r) * sq * mm, sq * mm, sq * mm, stroke=0, fill=1)
    # scale check bars in two opposite corners, inside the printable area and clear of the pattern's white border
    c.setLineWidth(0.6)
    for bx, by in ((8 * mm, 7 * mm), (W - 108 * mm, H - 7 * mm)):
        c.line(bx, by, bx + 100 * mm, by); c.line(bx, by - 2 * mm, bx, by + 2 * mm); c.line(bx + 100 * mm, by - 2 * mm, bx + 100 * mm, by + 2 * mm)
    c.setFont('Helvetica', 6); c.setFillColorRGB(0.35, 0.35, 0.35)
    c.drawString(112 * mm, 6 * mm, '<- 100.0 mm check bar: measure it; reprint at Actual size if not 100.0 +/- 0.5 mm')
    c.drawRightString(W - 112 * mm, H - 8 * mm, 'ATLAS Astra target: 9 x 6 inner corners, %.1f mm squares (design). %s landscape, 100%%, matte. ->' % (sq, page))
    c.showPage(); c.save()
    return {'pattern_mm': (COLS * sq, ROWS * sq), 'page_mm': (round(W / mm, 1), round(H / mm, 1)), 'margins_mm': (round(x0 / mm, 2), round(y0 / mm, 2))}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('out', nargs='?'); ap.add_argument('--page', choices=sorted(PAGES), default='A3')
    ap.add_argument('--square-mm', type=float, default=35.0); a = ap.parse_args()
    out = a.out or 'atlas_astra_checkerboard_9x6_%gmm_%s.pdf' % (a.square_mm, a.page)
    print(out, build(out, a.page, a.square_mm))
