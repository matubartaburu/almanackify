"""Servidor MCP de Almanackify.  Uso:  python -m almanackify.mcp_server   (stdio)

Registrar en Claude Code:
    claude mcp add almanackify -- python -m almanackify.mcp_server
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP

from . import core, extract

mcp = FastMCP("almanackify")
DEFAULT_OUT = "~/Documents/Almanackify"


@mcp.tool()
def almanackify(
    source: str,
    formats: list[str] | None = None,
    output_dir: str = DEFAULT_OUT,
    chapter: str | None = None,
    limit_words: int | None = None,
    box_every_words: int = 220,
    chain: bool = True,
    dedupe: bool = False,
    title: str | None = None,
    author: str | None = None,
    language: str | None = None,
) -> dict:
    """Convierte un libro/artículo/video al formato 'Almanack': párrafos cortos, preguntas en negrita,
    cajas grises tipo tweet y una cadena ↓ de resumen por capítulo. Devuelve las rutas de los archivos.

    source: ruta a .epub/.pdf/.txt/.srt/.vtt, URL de artículo, URL de YouTube (usa la transcripción),
            o directamente el texto/transcripción pegado.
    formats: ["epub","pdf"] (default ambos). El EPUB sirve para Send to Kindle.
    chapter: opcional, número o parte del título para procesar solo un capítulo.
    limit_words: opcional, solo las primeras N palabras.
    """
    return core.build(source, output_dir, tuple(formats or ["epub", "pdf"]), chapter, limit_words, title, author,
                      language, box_every_words, chain, dedupe)


@mcp.tool()
def almanackify_extract(source: str, output_dir: str = DEFAULT_OUT, chapter: str | None = None) -> dict:
    """Solo extrae la estructura (capítulos y párrafos) a un JSON, sin cajas. Sirve para que Claude escriba
    él mismo las cajas/resúmenes (bloques {"type":"tweet","text":...}) y después llame a almanackify_render."""
    book = extract.select_chapters(extract.load(source), chapter=chapter)
    blocks_book = {**book, "chapters": [{"title": c["title"], "blocks": [
        ({"type": "q", "text": p[2:-2]} if p.startswith("**") and p.endswith("**") else
         {"type": "quote", "text": p[2:]} if p.startswith("> ") else
         {"type": "h2", "text": p[3:]} if p.startswith("## ") else
         {"type": "p", "text": p}) for p in c["paragraphs"]]} for c in book["chapters"]]}
    out = Path(output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{core.render.slug(book['title'])}.book.json"
    path.write_text(json.dumps(blocks_book, ensure_ascii=False, indent=1), encoding="utf8")
    return {"json": str(path), "title": book["title"], "lang": book["lang"],
            "chapters": [{"title": c["title"], "words": sum(len(p.split()) for p in c["paragraphs"])} for c in book["chapters"]]}


@mcp.tool()
def almanackify_render(json_path: str, formats: list[str] | None = None, output_dir: str | None = None) -> dict:
    """Arma el EPUB/PDF a partir de un JSON ya procesado (por almanackify o editado a mano / por Claude)."""
    return core.render_json(json_path, output_dir, tuple(formats or ["epub", "pdf"]))


if __name__ == "__main__":
    mcp.run()
