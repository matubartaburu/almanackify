import unittest

from almanackify import extract, process


class FootnoteMarks(unittest.TestCase):
    def test_escaped_footnote_marks_are_removed(self):
        text = "That is the bet. \\[ 3 \\] Four steps: choose a field. \\[3\\] Next."
        out = extract.strip_footnote_marks(text)
        self.assertNotIn("\\[", out)
        self.assertNotIn("[ 3", out)
        self.assertIn("That is the bet.", out)
        self.assertIn("Four steps: choose a field.", out)

    def test_plain_bracket_marks_are_removed(self):
        self.assertEqual(extract.strip_footnote_marks("A claim [12] holds."), "A claim holds.")

    def test_non_numeric_brackets_are_kept(self):
        self.assertIn("[sic]", extract.strip_footnote_marks("He wrote [sic] twice."))


class CodeFences(unittest.TestCase):
    def test_fence_markers_are_removed_but_text_is_kept(self):
        out = extract.strip_code_fences("```\n``` Ne te quaesiveris extra.\n\nOur acts our angels are.")
        self.assertNotIn("```", out)
        self.assertIn("Ne te quaesiveris extra.", out)
        self.assertIn("Our acts our angels are.", out)


class ArchiveBoilerplate(unittest.TestCase):
    NOTICE = [
        "This book was produced in EPUB format by the Internet Archive.",
        "The book pages were scanned and converted to EPUB format automatically. This process relies on optical character recognition, and is somewhat susceptible to errors.",
        "The hidden page numbering which may be available to your ereader corresponds to the numbered pages in the print edition.",
    ]

    def test_internet_archive_scan_notice_is_dropped(self):
        book = {"title": "T", "author": "", "lang": "en", "chapters": [
            {"title": "T", "paragraphs": self.NOTICE + ["Advertising is salesmanship in print."]}]}
        out = extract.drop_archive_boilerplate(book)
        self.assertEqual(out["chapters"][0]["paragraphs"], ["Advertising is salesmanship in print."])

    def test_the_same_words_deep_in_a_book_are_kept(self):
        body = ["Intro one.", "Intro two."] * 10 + ["We use optical character recognition in this chapter."]
        book = {"title": "T", "author": "", "lang": "en", "chapters": [{"title": "T", "paragraphs": body}]}
        self.assertIn("We use optical character recognition in this chapter.", extract.drop_archive_boilerplate(book)["chapters"][0]["paragraphs"])


class StandaloneBoxes(unittest.TestCase):
    def test_sentence_pointing_back_is_not_a_box(self):
        s = "Learning, for example, is an instance of this phenomenon: the more you learn about something, the easier it is to learn more."
        self.assertIsNone(process.aphorism(s, "en"))

    def test_these_and_above_are_not_boxes(self):
        for s in (
            "The best founders understand these tradeoffs better than anyone else around them.",
            "Nothing in the list above matters as much as simply doing the work every day.",
        ):
            self.assertIsNone(process.aphorism(s, "en"), s)

    def test_such_is_a_back_reference(self):
        s = "The soul always hears an admonition in such lines, let the subject be what it may."
        self.assertIsNone(process.aphorism(s, "en"))

    def test_spanish_back_reference_is_not_a_box(self):
        s = "Aprender es un ejemplo de este fenómeno: cuanto más sabés, más fácil es aprender."
        self.assertIsNone(process.aphorism(s, "es"))

    def test_list_ordinals_are_not_boxes(self):
        for s in (
            "Fourthly, when it plays a part, and does or says anything insincerely and untruly.",
            "Secondly, a person should always weigh the cost of every promise they make.",
        ):
            self.assertIsNone(process.aphorism(s, "en"), s)

    def test_standalone_aphorisms_still_qualify(self):
        for s in (
            "The way to figure out what to work on is by working.",
            "People who do great things don't get a lot done every day.",
            "Boldly chase outlier ideas, even if other people aren't interested in them — in fact, especially if they aren't.",
        ):
            self.assertIsNotNone(process.aphorism(s, "en"), s)


if __name__ == "__main__":
    unittest.main()
