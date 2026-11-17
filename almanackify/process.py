"""Procesador sin IA: párrafos cortos + cajas "tipo tweet" + cadena ↓ por capítulo.

Las cajas se eligen del propio texto con un puntaje (centralidad tipo TextRank sobre
TF-IDF + densidad de términos + "aforismo-ness" por heurísticas). No se reescribe nada.

Salida (dict serializable):
    {"title","author","lang","chapters":[{"title","blocks":[
        {"type":"p"|"q"|"quote"|"h2"|"tweet"|"list"|"chain", ...}]}]}
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

ABBR = {
    "sr", "sra", "srta", "dr", "dra", "prof", "etc", "vs", "ej", "pág", "págs", "fig", "cap", "art", "núm", "ud", "uds",
    "mr", "mrs", "ms", "jr", "sr", "st", "no", "inc", "ltd", "co", "corp", "dept", "approx", "est", "vol", "al", "cf",
    "u.s", "e.g", "i.e", "a.m", "p.m", "ph.d", "u.k", "n.y", "d.c",
}
BOUND = re.compile(r"([.!?…]+[\"”»’')\]*]*)\s+(?=[\"“«‘¿¡(\[*]*[A-ZÁÉÍÓÚÑÜ0-9])")

STOP = {
    "es": set("el la los las de del al y o u e en un una unos unas que se su sus lo le les me te nos mi mis tu tus por para con sin sobre entre como pero si no ni es son era eran fue fueron ser estar está están hay ha han he has más menos muy ya también esto eso esta este ese esa estos esos aquí allí cuando donde quien cual cuales porque qué cómo yo tú él ella ellos ellas usted ustedes nosotros".split()),
    "en": set("the a an and or but of to in on at by for with from as is are was were be been being it its this that these those he she they we you i me my your his her their our not no do does did have has had will would can could should may might there here what which who whom when where why how than then so if just also very more most some any all each other into over after before about out up down".split()),
}

BAD_START = set(
    "pero y o sino aunque además también entonces así esto eso ello él ella ellos ellas le les esta este ese esa estos esos "
    "aquello aquí allí bueno hmm because porque imagine imagina remember recuerda consider suppose suppongamos let here’s here's lets "
    "but and or so then also this that these those he she they it his her their its such yet though although however thus hence "
    "moreover furthermore instead otherwise still".split()
)
BAD_PREFIX = re.compile(
    r"^(por ejemplo|sin embargo|por lo tanto|por eso|en cambio|es decir|en efecto|de hecho|para eso|"
    r"for example|for instance|in fact|that is|in other words|of course|in short|that said|on the other hand)\b",
    re.I,
)
GENERAL = set(
    "nunca siempre todo todos toda todas nadie cada nada mejor peor solo sólo sino debes debe pueden puede hay "
    "never always everything everyone nobody every only best worst must should can cannot nothing anything "
    "most more less without rather".split()
)
MIN_APHO = 0.55
PAST_WORDS = set("was were had did said went became got made took came saw knew thought told asked fue fueron era eran tuvo hizo dijo".split())
FIRST_PERSON = re.compile(r"\b(yo|me|mi|mis|conmigo|I|I’m|I'm|I’ve|I've|I’d|I'd|my|me|myself|we|our|nos|nuestro)\b")


@dataclass
class Opts:
    box_every_words: int = 220      # una caja aprox. cada N palabras de prosa
    max_par_words: int = 70         # párrafos más largos se parten
    chain: bool = True              # cadena ↓ al cierre de cada capítulo
    chain_min_words: int = 900      # capítulo mínimo para tener cadena
    chain_items: int = 5
    dedupe: bool = False            # True: la frase de la caja se saca de la prosa
    lang: str = "en"


# ----------------------------------------------------------------------------
def strip_marks(t: str) -> str:
    return t.replace("*", "")


def split_sentences(text: str) -> list[str]:
    out, start = [], 0
    for m in BOUND.finditer(text):
        end = m.end(1)
        head = text[start : m.start(1) + 1]
        toks = head.split()
        tok = toks[-1].lower().strip("\"“”‘’()[]*").rstrip(".!?…") if toks else ""
        if m.group(1).startswith(".") and (tok in ABBR or (len(tok) == 1 and tok.isalpha()) or tok.isdigit()):
            continue
        out.append(text[start:end].strip())
        start = m.end()
    rest = text[start:].strip()
    if rest:
        out.append(rest)
    return out


def tokens(s: str, stop: set) -> list[str]:
    return [w for w in re.findall(r"[^\W\d_]+", strip_marks(s).lower()) if len(w) > 2 and w not in stop]


def aphorism(s: str, lang: str) -> float | None:
    """None = no elegible. Si no, puntaje 0..1 de qué tan 'tuiteable' es."""
    plain = strip_marks(s).strip()
    words = plain.split()
    n = len(words)
    if n < 7 or n > 32:
        return None
    if plain.endswith("?") or re.search(r"\[\d+\]|https?:|@\w|\bwww\.", plain):
        return None
    if plain.count("“") != plain.count("”") or plain.count("(") != plain.count(")"):
        return None
    first = re.sub(r"^[\"“‘'(¿¡]+", "", words[0]).lower().rstrip(",;:")
    if first in BAD_START or BAD_PREFIX.match(plain):
        return None
    if re.match(r"^[a-záéíóúñ]", plain):  # empieza en minúscula: fragmento
        return None
    sc = 0.35
    sc += 0.3 if 10 <= n <= 22 else (0.15 if n < 10 or n <= 28 else 0.0)
    lw = [w.lower().strip(".,;:!?\"“”") for w in words]
    sc += min(0.3, 0.1 * sum(1 for w in lw if w in GENERAL))
    if FIRST_PERSON.search(plain):
        sc -= 0.2
    # relato en pasado => poco "tuiteable"; afirmaciones generales/contrastes => más
    past = 0
    for w in lw:
        if w in PAST_WORDS or (lang == "en" and len(w) > 4 and w.endswith("ed")) or (
            lang == "es" and len(w) > 4 and (w.endswith(("ó", "aron", "ieron", "aba", "aban", "ía", "ían")))
        ):
            past += 1
    sc -= min(0.3, 0.12 * past)
    if re.search(r"\b(not|rather|instead|never|isn[’']t|aren[’']t|don[’']t|can[’']t|won[’']t)\b|\b(no es|no son|sino|en lugar de|en vez de|nunca)\b", plain.lower()):
        sc += 0.1
    if re.search(r"[:—]", plain):
        sc += 0.05
    caps_mid = sum(1 for w in words[1:] if w[:1].isupper() and w.lower() not in GENERAL)
    sc -= min(0.3, 0.1 * caps_mid)
    if re.search(r"\d", plain):
        sc -= 0.15
    if re.search(r"\$|€|\d{2,}", plain):
        sc -= 0.2
    if re.search(r"[\"“”«»]", plain):
        sc -= 0.1
    if not plain.endswith((".", "!")):
        sc -= 0.2
    return max(0.0, min(1.0, sc))


def _pct(x: np.ndarray) -> np.ndarray:
    if len(x) == 0:
        return x
    order = x.argsort().argsort()
    return order / max(1, len(x) - 1)


def jaccard(a: set, b: set) -> float:
    return len(a & b) / max(1, len(a | b))


# ----------------------------------------------------------------------------
def shorten(paragraph: str, max_words: int) -> list[list[str]]:
    """Devuelve el párrafo como lista de párrafos (cada uno = lista de oraciones)."""
    sents = split_sentences(paragraph)
    # sin puntuación (transcripciones): cortar a mano
    fixed = []
    for s in sents:
        w = s.split()
        if len(w) > 60:
            for i in range(0, len(w), 28):
                fixed.append(" ".join(w[i : i + 28]))
        else:
            fixed.append(s)
    sents = fixed
    total = sum(len(s.split()) for s in sents)
    if total <= max_words:
        return [sents]
    groups, cur, cw = [], [], 0
    for s in sents:
        w = len(s.split())
        if cur and cw + w > max_words * 0.75 and cw >= 22:
            groups.append(cur)
            cur, cw = [], 0
        cur.append(s)
        cw += w
    if cur:
        if groups and cw < 14:
            groups[-1].extend(cur)
        else:
            groups.append(cur)
    return groups


def process(book: dict, opts: Opts | None = None) -> dict:
    from sklearn.feature_extraction.text import TfidfVectorizer

    opts = opts or Opts()
    lang = (book.get("lang") or opts.lang or "en")[:2]
    stop = STOP.get(lang, STOP["en"])

    # 1) estructura: párrafos -> grupos de oraciones, por capítulo
    chapters = []
    quoted: set[str] = set()
    all_sents: list[str] = []
    for ch in book["chapters"]:
        items = []  # ("p", [sents]) | ("q"/"quote"/"h2", text) | ("list", [items])
        pending_list: list[str] = []
        for raw in ch["paragraphs"]:
            if raw.startswith("• "):
                pending_list.append(raw[2:])
                continue
            if pending_list:
                items.append(("list", pending_list))
                pending_list = []
            if raw.startswith("## "):
                items.append(("h2", raw[3:]))
            elif raw.startswith("> "):
                items.append(("quote", raw[2:]))
            elif raw.startswith("**") and raw.endswith("**") and raw.count("**") == 2:
                items.append(("q", raw[2:-2]))
            else:
                bal = 0
                for s0 in split_sentences(raw):  # frases dentro de una cita/diálogo no sirven como caja
                    start = bal
                    bal += s0.count("“") - s0.count("”")
                    if start > 0 or bal > 0:
                        quoted.add(s0)
                for grp in shorten(raw, opts.max_par_words):
                    items.append(("p", grp))
                    all_sents.extend(grp)
        if pending_list:
            items.append(("list", pending_list))
        chapters.append((ch["title"], items))

    # 2) puntajes globales
    scores: dict[str, float] = {}
    if all_sents:
        uniq = list(dict.fromkeys(all_sents))
        vec = TfidfVectorizer(tokenizer=lambda s: tokens(s, stop), lowercase=False, token_pattern=None, max_df=0.4, sublinear_tf=True)
        X = vec.fit_transform(uniq)
        idx = {s: i for i, s in enumerate(uniq)}
        apho = [aphorism(s, lang) for s in uniq]
        # centralidad por capítulo (segmentos de <=1200 oraciones)
        cen = np.zeros(len(uniq))
        dens = np.zeros(len(uniq))
        for _title, items in chapters:
            sents = [s for kind, grp in items if kind == "p" for s in grp]
            ids = sorted({idx[s] for s in sents})
            for k in range(0, len(ids), 1200):
                seg = ids[k : k + 1200]
                if len(seg) < 2:
                    continue
                M = (X[seg] @ X[seg].T).toarray()
                np.fill_diagonal(M, 0)
                M[M < 0.05] = 0
                rs = M.sum(axis=1, keepdims=True)
                rs[rs == 0] = 1
                P = M / rs
                v = np.ones(len(seg)) / len(seg)
                for _ in range(30):
                    v = 0.15 / len(seg) + 0.85 * (P.T @ v)
                cen[seg] = _pct(v)
                top = np.asarray([np.sort(X[i].data)[-3:].mean() if X[i].nnz else 0 for i in seg])
                dens[seg] = _pct(top)
        for s, i in idx.items():
            a = apho[i]
            if a is None or s in quoted:
                continue
            if a < MIN_APHO:
                continue
            scores[s] = 0.30 * cen[i] + 0.20 * dens[i] + 0.50 * a

    # 3) cajas y cadenas
    out_chapters = []
    n_boxes = n_chains = 0
    used_global: list[set] = []
    for title, items in chapters:
        blocks = []
        acc = 0
        last_box_at = -1  # índice en items
        chapter_words = sum(len(s.split()) for kind, grp in items if kind == "p" for s in grp)
        chapter_boxes: list[str] = []
        for i, (kind, payload) in enumerate(items):
            if kind == "p":
                blocks.append({"type": "p", "text": " ".join(payload)})
                acc += sum(len(s.split()) for s in payload)
                nxt = items[i + 1][0] if i + 1 < len(items) else None
                if acc >= opts.box_every_words and nxt == "p":
                    cand = []
                    for j in range(last_box_at + 1, i + 1):
                        if items[j][0] != "p":
                            continue
                        for s in items[j][1]:
                            if s in scores and not any(jaccard(set(tokens(s, stop)), u) > 0.5 for u in used_global[-12:]):
                                cand.append((scores[s], j, s))
                    if cand:
                        _sc, j, s = max(cand)
                        used_global.append(set(tokens(s, stop)))
                        chapter_boxes.append(s)
                        if opts.dedupe:
                            for b in blocks:
                                if b["type"] == "p" and s in b["text"]:
                                    b["text"] = re.sub(r"\s+", " ", b["text"].replace(s, "", 1)).strip()
                            blocks = [b for b in blocks if not (b["type"] == "p" and not b["text"])]
                        blocks.append({"type": "tweet", "text": s})
                        n_boxes += 1
                        acc = 0
                        last_box_at = i
            elif kind == "list":
                blocks.append({"type": "list", "items": payload})
            else:
                blocks.append({"type": kind, "text": payload})
        if opts.chain and chapter_words >= opts.chain_min_words:
            sents = [s for kind, grp in items if kind == "p" for s in grp]
            k = max(3, min(opts.chain_items, chapter_words // 600))
            seg_len = max(1, len(sents) // k)
            picks = []
            for g in range(k):
                seg = sents[g * seg_len : (g + 1) * seg_len if g < k - 1 else len(sents)]
                cand = [(scores[s], s) for s in seg if s in scores and s not in chapter_boxes]
                if cand:
                    picks.append(max(cand)[1])
            if len(picks) >= 3:
                blocks.append({"type": "chain", "title": {"es": "En resumen:", "pt": "Em resumo:"}.get(lang, "In short:"), "items": picks})
                n_chains += 1
        out_chapters.append({"title": title, "blocks": blocks})

    return {
        "title": book.get("title", ""),
        "author": book.get("author", ""),
        "lang": lang,
        "chapters": out_chapters,
        "stats": {
            "chapters": len(out_chapters),
            "words": sum(len(p.split()) for ch in book["chapters"] for p in ch["paragraphs"]),
            "boxes": n_boxes,
            "chains": n_chains,
        },
    }
