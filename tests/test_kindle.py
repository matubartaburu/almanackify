import unittest
from unittest import mock

from almanackify import kindle


class Kindle(unittest.TestCase):
    def test_only_kindle_addresses_are_accepted(self):
        self.assertTrue(kindle.valid_kindle_address("name_1@kindle.com"))
        for bad in ("victim@gmail.com", "x@kindle.com.evil.com", "a@b@kindle.com", "", "x@notkindle.com"):
            self.assertFalse(kindle.valid_kindle_address(bad), bad)

    def test_config_needs_host_user_and_password(self):
        self.assertIsNone(kindle.smtp_config({"ALMANACKIFY_SMTP_HOST": "h"}))
        cfg = kindle.smtp_config({"ALMANACKIFY_SMTP_HOST": "h", "ALMANACKIFY_SMTP_USER": "u@x.com", "ALMANACKIFY_SMTP_PASSWORD": "p"})
        self.assertEqual((cfg["port"], cfg["from"]), (465, "u@x.com"))

    def test_epub_is_attached_and_sent_over_ssl(self):
        import tempfile, pathlib
        f = pathlib.Path(tempfile.mkdtemp()) / "book.epub"; f.write_bytes(b"PK-fake")
        cfg = {"host": "smtp.example.com", "port": 465, "user": "u@x.com", "password": "p", "from": "u@x.com"}
        with mock.patch("smtplib.SMTP_SSL") as ssl_cls:
            kindle.send_epub(str(f), "me@kindle.com", cfg)
        s = ssl_cls.return_value.__enter__.return_value
        s.login.assert_called_once_with("u@x.com", "p")
        msg = s.send_message.call_args[0][0]
        self.assertEqual(msg["To"], "me@kindle.com")
        self.assertEqual(next(msg.iter_attachments()).get_filename(), "book.epub")

    def test_foreign_address_is_refused_before_any_connection(self):
        with mock.patch("smtplib.SMTP_SSL") as ssl_cls:
            with self.assertRaises(ValueError):
                kindle.send_epub("x", "victim@gmail.com", {"host": "h", "port": 465, "user": "u", "password": "p", "from": "u"})
        ssl_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
