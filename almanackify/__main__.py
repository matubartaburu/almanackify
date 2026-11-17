import argparse
import json
import sys

from .core import build, render_json


def main():
    ap = argparse.ArgumentParser(prog="almanackify", description="Convierte libros/artículos/videos al formato 'Almanack' (párrafos cortos + cajas tipo tweet).")
    ap.add_argument("source", help="archivo .epub/.pdf/.txt, URL de artículo o YouTube, o un .json ya procesado")
    ap.add_argument("-o", "--out", default="./salida")
    ap.add_argument("--formats", nargs="+", default=["epub", "pdf"], choices=["epub", "pdf"])
    ap.add_argument("--chapter", help="solo este capítulo (número o parte del título)")
    ap.add_argument("--limit-words", type=int, help="solo las primeras N palabras")
    ap.add_argument("--every", type=int, default=220, help="una caja cada ~N palabras (default 220)")
    ap.add_argument("--no-chain", action="store_true")
    ap.add_argument("--dedupe", action="store_true", help="sacar de la prosa la frase que va en la caja")
    ap.add_argument("--title"); ap.add_argument("--author"); ap.add_argument("--lang")
    a = ap.parse_args()
    if a.source.endswith(".json"):
        r = render_json(a.source, a.out, a.formats)
    else:
        r = build(a.source, a.out, a.formats, a.chapter, a.limit_words, a.title, a.author, a.lang, a.every, not a.no_chain, a.dedupe)
    print(json.dumps(r, ensure_ascii=False, indent=1))


main()
