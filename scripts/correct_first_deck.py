"""Add a vector editorial correction layer; preserve NotebookLM's comic pages.

Corrections are source attribution, verified names and overbroad claims.
The original downloaded PDF is retained in ignored work/ for comparison.
"""
import io, pathlib, shutil
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = pathlib.Path(__file__).resolve().parents[1]
FILE = ROOT / 'assets/slides/683e851c38dcc57c644718eb.pdf'
ORIGINAL = ROOT / 'work/683e851c38dcc57c644718eb-original.pdf'
if not ORIGINAL.exists(): shutil.copyfile(FILE, ORIGINAL)
reader = PdfReader(ORIGINAL); writer = PdfWriter()
pdfmetrics.registerFont(TTFont('Chinese', '/System/Library/Fonts/STHeiti Medium.ttc', subfontIndex=0))
for i, page in enumerate(reader.pages):
    width, height = float(page.mediabox.width), float(page.mediabox.height)
    sx, sy = width / 1280, height / 714
    buffer = io.BytesIO(); c = canvas.Canvas(buffer, pagesize=(width, height))
    def box(x, y, w, h, lines, size=23, color='#f5f0df', ink='#252a27'):
        c.setFillColor(color); c.rect(x*sx, height-(y+h)*sy, w*sx, h*sy, stroke=0, fill=1)
        c.setFillColor(ink); c.setFont('Chinese', size*sx)
        for n,line in enumerate(lines): c.drawString((x+5)*sx, height-(y+size+4+n*(size+6))*sy, line)
    if i == 0:
        box(47, 197, 627, 63, ['从中文打字机起家，走到产品换代与跨行业投资的挑战。', '一集读懂四通的创业、技术与经营选择。'], 22, '#f4e9b6')
        box(866, 638, 373, 34, ['根据《半拿铁》No.153单集整理'], 22, '#f4e9b6')
    if i == len(reader.pages)-1:
        box(68, 351, 92, 31, ['陈春先'], 23)
        box(593, 183, 88, 35, ['万润南'], 23)
        box(540, 371, 96, 32, ['王缉志'], 23)
        box(80, 592, 126, 33, ['段永基'], 23)
        box(278, 658, 120, 33, ['王志东'], 23)
        box(334, 94, 218, 36, ['1986：MS-2400问世'], 21)
        box(329, 413, 199, 32, ['2001：王志东离任'], 21)
        box(629, 443, 97, 74, ['后续：', '继续转型'], 23, '#d2d0bc')
        box(756, 598, 470, 72, ['四通曾是中关村的重要科技企业。', '21人是节目制作时查询的单一公司社保数据。'], 21, '#ffffff')
    box(24, 698, 1220, 15, ['来源：《半拿铁》No.153。AI漫画演绎；姓名及数字校对说明见对应网页。'], 10, '#ffffff')
    c.save(); buffer.seek(0); page.merge_page(PdfReader(buffer).pages[0]); writer.add_page(page)
with FILE.open('wb') as f: writer.write(f)
print('Corrected attribution, names and scope of closing statistics; original preserved in work/.')
