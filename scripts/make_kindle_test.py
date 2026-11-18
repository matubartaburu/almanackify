"""Genera un EPUB de prueba con todos los bloques, para revisarlo en un Kindle real.

Uso: .venv/bin/python scripts/make_kindle_test.py   ->  examples/almanackify-kindle-test.epub
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from almanackify import render  # noqa: E402

OUT = ROOT / "examples"

BOOK = {
    "title": "Almanackify · Kindle test",
    "author": "Almanackify",
    "lang": "en",
    "chapters": [
        {"title": "What you should see", "blocks": [
            {"type": "p", "text": "This short book checks that everything survives the trip to your Kindle. Go through the list below and note anything that looks wrong."},
            {"type": "list", "items": [
                "The cover shows in your Library: a white page, the title, and a gray box with a sentence.",
                "Letters look like Garamond (a classic serif). If they look like your usual Kindle font, turn on “Publisher Font” in the Aa menu.",
                "Gray boxes appear as boxes, with text inside, and never split across two pages.",
                "Arrows ↓ and → show as arrows, not as empty squares.",
                "Accented letters work: canción, niño, café, über, façade.",
            ]},
            {"type": "q", "text": "Does this question appear in bold, on its own line?"},
            {"type": "p", "text": "Short paragraphs keep the pace light. Long paragraphs are kept justified so the page looks like a printed book, with the first line of each paragraph indented and the rest flush."},
            {"type": "tweet", "text": "If you can read this inside a gray box, the idea boxes work on your device."},
            {"type": "p", "text": "Here is a paragraph after a box. It should not be indented, because it follows a box. The next one is indented again, as in a book."},
            {"type": "p", "text": "Second paragraph: indented. Keep reading; the chain below shows the arrows between steps, one idea per step."},
            {"type": "chain", "title": "Quick check", "items": ["Cover in the Library", "Garamond letters", "Gray boxes", "Arrows ↓ and →", "Table of contents works"]},
            {"type": "quote", "text": "A quote appears indented and in italics."},
            {"type": "h2", "text": "A section heading"},
            {"type": "p", "text": "Open the table of contents from the Kindle menu: you should see this chapter and the next one."},
        ]},
        {"title": "Second chapter", "blocks": [
            {"type": "p", "text": "Every chapter starts on a new page, with its title in bold capitals. If you are reading this on its own page, chapter breaks work."},
            {"type": "tweet", "text": "Send this file to your Kindle with Send to Kindle, then tell us what looked wrong."},
        ]},
    ],
}

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    print(json.dumps(render.render(BOOK, str(OUT), ("epub",), basename="almanackify-kindle-test"), indent=1))
