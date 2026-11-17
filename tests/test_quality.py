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

    def test_spanish_back_reference_is_not_a_box(self):
        s = "Aprender es un ejemplo de este fenómeno: cuanto más sabés, más fácil es aprender."
        self.assertIsNone(process.aphorism(s, "es"))

    def test_standalone_aphorisms_still_qualify(self):
        for s in (
            "The way to figure out what to work on is by working.",
            "People who do great things don't get a lot done every day.",
            "Boldly chase outlier ideas, even if other people aren't interested in them — in fact, especially if they aren't.",
        ):
            self.assertIsNotNone(process.aphorism(s, "en"), s)


if __name__ == "__main__":
    unittest.main()
