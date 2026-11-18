"""Extractores: convierten cualquier fuente en un "libro" estructurado.

Estructura devuelta (dict, serializable a JSON):

    {"title": str, "author": str, "lang": "es"|"en"|...,
     "chapters": [{"title": str, "paragraphs": [str, ...]}]}

Convenciones dentro de cada párrafo (strings):
    "**x**"   negrita          "*x*"  cursiva
    "• texto" item de lista    "## t" subtítulo      "> t" cita / epígrafe
"""
from __future__ import annotations

import html
import re
from collections import Counter
from pathlib import Path

SKIP_TITLE_RE = re.compile(
    r"^(contents|table of contents|índice|indice|copyright|title page|also by|about the author|"
    r"acknowledg|notes|index|resources|dedication|praise|cover|half title|colophon|"
    r"sobre el autor|agradecimientos|notas|bibliograf)",
    re.I,
)
BULLET_RE = re.compile(r"^[•·▪‣◦→\-–—]\s+")
JUNK_RE = re.compile(r"oceanofpdf|z-?library|libgen|pdfdrive|ebookee", re.I)
TERMINATORS = ".!?…:;\"”»)’'"


# ----------------------------------------------------------------------------
# utilidades
# ----------------------------------------------------------------------------
def _noast(text: str) -> str:
    return text.replace("*", "∗")


