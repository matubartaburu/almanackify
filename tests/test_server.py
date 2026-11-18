import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from almanackify import server

TEXT = "\n\n".join(
    [
        "Trust thyself: every heart vibrates to that iron string. Accept the place the divine providence has found for you.",
        "Whoso would be a man must be a nonconformist. Nothing is at last sacred but the integrity of your own mind.",
        "A foolish consistency is the hobgoblin of little minds, adored by little statesmen and philosophers and divines.",
        "Speak what you think now in hard words, and tomorrow speak what tomorrow thinks in hard words again.",
        "To be great is to be misunderstood. Your goodness must have some edge to it, else it is none at all.",
        "The reliance on property, including the reliance on governments which protect it, is the want of self-reliance.",
    ]
    * 4
)


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.srv = server.make_server("127.0.0.1", 0, jobs_dir=cls.tmp.name)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def call(self, method, path, body=None, headers=None, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=120)
        h = dict(headers or {})
        c.putrequest(method, path, skip_host=True)
        c.putheader("Host", host or f"127.0.0.1:{self.port}")
        for k, v in h.items():
            c.putheader(k, v)
        data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else b"")
        c.putheader("Content-Length", str(len(data)))
        c.endheaders(data)
        r = c.getresponse()
        raw = r.read()
        c.close()
        return r.status, r.getheader("Content-Type", ""), raw

    JSON = {"Content-Type": "application/json", "X-Almanackify": "1"}

    def test_health_and_index(self):
        s, _, raw = self.call("GET", "/api/health")
        self.assertEqual(s, 200)
        self.assertTrue(json.loads(raw)["ok"])
        s, ct, raw = self.call("GET", "/")
        self.assertEqual(s, 200)
        self.assertIn("text/html", ct)
        self.assertIn(b"Almanackify", raw)

    def test_convert_requires_the_custom_header(self):
        s, _, _ = self.call("POST", "/api/convert", {"text": TEXT}, {"Content-Type": "application/json"})
        self.assertEqual(s, 403)

    def test_rejects_foreign_host_header(self):
        s, _, _ = self.call("GET", "/api/health", host="evil.example")
        self.assertEqual(s, 403)

    def test_local_paths_are_not_accepted_as_source(self):
        for src in ("/etc/hosts", "~/.ssh/id_rsa", "file:///etc/hosts", "relative/file.txt"):
            s, _, raw = self.call("POST", "/api/convert", {"source": src}, self.JSON)
            self.assertEqual(s, 400, src)
            self.assertIn("error", json.loads(raw))

    def test_empty_request_is_a_400(self):
        s, _, _ = self.call("POST", "/api/convert", {}, self.JSON)
        self.assertEqual(s, 400)

    def test_convert_text_returns_downloadable_epub(self):
        s, _, raw = self.call("POST", "/api/convert", {"text": TEXT, "title": "Demo", "formats": ["epub"]}, self.JSON)
        self.assertEqual(s, 200, raw[:300])
        res = json.loads(raw)
        self.assertEqual(res["title"], "Demo")
        self.assertIn("epub", res["files"])
        self.assertNotIn("pdf", res["files"])
        self.assertIsInstance(res["boxes"], list)
        s, ct, data = self.call("GET", res["files"]["epub"])
        self.assertEqual(s, 200)
        self.assertEqual(data[:2], b"PK")
        self.assertIn("epub", ct)

    def test_file_upload_txt(self):
        s, _, raw = self.call(
            "POST", "/api/convert-file?formats=epub", TEXT.encode(),
            {"X-Almanackify": "1", "X-Filename": "emerson.txt", "Content-Type": "application/octet-stream"},
        )
        self.assertEqual(s, 200, raw[:300])
        self.assertEqual(json.loads(raw)["title"], "emerson")

    def test_upload_rejects_unknown_extension(self):
        s, _, _ = self.call("POST", "/api/convert-file", b"MZ", {"X-Almanackify": "1", "X-Filename": "evil.exe"})
        self.assertEqual(s, 400)

    def test_idea_card_endpoint_serves_a_png(self):
        s, _, raw = self.call("POST", "/api/convert", {"text": TEXT, "title": "Demo", "formats": ["epub"]}, self.JSON)
        res = json.loads(raw)
        if not res["boxes"]:
            self.skipTest("el texto de prueba no produjo cajitas")
        s, ct, data = self.call("GET", f"/files/{res['job']}/card-0.png")
        self.assertEqual(s, 200)
        self.assertEqual(ct, "image/png")
        self.assertEqual(data[:4], b"\x89PNG")
        s, _, _ = self.call("GET", f"/files/{res['job']}/card-99.png")
        self.assertEqual(s, 404)

    def test_shelf_lists_converted_books_newest_first(self):
        ids = []
        for title in ("Shelf One", "Shelf Two"):
            s, _, raw = self.call("POST", "/api/convert", {"text": TEXT, "title": title, "formats": ["epub"]}, self.JSON)
            self.assertEqual(s, 200)
            ids.append(json.loads(raw)["job"])
        s, ct, raw = self.call("GET", "/api/shelf")
        self.assertEqual(s, 200)
        self.assertIn("json", ct)
        books = json.loads(raw)["books"]
        self.assertEqual([b["job"] for b in books[:2]], ids[::-1])
        first = books[0]
        self.assertEqual(first["title"], "Shelf Two")
        self.assertIn("epub", first["files"])
        s, ct, data = self.call("GET", first["cover"])
        self.assertEqual((s, ct, data[:2]), (200, "image/jpeg", b"\xff\xd8"))

    def test_shelf_respects_the_host_check(self):
        s, _, _ = self.call("GET", "/api/shelf", host="evil.example")
        self.assertEqual(s, 403)

    def test_path_traversal_is_blocked(self):
        for p in ("/files/../../etc/hosts", "/files/..%2F..%2Fetc%2Fhosts", "/files/abc/../../x"):
            s, _, _ = self.call("GET", p)
            self.assertIn(s, (400, 403, 404), p)

    def test_jobs_stay_inside_jobs_dir(self):
        s, _, raw = self.call("POST", "/api/convert", {"text": TEXT, "formats": ["epub"]}, self.JSON)
        self.assertEqual(s, 200)
        for path in json.loads(raw)["files"].values():
            self.assertTrue(path.startswith("/files/"))
        self.assertTrue(any(Path(self.tmp.name).iterdir()))


if __name__ == "__main__":
    unittest.main()
