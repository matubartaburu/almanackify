"""Genera los libros de muestra de la portada de la web (solo dominio público) en almanackify/web/demo/.

Uso: .venv/bin/python scripts/build_demo.py     (necesita internet; usa Standard Ebooks)
Cada libro sale de la conversión real de Almanackify: la portada y las cajitas son las que produce el programa.
"""
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from almanackify import core, extract, render  # noqa: E402

DEMO = ROOT / "almanackify" / "web" / "demo"
SE = "https://standardebooks.org/ebooks"
IA = "https://archive.org/download/scientific-advertising/Scientific%20Advertising.epub"
# (slug, título, autor, fuente descargable, límite de palabras, página de la fuente, licencia)
BOOKS = [
    ("scientific-advertising", "Scientific Advertising", "Claude C. Hopkins", IA, None,
     "https://archive.org/details/scientific-advertising", "public domain (US, published 1923)"),
    ("shortness-of-life", "On the Shortness of Life", "Seneca", f"{SE}/seneca/dialogues/aubrey-stewart/text/on-the-shortness-of-life", None,
     f"{SE}/seneca/dialogues/aubrey-stewart", "public domain"),
    ("walden", "Walden: Economy", "Henry David Thoreau", f"{SE}/henry-david-thoreau/walden/text/economy", 9000,
     f"{SE}/henry-david-thoreau/walden", "public domain"),
    ("meditations-4", "Meditations: Book 4", "Marcus Aurelius", f"{SE}/marcus-aurelius/meditations/george-long/text/book-4", None,
     f"{SE}/marcus-aurelius/meditations/george-long", "public domain"),
]


def load(url, title, author):
    """Un EPUB remoto se baja a una carpeta temporal propia (archivo ajeno: solo se lee como datos); lo demás va por extract.load."""
    if url.endswith(".epub"):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "book.epub"
            f.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=90).read())
            return extract.load(str(f), title=title, author=author)
    return extract.load(url, title=title, author=author)


if __name__ == "__main__":
    DEMO.mkdir(parents=True, exist_ok=True)
    out = []
    for slug, title, author, url, limit, page, lic in BOOKS:
        book = load(url, title, author)
        with tempfile.TemporaryDirectory() as t:
            res = core.build_book(book, t, ("epub",), limit_words=limit)
            processed = json.loads(Path(res["files"]["json"]).read_text(encoding="utf8"))
        (DEMO / f"{slug}.jpg").write_bytes(render.make_cover(processed, dpi=64))
        boxes = [b["text"] for c in processed["chapters"] for b in c["blocks"] if b["type"] == "tweet"]
        out.append({"slug": slug, "title": title, "author": author, "cover": f"demo/{slug}.jpg", "boxes": boxes[:2],
                    "stats": processed["stats"], "source": page, "license": lic})
        print(f"{title}: {processed['stats']['boxes']} boxes")
    (DEMO / "books.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf8")
