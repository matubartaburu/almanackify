import io
import re
import tempfile
import unittest
import zipfile
from pathlib import Path

from fontTools.ttLib import TTFont

from almanackify import render

BOOK = {
    "title": "Self-Reliance",
    "author": "Ralph Waldo Emerson",
    "lang": "en",
    "chapters": [
        {
            "title": "Self-Reliance",
            "blocks": [
                {"type": "p", "text": "Trust thyself: every heart vibrates to that iron string."},
                {"type": "tweet", "text": "Whoso would be a man, must be a nonconformist."},
                {"type": "chain", "title": "Review", "items": ["Trust yourself", "Resist conformity"]},
            ],
        }
    ],
}


def build_epub():
    d = tempfile.mkdtemp()
    path = render.to_epub(BOOK, str(Path(d) / "t.epub"))
    return zipfile.ZipFile(path)


class EpubForKindle(unittest.TestCase):
    def test_static_fonts_are_embedded_and_declared(self):
        z = build_epub()
        fonts = [n for n in z.namelist() if n.endswith(".ttf")]
        self.assertEqual(len(fonts), 4)
        css = z.read("EPUB/style/almanack.css").decode()
        self.assertEqual(len(re.findall(r"@font-face", css)), 4)
        for n in fonts:
            self.assertIn(Path(n).name, css)

    def test_embedded_fonts_are_not_variable(self):
        z = build_epub()
        for n in (x for x in z.namelist() if x.endswith(".ttf")):
            self.assertNotIn("fvar", TTFont(io.BytesIO(z.read(n))), n)

    def test_cover_is_declared_and_present(self):
        z = build_epub()
        opf = z.read("EPUB/content.opf").decode()
        self.assertRegex(opf, r'properties="cover-image"')
        self.assertRegex(opf, r'<meta name="cover"')
        covers = [n for n in z.namelist() if "cover" in n.lower() and n.lower().endswith((".jpg", ".jpeg", ".png"))]
        self.assertEqual(len(covers), 1)
        self.assertGreater(len(z.read(covers[0])), 5_000)

    def test_cover_quote_is_the_strongest_box_not_the_first(self):
        book = {"lang": "en", "chapters": [{"title": "x", "blocks": [
            {"type": "tweet", "text": "He said that it was a long walk back to the old house yesterday."},
            {"type": "tweet", "text": "Your goodness must have some edge to it, else it is none."},
        ]}]}
        self.assertEqual(render._cover_quote(book), "Your goodness must have some edge to it, else it is none.")

    def test_idea_card_is_a_16_9_png(self):
        import pymupdf

        png = render.make_card("Trust thyself: every heart vibrates to that iron string.", "Self-Reliance", "Ralph Waldo Emerson")
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        pix = pymupdf.Pixmap(png)
        self.assertAlmostEqual(pix.width / pix.height, 16 / 9, delta=0.02)
        self.assertGreaterEqual(pix.width, 1200)

    def test_every_manifest_item_exists_in_the_zip(self):
        z = build_epub()
        opf = z.read("EPUB/content.opf").decode()
        names = set(z.namelist())
        for href in re.findall(r'<item[^>]*href="([^"]+)"', opf):
            self.assertIn("EPUB/" + href, names, href)

    def test_reading_starts_at_the_title_page_not_the_contents_page(self):
        z = build_epub()
        opf = z.read("EPUB/content.opf").decode()
        spine = re.search(r"<spine[^>]*>(.*?)</spine>", opf, re.S).group(1)
        refs = re.findall(r"<itemref ([^>]*)/>", spine)
        self.assertNotIn('idref="nav"', spine)  # el TOC sigue en el manifiesto, pero no es una página de lectura
        self.assertIn('idref="titlepage"', refs[0])
        self.assertTrue(all("linear" not in r for r in refs))  # sin contenido "no lineal" (epubcheck OPF-096)

    def test_document_language_and_metadata(self):
        z = build_epub()
        opf = z.read("EPUB/content.opf").decode()
        self.assertIn("<dc:title>Self-Reliance</dc:title>", opf)
        self.assertIn("Ralph Waldo Emerson", opf)
        self.assertIn("<dc:language>en</dc:language>", opf)


if __name__ == "__main__":
    unittest.main()
