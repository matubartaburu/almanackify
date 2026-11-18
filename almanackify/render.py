"""Render: libro procesado (dict) -> EPUB (Kindle) y/o PDF, con el estilo "Almanack"."""
from __future__ import annotations

import html
import re
import uuid
from pathlib import Path

FONT_DIR = Path(__file__).parent / "fonts"
STATIC_FONT_DIR = FONT_DIR / "static"  # versiones no variables (el Kindle falla con fuentes variables)
STATIC_FONTS = [("Regular", 400, "normal"), ("Bold", 700, "normal"), ("Italic", 400, "italic"), ("BoldItalic", 700, "italic")]
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
def _cover_quote(book: dict, max_chars: int = 120) -> str:
    """La cajita más 'tuiteable' y corta que entre en la portada (si ninguna es corta, se aceptan hasta 170)."""
    from .process import aphorism

    best, best_score = "", -1.0
    for ch in book["chapters"]:
        for b in ch["blocks"]:
            if b["type"] != "tweet" or len(b["text"]) > max_chars:
                continue
            score = aphorism(b["text"], book.get("lang") or "en")
            score = -0.5 if score is None else score
            if score > best_score:
                best, best_score = b["text"], score
    return best or (_cover_quote(book, 170) if max_chars < 170 else "")


def make_cover(book: dict) -> bytes:
    """Portada minimalista (JPEG 1600x2560): título, autor y una cajita con una idea del libro."""
    import pymupdf
    from weasyprint import HTML

    faces = "".join(
        f'@font-face {{ font-family: "EB Garamond"; src: url("{(STATIC_FONT_DIR / f"EBGaramond-{n}.ttf").as_uri()}"); '
        f"font-weight: {w}; font-style: {s}; }}\n" for n, w, s in STATIC_FONTS
        if (STATIC_FONT_DIR / f"EBGaramond-{n}.ttf").exists()
    )
    lab = LABELS.get(book.get("lang", "en"), LABELS["en"])
    author = f'<p class="by">{html.escape(book["author"])}</p>' if book.get("author") else ""
    quote = _cover_quote(book)
    box = f'<div class="box">{inline(quote)}</div>' if quote else ""
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><style>
    {faces}
    @page {{ size: 6.25in 10in; margin: 0; }}
    html, body {{ margin: 0; background: #fff; }}
    .cv {{ box-sizing: border-box; width: 6.25in; height: 10in; padding: .8in .7in; font-family: {FONT_STACK};
           color: #111; display: flex; flex-direction: column; }}
    h1 {{ font-size: 40pt; line-height: 1.05; text-transform: uppercase; font-weight: 700; margin: 0; }}
    .by {{ font-size: 16pt; margin: .35in 0 0 0; }}
    .sp {{ flex: 1; }}
    .box {{ background: #ddd; padding: .3in .28in; font-size: 17pt; line-height: 1.32; margin-bottom: .6in; }}
    .tag {{ font-size: 9pt; letter-spacing: .22em; text-transform: uppercase; }}
    </style></head><body><div class="cv"><h1>{inline(book["title"])}</h1>{author}<div class="sp"></div>{box}
    <div class="tag">Almanackify</div></div></body></html>"""
    pdf = HTML(string=doc).write_pdf()
    page = pymupdf.open(stream=pdf, filetype="pdf")[0]
    return page.get_pixmap(dpi=256).tobytes("jpeg")


def make_card(text: str, title: str = "", author: str = "") -> bytes:
    """Tarjeta para compartir una idea (PNG 16:9, formato de X): la cajita gris con su fuente."""
    import pymupdf
    from weasyprint import HTML

    faces = "".join(
        f'@font-face {{ font-family: "EB Garamond"; src: url("{(STATIC_FONT_DIR / f"EBGaramond-{n}.ttf").as_uri()}"); '
        f"font-weight: {w}; font-style: {s}; }}\n" for n, w, s in STATIC_FONTS
        if (STATIC_FONT_DIR / f"EBGaramond-{n}.ttf").exists()
    )
    size = 54 if len(text) <= 80 else 44 if len(text) <= 140 else 36
    src = ", ".join(x for x in (title, author) if x)
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><style>
    {faces}
    @page {{ size: 1200px 675px; margin: 0; }}
    html, body {{ margin: 0; background: #fff; }}
    .c {{ box-sizing: border-box; width: 1200px; height: 675px; padding: 70px 80px; font-family: {FONT_STACK}; color: #111;
          display: flex; flex-direction: column; justify-content: space-between; }}
    .box {{ background: #ddd; padding: 56px 60px; font-size: {size}px; line-height: 1.28; }}
    .src {{ font-size: 24px; margin-top: 26px; }}
    .tag {{ font-size: 15px; letter-spacing: .24em; text-transform: uppercase; }}
    </style></head><body><div class="c"><div class="tag">Almanackify</div>
    <div><div class="box">{inline(text)}</div><div class="src">{html.escape(src)}</div></div><div></div></div></body></html>"""
    page = pymupdf.open(stream=HTML(string=doc).write_pdf(), filetype="pdf")[0]
    return page.get_pixmap(dpi=144).tobytes("png")


def to_epub(book: dict, path: str, embed_font: bool = True) -> str:
    from ebooklib import epub

    lang = book.get("lang") or "en"
    eb = epub.EpubBook()
    eb.set_identifier(str(uuid.uuid4()))
    eb.set_title(book["title"])
    eb.set_language(lang)
    if book.get("author"):
        eb.add_author(book["author"])
    fonts_css = ""
    if embed_font and all((STATIC_FONT_DIR / f"EBGaramond-{n}.ttf").exists() for n, _, _ in STATIC_FONTS):
        for name, _, _ in STATIC_FONTS:
            eb.add_item(epub.EpubItem(uid=f"font-{name.lower()}", file_name=f"fonts/EBGaramond-{name}.ttf",
                                      media_type="font/ttf", content=(STATIC_FONT_DIR / f"EBGaramond-{name}.ttf").read_bytes()))
        fonts_css = "".join(
            f'@font-face {{ font-family: "EB Garamond"; src: url("../fonts/EBGaramond-{n}.ttf"); '
            f"font-weight: {w}; font-style: {s}; }}\n" for n, w, s in STATIC_FONTS
        )
    css = epub.EpubItem(uid="style", file_name="style/almanack.css", media_type="text/css", content=fonts_css + BASE_CSS)
    eb.add_item(css)
    eb.set_cover("images/cover.jpg", make_cover(book), create_page=False)

    items = []
    tp = epub.EpubHtml(uid="titlepage", title=book["title"], file_name="title.xhtml", lang=lang)
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
    eb.spine = items  # el nav.xhtml queda en el manifiesto (TOC del Kindle) pero fuera del orden de lectura
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
