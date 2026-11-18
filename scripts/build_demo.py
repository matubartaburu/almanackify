"""Genera los libros de muestra de la portada de la web (solo dominio público) en almanackify/web/demo/.

Uso: .venv/bin/python scripts/build_demo.py     (necesita internet; usa Standard Ebooks)
Cada libro sale de la conversión real de Almanackify: la portada y las cajitas son las que produce el programa.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from almanackify import core, extract, render  # noqa: E402

DEMO = ROOT / "almanackify" / "web" / "demo"
SE = "https://standardebooks.org/ebooks"
BOOKS = [
    ("self-reliance", "Self-Reliance", "Ralph Waldo Emerson", f"{SE}/ralph-waldo-emerson/essays/text/self-reliance", None),
    ("shortness-of-life", "On the Shortness of Life", "Seneca", f"{SE}/seneca/dialogues/aubrey-stewart/text/on-the-shortness-of-life", None),
    ("walden", "Walden: Economy", "Henry David Thoreau", f"{SE}/henry-david-thoreau/walden/text/economy", 9000),
    ("meditations-4", "Meditations: Book 4", "Marcus Aurelius", f"{SE}/marcus-aurelius/meditations/george-long/text/book-4", None),
]

if __name__ == "__main__":
    DEMO.mkdir(parents=True, exist_ok=True)
    out = []
    for slug, title, author, url, limit in BOOKS:
        book = extract.load(url, title=title, author=author)
        with tempfile.TemporaryDirectory() as t:
            res = core.build_book(book, t, ("epub",), limit_words=limit)
            processed = json.loads(Path(res["files"]["json"]).read_text(encoding="utf8"))
        (DEMO / f"{slug}.jpg").write_bytes(render.make_cover(processed, dpi=64))
        boxes = [b["text"] for c in processed["chapters"] for b in c["blocks"] if b["type"] == "tweet"]
        out.append({"slug": slug, "title": title, "author": author, "cover": f"demo/{slug}.jpg", "boxes": boxes[:2],
                    "stats": processed["stats"], "source": url})
        print(f"{title}: {processed['stats']['boxes']} boxes")
    (DEMO / "books.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf8")
