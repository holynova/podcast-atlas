"""Render verified deck pages and package them as web-sized JPEGs.

Use Poppler rather than pypdf image extraction: pypdf can misdecode image
predictors in these NotebookLM PDFs. The original stays in ignored work/.
"""
import io, pathlib, shutil, subprocess, sys, tempfile
from pypdf import PdfReader
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

source = pathlib.Path(sys.argv[1]); root = pathlib.Path(__file__).resolve().parents[1]
original = root / 'work' / (source.stem + '-uncompressed.pdf')
if not original.exists(): shutil.copyfile(source, original)
reader = PdfReader(original)
target = source.with_suffix('.optimized.pdf')
pdf = canvas.Canvas(str(target), pagesize=(1376,768), pageCompression=1)
pdf.setTitle(source.stem + ' · 中文漫画幻灯片')
with tempfile.TemporaryDirectory(dir=root / 'work') as directory:
    for i, page in enumerate(reader.pages):
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        prefix = pathlib.Path(directory) / 'page'
        subprocess.run(['/Users/sym/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/pdftoppm','-f',str(i+1),'-l',str(i+1),'-singlefile','-scale-to',str(round(max(width,height))),'-png',str(original),str(prefix)],check=True)
        with Image.open(prefix.with_suffix('.png')) as image:
            buffer = io.BytesIO(); image.convert('RGB').save(buffer,'JPEG',quality=95,subsampling=0);buffer.seek(0)
            pdf.setPageSize((width,height));pdf.drawImage(ImageReader(buffer),0,0,width=width,height=height);pdf.showPage()
pdf.save()
if len(PdfReader(target).pages) != len(reader.pages): raise RuntimeError('Page count changed')
if target.stat().st_size < original.stat().st_size: target.replace(source)
else: shutil.copyfile(original,source);target.unlink()
print(f'Web PDF: {source.name}: {original.stat().st_size/1e6:.1f} → {source.stat().st_size/1e6:.1f} MB')
