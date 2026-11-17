"""Render: libro procesado (dict) -> EPUB (Kindle) y/o PDF, con el estilo "Almanack"."""
from __future__ import annotations

import html
import re
import uuid
from pathlib import Path

FONT_DIR = Path(__file__).parent / "fonts"
FONT_STACK = '"EB Garamond", "Adobe Garamond Pro", Garamond, "Times New Roman", "Liberation Serif", serif'

LABELS = {
    "es": {"toc": "Contenido", "by": "por"},
    "en": {"toc": "Contents", "by": "by"},
    "pt": {"toc": "Conteúdo", "by": "por"},
}


def inline(text: str) -> str:
    t = html.escape(text, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", t)
    return t.replace("∗", "*")


def block_html(b: dict, first: bool) -> str:
    t = b["type"]
    if t == "p":
        return f'<p class="{"first" if first else ""}">{inline(b["text"])}</p>'
    if t == "q":
        return f'<p class="question"><b>{inline(b["text"])}</b></p>'
    if t == "quote":
        return f'<p class="quote">{inline(b["text"])}</p>'
    if t == "h2":
        return f"<h2>{inline(b['text'])}</h2>"
    if t == "tweet":
        return f'<div class="tweet"><p>{inline(b["text"])}</p></div>'
    if t == "list":
        n = len(b["items"])
        return "".join(f'<p class="li{" lastli" if i == n - 1 else ""}">→ {inline(x)}</p>' for i, x in enumerate(b["items"]))
    if t == "chain":
        parts = []
        if b.get("title"):
            parts.append(f'<p class="chain-title">{inline(b["title"])}</p>')
        for i, item in enumerate(b["items"]):
            parts.append(f'<p class="chain-item">{inline(item)}</p>')
            if i < len(b["items"]) - 1:
                parts.append('<p class="arrow">↓</p>')
        return '<div class="chain">' + "".join(parts) + "</div>"
    return ""


def chapter_html(ch: dict) -> str:
    out = [f"<h1>{inline(ch['title'])}</h1>"]
    first = True
    for b in ch["blocks"]:
        out.append(block_html(b, first))
        first = b["type"] != "p"  # sin sangría tras caja/título/pregunta
    return "\n".join(out)


BASE_CSS = f"""
body {{ font-family: {FONT_STACK}; line-height: 1.38; text-align: justify; margin: 0; }}
h1 {{ font-weight: bold; text-transform: uppercase; text-align: left; font-size: 1.25em; line-height: 1.2;
     margin: 0 0 1.6em 0; page-break-before: always; break-before: page; }}
h2 {{ font-weight: bold; text-align: left; font-size: 1.05em; margin: 1.6em 0 .6em 0; page-break-after: avoid; }}
p {{ margin: 0; text-indent: 1.5em; orphans: 2; widows: 2; }}
p.first {{ text-indent: 0; }}
p.question {{ margin: 1.1em 0 .5em 0; text-indent: 0; text-align: left; }}
p.quote {{ margin: .8em 1.2em .8em 1.2em; text-indent: 0; font-style: italic; text-align: left; font-size: .95em; }}
p.li {{ text-indent: -1.4em; margin-left: 1.4em; text-align: left; }}
p.lastli {{ margin-bottom: .9em; }}
.tweet {{ background: #dddddd; margin: 1.7em 0; padding: .95em .85em; page-break-inside: avoid; break-inside: avoid; }}
.tweet p {{ text-indent: 0; text-align: left; margin: 0; }}
.chain {{ background: #dddddd; margin: 1.7em 0; padding: .9em .85em .9em .85em; page-break-inside: avoid; break-inside: avoid; }}
.chain p {{ text-indent: 0; text-align: left; margin: 0; }}
.chain p.chain-title {{ margin-bottom: 1em; }}
.chain p.arrow {{ text-align: center; margin: .55em 0; }}
.titlepage {{ text-align: center; margin-top: 30%; }}
.titlepage h1 {{ page-break-before: avoid; break-before: avoid; text-align: center; font-size: 1.6em; }}
.titlepage p {{ text-indent: 0; text-align: center; }}
"""


def _title_html(book: dict) -> str:
    lab = LABELS.get(book.get("lang", "en"), LABELS["en"])
    author = f'<p>{lab["by"]} {html.escape(book["author"])}</p>' if book.get("author") else ""
    return f'<div class="titlepage"><h1>{inline(book["title"])}</h1>{author}</div>'


# ----------------------------------------------------------------------------
def to_epub(book: dict, path: str, embed_font: bool = False) -> str:
    from ebooklib import epub

    lang = book.get("lang") or "en"
    eb = epub.EpubBook()
    eb.set_identifier(str(uuid.uuid4()))
    eb.set_title(book["title"])
    eb.set_language(lang)
    if book.get("author"):
        eb.add_author(book["author"])
    css = epub.EpubItem(uid="style", file_name="style/almanack.css", media_type="text/css", content=BASE_CSS)
    eb.add_item(css)

    items = []
    tp = epub.EpubHtml(title=book["title"], file_name="title.xhtml", lang=lang)
    tp.content = _title_html(book)
    tp.add_item(css)
    eb.add_item(tp)
    items.append(tp)
    for i, ch in enumerate(book["chapters"], 1):
        c = epub.EpubHtml(title=re.sub(r"\*", "", ch["title"]), file_name=f"ch{i:03d}.xhtml", lang=lang)
        c.content = chapter_html(ch)
        c.add_item(css)
        eb.add_item(c)
        items.append(c)
    eb.toc = tuple(items[1:])
    eb.add_item(epub.EpubNcx())
    eb.add_item(epub.EpubNav())
    eb.spine = ["nav"] + items
    epub.write_epub(path, eb, {})
    return path


def to_pdf(book: dict, path: str) -> str:
    from weasyprint import HTML

    lang = book.get("lang") or "en"
    title_up = html.escape(book["title"].upper())
    fonts = ""
    if (FONT_DIR / "EBGaramond.ttf").exists():
        fonts = (
            f'@font-face {{ font-family: "EB Garamond"; src: url("{(FONT_DIR / "EBGaramond.ttf").as_uri()}"); font-weight: 400 800; font-style: normal; }}\n'
            f'@font-face {{ font-family: "EB Garamond"; src: url("{(FONT_DIR / "EBGaramond-Italic.ttf").as_uri()}"); font-weight: 400 800; font-style: italic; }}\n'
        )
    page_css = f"""
    {fonts}
    @page {{ size: 5.5in 8.5in; margin: 0.8in 0.7in 0.8in 0.7in;
            @top-left {{ content: "{title_up}"; font-family: {FONT_STACK}; font-size: 7pt; letter-spacing: .06em; color: #444; }}
            @bottom-center {{ content: counter(page); font-family: {FONT_STACK}; font-size: 9pt; }} }}
    @page :first {{ @top-left {{ content: none; }} @bottom-center {{ content: none; }} }}
    body {{ font-size: 10.5pt; hyphens: auto; }}
    h1 {{ font-size: 13pt; }}
    .tweet, .chain {{ margin-left: 0; margin-right: 0; }}
    """
    body = _title_html(book) + "\n".join(chapter_html(ch) for ch in book["chapters"])
    doc = f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><title>{html.escape(book["title"])}</title><style>{BASE_CSS}{page_css}</style></head><body>{body}</body></html>'
    HTML(string=doc).write_pdf(path)
    return path


def slug(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s, flags=re.U).strip().lower()
    return re.sub(r"[\s_-]+", "-", s)[:60] or "libro"


def render(book: dict, output_dir: str, formats=("epub", "pdf"), basename: str | None = None) -> dict:
    out = Path(output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    base = basename or (slug(book["title"]) + "-almanack")
    paths = {}
    if "epub" in formats:
        paths["epub"] = to_epub(book, str(out / f"{base}.epub"))
    if "pdf" in formats:
        paths["pdf"] = to_pdf(book, str(out / f"{base}.pdf"))
    return paths