def _clean(text: str) -> str:
    text = text.replace("­", "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def strip_code_fences(text: str) -> str:
    """Quita los ``` que deja el extractor en epígrafes y versos (se conserva el texto)."""
    return text.replace("```", "")


_FOOTNOTE = re.compile(r"\s*\\?\[\s*\d{1,3}\s*\\?\]")


def strip_footnote_marks(text: str) -> str:
    """Quita marcas de nota al pie como [3], [ 3 ] o \\[ 3 \\] que dejan las páginas web."""
    return _FOOTNOTE.sub("", text)


def detect_lang(text: str) -> str:
    sample = text[:60000].lower()
    words = re.findall(r"[^\W\d_]+", sample)
    if not words:
        return "en"
    es = {"el", "la", "los", "las", "de", "que", "y", "en", "un", "una", "es", "por", "con", "para", "no", "se", "su", "lo", "del", "al", "más", "como", "pero"}
    en = {"the", "of", "and", "to", "in", "a", "is", "that", "it", "for", "with", "as", "on", "was", "are", "be", "this", "not", "but", "you", "have"}
    pt = {"o", "os", "as", "da", "do", "em", "um", "uma", "não", "para", "com", "que", "se", "mais", "mas", "você"}
    c = Counter(words)
    scores = {"es": sum(c[w] for w in es), "en": sum(c[w] for w in en), "pt": sum(c[w] for w in pt if w not in es)}
    return max(scores, key=scores.get)


def _new_chapter(title: str) -> dict:
    return {"title": title, "paragraphs": []}


def _merge_titles(prev: str, new: str) -> str:
    if re.fullmatch(r"(chapter|capítulo|capitulo|part|parte)?\s*[\dIVXLC]+\.?", prev.strip(), re.I):
        return f"{prev.strip().rstrip('.')}. {new}"
    return f"{prev} — {new}"


def _finalize(book: dict, min_words: int = 40, skip_titles: bool = True) -> dict:
    chapters = []
    for ch in book["chapters"]:
        words = sum(len(p.split()) for p in ch["paragraphs"])
        if words < min_words:
            continue
        if skip_titles and SKIP_TITLE_RE.match(ch["title"].strip()):
            continue
        if skip_titles and ch["title"].strip() == (book.get("title") or "").strip() and words < 400:
            continue
        chapters.append(ch)
    if not chapters:
        raise ValueError("No se pudo extraer texto del documento (¿está escaneado? haría falta OCR).")
    book["chapters"] = chapters
    if not book.get("lang"):
        book["lang"] = detect_lang(" ".join(" ".join(c["paragraphs"]) for c in chapters[:6]))
    book["lang"] = (book["lang"] or "en")[:2].lower()
    return book


# ----------------------------------------------------------------------------
# EPUB
# ----------------------------------------------------------------------------
def from_epub(path: str) -> dict:
    import warnings

    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
    from ebooklib import ITEM_DOCUMENT, epub

    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

    book = epub.read_epub(path, options={"ignore_ncx": True})

    def meta(key):
        v = book.get_metadata("DC", key)
        return v[0][0] if v else ""

    out = {"title": meta("title") or Path(path).stem, "author": meta("creator"), "lang": meta("language"), "chapters": []}
    cur = None
    fresh = False  # el capítulo actual solo tiene título (sin párrafos todavía)

    for item_id, _linear in book.spine:
        item = book.get_item_with_id(item_id)
        if item is None or item.get_type() != ITEM_DOCUMENT:
            continue
        soup = BeautifulSoup(item.get_content(), "lxml")
        body = soup.body or soup
        for node in body.find_all(string=True):
            if "*" in node:
                node.replace_with(node.replace("*", "∗"))
        for s in body.find_all(["sup", "script", "style"]):
            s.decompose()
        for br in body.find_all("br"):
            br.replace_with(" ")
        for tag in body.find_all(["em", "i"]):
            tag.insert_before("*")
            tag.insert_after("*")
            tag.unwrap()
        for tag in body.find_all(["strong", "b"]):
            tag.insert_before("**")
            tag.insert_after("**")
            tag.unwrap()

        for el in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote"]):
            if el.name == "blockquote" and el.find("p"):
                continue
            text = _clean(el.get_text(""))
            text = re.sub(r"\*\*\s*\*\*|(?<!\*)\*\s*\*(?!\*)", "", text)
            text = re.sub(r"(?<!\*)\*(\s+)([^*]+?)\*(?!\*)", r"\1*\2*", text)
            text = re.sub(r"(?<!\*)\*([^*]+?)(\s+)\*(?!\*)", r"*\1*\2", text)
            if not text or JUNK_RE.search(text) and len(text) < 80:
                continue
            cls = " ".join(el.get("class", [])).lower()
            if el.name in ("h1", "h2"):
                if cur is not None and fresh:
                    cur["title"] = _merge_titles(cur["title"], text)
                else:
                    cur = _new_chapter(text)
                    out["chapters"].append(cur)
                fresh = True
                continue
            if cur is None:
                cur = _new_chapter(out["title"])
                out["chapters"].append(cur)
            fresh = False
            if el.name in ("h3", "h4", "h5", "h6"):
                cur["paragraphs"].append("## " + text)
            elif el.name == "li":
                cur["paragraphs"].append("• " + text)
            elif el.name == "blockquote" or el.find_parent("blockquote") or "epigraph" in cls:
                cur["paragraphs"].append("> " + text)
            elif "question" in cls:
                cur["paragraphs"].append("**" + text.strip("*") + "**")
            else:
                cur["paragraphs"].append(text)
    return _finalize(out)


# ----------------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------------
def from_pdf(path: str) -> dict:
    import statistics

    import pymupdf

    doc = pymupdf.open(path)
    meta = doc.metadata or {}
    pages = []
    size_chars: Counter = Counter()
    for page in doc:
        H = page.rect.height
        lines = []
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for l in b["lines"]:
                spans = [s for s in l["spans"] if s["text"].strip()]
                if not spans:
                    continue
                text = _clean(_noast("".join(s["text"] for s in l["spans"])))
                if not text:
                    continue
                size = round(max(s["size"] for s in spans), 1)
                chars = sum(len(s["text"]) for s in spans)
                bold = all((s["flags"] & 16) or "bold" in s["font"].lower() for s in spans)
                x0, y0, x1, y1 = l["bbox"]
                lines.append({"t": text, "size": size, "x0": x0, "x1": x1, "y0": y0, "y1": y1, "bold": bool(bold)})
                size_chars[size] += chars
        pages.append({"H": H, "W": page.rect.width, "lines": lines})
    if not size_chars:
        raise ValueError("El PDF no tiene texto (¿escaneado? haría falta OCR).")
    body_size = size_chars.most_common(1)[0][0]

    # encabezados/pies repetidos y números de página
    def norm(t):
        return re.sub(r"\d+", "#", t.lower())

    edge_counter: Counter = Counter()
    for p in pages:
        for ln in p["lines"]:
            if ln["y0"] < 0.09 * p["H"] or ln["y1"] > 0.92 * p["H"]:
                edge_counter[norm(ln["t"])] += 1
    thresh = max(3, int(0.15 * len(pages)))

    def is_noise(ln, p):
        in_edge = ln["y0"] < 0.09 * p["H"] or ln["y1"] > 0.92 * p["H"]
        if not in_edge:
            return False
        t = ln["t"].strip()
        if re.fullmatch(r"[\divxlc\s·\-–|]+", t, re.I):
            return True
        return edge_counter[norm(t)] >= thresh

    body_lines = [ln for p in pages for ln in p["lines"] if abs(ln["size"] - body_size) < 0.6 and not is_noise(ln, p)]
    if not body_lines:
        raise ValueError("No se encontró texto de cuerpo en el PDF.")
    lefts = Counter(round(ln["x0"] / 2) * 2 for ln in body_lines)
    left = lefts.most_common(1)[0][0]
    heights = [ln["y1"] - ln["y0"] for ln in body_lines]
    lh = statistics.median(heights)
    rights = sorted(ln["x1"] for ln in body_lines)
    right = rights[int(0.9 * (len(rights) - 1))]

    out = {"title": (meta.get("title") or Path(path).stem).replace(".indd", ""), "author": meta.get("author") or "", "lang": "", "chapters": []}
    cur = None
    para: list[str] = []
    heading: list[str] = []
    prev = None

    def join(parts):
        txt = ""
        for part in parts:
            if not txt:
                txt = part
            elif txt.endswith("-") and part[:1].islower() and len(txt) > 1 and txt[-2].isalpha():
                txt = txt[:-1] + part
            else:
                txt += " " + part
        return txt

    def flush_para():
        nonlocal para
        if para and cur is not None:
            txt = join(para).strip()
            if txt:
                cur["paragraphs"].append(txt)
        para = []

    def flush_heading():
        nonlocal heading, cur
        if heading:
            title = " ".join(heading).strip()
            if cur is not None and not cur["paragraphs"]:
                cur["title"] = _merge_titles(cur["title"], title)
            else:
                cur = _new_chapter(title)
                out["chapters"].append(cur)
        heading = []

    for p in pages:
        for ln in p["lines"]:
            if is_noise(ln, p):
                continue
            is_head = (ln["size"] >= body_size * 1.18 and len(ln["t"]) < 160) or (
                ln["bold"] and ln["t"].isupper() and len(ln["t"]) < 120 and ln["size"] >= body_size * 0.95
            )
            if is_head:
                flush_para()
                heading.append(ln["t"])
                prev = ln
                continue
            if heading:
                flush_heading()
            if cur is None:
                cur = _new_chapter(out["title"])
                out["chapters"].append(cur)
            new_par = False
            if not para:
                new_par = True
            else:
                gap = ln["y0"] - prev["y1"] if prev is not None and prev["y1"] <= ln["y0"] + 1 else 0
                if ln["x0"] - left > 0.8 * body_size:
                    new_par = True
                elif gap > 0.55 * lh:
                    new_par = True
                elif BULLET_RE.match(ln["t"]):
                    new_par = True
                elif prev is not None and prev["x1"] < right - 0.25 * (right - left) and para[-1].rstrip()[-1:] in ".!?…”\"":
                    new_par = True
            if new_par:
                flush_para()
            para.append(ln["t"])
            prev = ln
    flush_para()
    flush_heading()
    for ch in out["chapters"]:
        ch["paragraphs"] = [("• " + BULLET_RE.sub("", t)) if BULLET_RE.match(t) else t for t in ch["paragraphs"]]
    return _finalize(out)


# ----------------------------------------------------------------------------
# texto plano / transcripciones / web / YouTube
# ----------------------------------------------------------------------------
def from_text(text: str, title: str = "Texto", lang: str = "") -> dict:
    text = _noast(text)
    paras = [_clean(p) for p in re.split(r"\n\s*\n", text) if _clean(p)]
    if len(paras) <= 2:  # sin saltos de párrafo: cortar luego por oraciones
        paras = [_clean(text)]
    chapters, cur = [], None
    for p in paras:
        m = re.match(r"^#{1,2}\s+(.*)", p)
        if m:
            cur = _new_chapter(m.group(1))
            chapters.append(cur)
            continue
        if cur is None:
            cur = _new_chapter(title)
            chapters.append(cur)
        cur["paragraphs"].append("• " + BULLET_RE.sub("", p) if BULLET_RE.match(p) else p)
    return _finalize({"title": title, "author": "", "lang": lang, "chapters": chapters}, min_words=1, skip_titles=False)


def from_url(url: str) -> dict:
    import trafilatura

    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise ValueError("No pude descargar la página (¿bloqueada o sin conexión?).")
    md = trafilatura.extract(downloaded, output_format="markdown", include_comments=False, include_tables=False)
    md = _noast(strip_footnote_marks(strip_code_fences(md))) if md else md
    if not md:
        raise ValueError("No pude extraer el texto principal de la página.")
    meta = trafilatura.extract_metadata(downloaded)
    title = (meta.title if meta and meta.title else url)
    author = meta.author if meta and meta.author else ""
    out = {"title": title, "author": author or "", "lang": (meta.language if meta and meta.language else ""), "chapters": []}
    cur = _new_chapter(title)
    out["chapters"].append(cur)
    for blk in re.split(r"\n\s*\n", md):
        blk = blk.strip()
        if not blk:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", blk)
        if m:
            cur["paragraphs"].append("## " + _clean(m.group(2)))
        elif re.match(r"^[-*]\s", blk):
            for item in blk.split("\n"):
                cur["paragraphs"].append("• " + _clean(re.sub(r"^[-*]\s+", "", item)))
        else:
            cur["paragraphs"].append(_clean(blk))
    return _finalize(out, min_words=1, skip_titles=False)


def _youtube_id(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


def from_youtube(url: str, languages: tuple = ("es", "en")) -> dict:
    from youtube_transcript_api import YouTubeTranscriptApi

    vid = _youtube_id(url)
    if not vid:
        raise ValueError("No pude identificar el ID del video de YouTube.")
    try:
        fetched = YouTubeTranscriptApi().fetch(vid, languages=list(languages))
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"No pude bajar la transcripción de YouTube ({type(e).__name__}). Pegá la transcripción como texto.") from e
    snippets = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else list(fetched)
    title, author = f"Video {vid}", ""
    try:
        import json
        import urllib.request

        with urllib.request.urlopen(f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json", timeout=10) as r:
            info = json.loads(r.read().decode("utf8"))
            title, author = info.get("title", title), info.get("author_name", "")
    except Exception:  # noqa: BLE001
        pass

    paras, cur, words, last_end = [], [], 0, 0.0
    for s in snippets:
        txt = _clean(re.sub(r"\[[^\]]*\]|>>", " ", s["text"]))
        if not txt:
            continue
        gap = s["start"] - last_end
        if cur and ((gap > 1.8 and words > 35) or words > 110):
            paras.append((" ".join(cur), s["start"]))
            cur, words = [], 0
        cur.append(txt)
        words += len(txt.split())
        last_end = s["start"] + s.get("duration", 0)
    if cur:
        paras.append((" ".join(cur), last_end))

    chapters, ch, ch_words, start = [], None, 0, 0.0
    for text, t in paras:
        if ch is None or ch_words > 1500:
            if ch is not None:
                start = t
            ch = _new_chapter(f"Parte {len(chapters) + 1} · {int(start // 60)}:{int(start % 60):02d}")
            chapters.append(ch)
            ch_words = 0
        ch["paragraphs"].append(text)
        ch_words += len(text.split())
    if len(chapters) == 1:
        chapters[0]["title"] = title
    return _finalize({"title": title, "author": author, "lang": "", "chapters": chapters}, min_words=1, skip_titles=False)


# ----------------------------------------------------------------------------
# punto de entrada
# ----------------------------------------------------------------------------
def load(source: str, title: str | None = None, author: str | None = None, lang: str | None = None) -> dict:
    s = str(source).strip()
    if re.match(r"https?://", s):
        book = from_youtube(s) if re.search(r"(youtube\.com|youtu\.be)", s) else from_url(s)
    else:
        p = Path(s).expanduser()
        if p.exists():
            ext = p.suffix.lower()
            if ext == ".epub":
                book = from_epub(str(p))
            elif ext == ".pdf":
                book = from_pdf(str(p))
            elif ext in (".txt", ".md", ".srt", ".vtt"):
                raw = p.read_text(encoding="utf8", errors="replace")
                if ext in (".srt", ".vtt"):
                    raw = re.sub(r"^\d+\s*$|^\d{2}:\d{2}.*-->.*$|^WEBVTT.*$", " ", raw, flags=re.M)
                book = from_text(raw, title=p.stem)
            else:
                raise ValueError(f"Formato no soportado: {ext}")
        elif "\n" in s or len(s.split()) > 30:
            book = from_text(s, title=title or "Texto")
        else:
            raise ValueError(f"No encontré el archivo: {s}")
    if title:
        book["title"] = title
    if author:
        book["author"] = author
    if lang:
        book["lang"] = lang
    return book


def select_chapters(book: dict, chapter: str | None = None, limit_words: int | None = None) -> dict:
    """Se queda con un capítulo (por número o texto del título) y/o las primeras N palabras."""
    chs = book["chapters"]
    if chapter:
        c = str(chapter).strip().lower()
        found = [x for x in chs if re.match(rf"^{re.escape(c)}(\b|\.|\s|—)", x["title"].lower()) or c in x["title"].lower()]
        if not found and c.isdigit() and 1 <= int(c) <= len(chs):
            found = [chs[int(c) - 1]]
        if not found:
            raise ValueError(f"No encontré el capítulo '{chapter}'. Capítulos: " + "; ".join(x["title"] for x in chs[:25]))
        chs = found[:1] if c.isdigit() else found
    if limit_words:
        total, kept = 0, []
        for ch in chs:
            new = {"title": ch["title"], "paragraphs": []}
            for p in ch["paragraphs"]:
                if total >= limit_words:
                    break
                new["paragraphs"].append(p)
                total += len(p.split())
            if new["paragraphs"]:
                kept.append(new)
            if total >= limit_words:
                break
        chs = kept
    return {**book, "chapters": chs}
