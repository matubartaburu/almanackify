import unittest
from unittest import mock

from almanackify import extract


def snippets(n=40, words=60, text="Great advertising is measured by what it sells, not by what it amuses. "):
    unit = (text * 10).split()
    return [{"text": " ".join(unit[:words]), "start": i * 20.0, "duration": 19.0} for i in range(n)]


class FakeApi:
    """Sustituye a YouTubeTranscriptApi: no toca la red."""
    result = None
    error = None

    def fetch(self, vid, languages=None):
        if FakeApi.error:
            raise FakeApi.error
        return FakeApi.result


class YoutubeIds(unittest.TestCase):
    def test_id_is_found_in_every_common_url_shape(self):
        for url in ("https://www.youtube.com/watch?v=uJuxenfe-NU&t=2817s", "https://youtu.be/uJuxenfe-NU?t=5",
                    "https://www.youtube.com/shorts/uJuxenfe-NU", "https://www.youtube.com/embed/uJuxenfe-NU"):
            self.assertEqual(extract._youtube_id(url), "uJuxenfe-NU", url)


class YoutubeTranscripts(unittest.TestCase):
    def setUp(self):
        FakeApi.error, FakeApi.result = None, None
        p = mock.patch("youtube_transcript_api.YouTubeTranscriptApi", FakeApi)
        p.start(); self.addCleanup(p.stop)
        q = mock.patch("urllib.request.urlopen", side_effect=OSError("sin red"))  # el título (oembed) también necesita red
        q.start(); self.addCleanup(q.stop)

    def test_unreachable_youtube_gives_an_actionable_english_message(self):
        FakeApi.error = ConnectionError("blocked")
        with self.assertRaises(extract.SourceError) as cm:
            extract.from_youtube("https://www.youtube.com/watch?v=uJuxenfe-NU")
        self.assertEqual(cm.exception.code, "youtube_unreachable")
        msg = str(cm.exception)
        self.assertIn("Text tab", msg)
        self.assertNotIn("Pegá", msg)

    def test_video_without_captions_is_reported_as_such(self):
        class TranscriptsDisabled(Exception):
            pass
        FakeApi.error = TranscriptsDisabled("off")
        with self.assertRaises(extract.SourceError) as cm:
            extract.from_youtube("https://youtu.be/uJuxenfe-NU")
        self.assertEqual(cm.exception.code, "youtube_no_transcript")

    def test_bad_url_is_a_clear_error(self):
        with self.assertRaises(extract.SourceError) as cm:
            extract.from_youtube("https://youtube.com/")
        self.assertIn("video ID", str(cm.exception))

    def test_transcript_becomes_paragraphs_and_english_parts(self):
        FakeApi.result = snippets()
        book = extract.from_youtube("https://www.youtube.com/watch?v=uJuxenfe-NU&t=2817s")
        self.assertEqual(book["title"], "Video uJuxenfe-NU")
        self.assertGreaterEqual(len(book["chapters"]), 2)
        self.assertTrue(book["chapters"][0]["title"].startswith("Part 1 ·"), book["chapters"][0]["title"])
        self.assertTrue(all(c["paragraphs"] for c in book["chapters"]))
        self.assertEqual(book["lang"], "en")

    def test_spanish_transcript_keeps_spanish_part_labels(self):
        FakeApi.result = snippets(text="La publicidad buena se mide por lo que vende y no por lo que divierte a la gente. ")
        book = extract.from_youtube("https://youtu.be/uJuxenfe-NU")
        self.assertTrue(book["chapters"][0]["title"].startswith("Parte 1 ·"), book["chapters"][0]["title"])


if __name__ == "__main__":
    unittest.main()
