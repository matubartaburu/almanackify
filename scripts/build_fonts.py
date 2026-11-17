"""Genera fuentes estáticas y livianas de EB Garamond para el EPUB (el Kindle no maneja bien fuentes variables).

Uso: .venv/bin/python scripts/build_fonts.py
"""
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

FONTS = Path(__file__).resolve().parent.parent / "almanackify" / "fonts"
OUT = FONTS / "static"
UNICODES = list(range(0x20, 0x7F)) + list(range(0xA0, 0x180)) + [
    0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2026, 0x2190, 0x2191, 0x2192, 0x2193,
]
JOBS = [("EBGaramond.ttf", 400, "Regular"), ("EBGaramond.ttf", 700, "Bold"),
        ("EBGaramond-Italic.ttf", 400, "Italic"), ("EBGaramond-Italic.ttf", 700, "BoldItalic")]


def main():
    OUT.mkdir(exist_ok=True)
    for src, wght, name in JOBS:
        font = instantiateVariableFont(TTFont(FONTS / src), {"wght": wght})
        opts = subset.Options()
        opts.layout_features = ["kern", "liga", "onum", "lnum"]
        opts.name_IDs = [1, 2, 3, 4, 6]
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=UNICODES)
        sub.subset(font)
        dest = OUT / f"EBGaramond-{name}.ttf"
        font.save(dest)
        print(dest.name, dest.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
