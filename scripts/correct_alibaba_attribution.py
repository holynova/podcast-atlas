"""Correct the source-show typo on the imported Alibaba founding deck cover."""
import io,pathlib
from pypdf import PdfReader,PdfWriter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
ROOT=pathlib.Path(__file__).resolve().parents[1]
file=ROOT/'assets/slides/68f505f8456ffec65e871c27.pdf'
original=ROOT/'work/68f505f8456ffec65e871c27-uncompressed.pdf'
reader=PdfReader(original);writer=PdfWriter()
pdfmetrics.registerFont(TTFont('Chinese','/System/Library/Fonts/STHeiti Medium.ttc',subfontIndex=0))
for i,page in enumerate(reader.pages):
 if i==0:
  width,height=float(page.mediabox.width),float(page.mediabox.height);sx,sy=width/1280,height/714
  buf=io.BytesIO();c=canvas.Canvas(buf,pagesize=(width,height));c.setFillColor('#f5e9b4');c.rect(25*sx,height-63*sy,550*sx,31*sy,fill=1,stroke=0);c.setFont('Chinese',22*sx);c.setFillColor('#151515');c.drawString(30*sx,height-55*sy,'中国互联网故事10｜原播客：半拿铁 No.172');c.save();buf.seek(0);page.merge_page(PdfReader(buf).pages[0])
 writer.add_page(page)
with file.open('wb') as f:writer.write(f)
print('Corrected show attribution; native original preserved in work/.')
