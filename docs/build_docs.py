"""Build self-contained report.html and slides.html: every screenshot is embedded as base64, so the files
work when double-clicked or emailed. Usage: python docs/build_docs.py"""
import base64, re
from pathlib import Path
D = Path(__file__).resolve().parent
SHOTS = D / "screenshots"

def embed(html: str) -> str:
    def rep(m):
        f = SHOTS / m.group(1)
        mime = "image/png" if f.suffix == ".png" else "image/jpeg"
        return f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode()
    return re.sub(r"IMG:([\w.\-]+)", rep, html)

for src, out in (("report_src.html", "report.html"), ("slides_src.html", "slides.html")):
    p = D / src
    if p.exists():
        html = embed(p.read_text(encoding="utf-8"))
        assert "IMG:" not in html
        (D / out).write_text(html, encoding="utf-8")
        print(out, f"{len(html)/1e6:.1f} MB")
