"""Pipeline completo: fuente -> libro procesado -> archivos."""
from __future__ import annotations

import json
from pathlib import Path

from . import extract, process, render


def build(source, output_dir="~/Almanackify", formats=("epub", "pdf"), chapter=None, limit_words=None,
          title=None, author=None, lang=None, box_every_words=220, chain=True, dedupe=False, save_json=True):
    book = extract.load(source, title=title, author=author, lang=lang)
    book = extract.select_chapters(book, chapter=chapter, limit_words=limit_words)
    opts = process.Opts(box_every_words=box_every_words, chain=chain, dedupe=dedupe, lang=book.get("lang", "en"))
    processed = process.process(book, opts)
    base = render.slug(processed["title"]) + ("-cap" + str(chapter) if chapter else "") + "-almanack"
    paths = render.render(processed, output_dir, formats, basename=base)
    if save_json:
        jp = Path(output_dir).expanduser() / f"{base}.json"
        jp.write_text(json.dumps(processed, ensure_ascii=False, indent=1), encoding="utf8")
        paths["json"] = str(jp)
    return {"files": paths, "stats": processed["stats"], "title": processed["title"], "lang": processed["lang"]}


def render_json(json_path, output_dir=None, formats=("epub", "pdf")):
    p = Path(json_path).expanduser()
    book = json.loads(p.read_text(encoding="utf8"))
    out = output_dir or str(p.parent)
    return {"files": render.render(book, out, formats, basename=p.stem)}
