"""Interfaz web local de Almanackify.

    python -m almanackify.server            ->  http://127.0.0.1:8742

Solo escucha en 127.0.0.1. Acepta un link http(s), texto pegado o un archivo subido; nunca rutas locales.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import core, extract, render

WEB_DIR = Path(__file__).parent / "web"
DEFAULT_JOBS = Path("~/.almanackify/web").expanduser()  # fuera del repo y de la carpeta de salida visible
MAX_BODY = 2 * 1024 * 1024  # JSON / texto pegado
MAX_UPLOAD = 60 * 1024 * 1024
UPLOAD_EXT = {".epub", ".pdf", ".txt", ".md", ".srt", ".vtt"}
FORMATS = ("epub", "pdf")
MIME = {".epub": "application/epub+zip", ".pdf": "application/pdf", ".json": "application/json", ".jpg": "image/jpeg"}
JOB_RE = re.compile(r"^[0-9a-f]{12}$")
NAME_RE = re.compile(r"^[\w.\-]+$", re.U)


class Handler(BaseHTTPRequestHandler):
    server_version = "Almanackify"

    def log_message(self, *args):  # silencio: la salida es del usuario, no del servidor
        pass

    # ---- utilidades ----------------------------------------------------
    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj: dict):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf8"), "application/json; charset=utf-8")

    def _error(self, status: int, msg: str):
        self._json(status, {"error": msg})

    def _host_ok(self) -> bool:
        port = self.server.server_address[1]
        return self.headers.get("Host", "").lower() in {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

    def _read_body(self, limit: int) -> bytes | None:
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = -1
        if n < 0 or n > limit:
            return None
        return self.rfile.read(n) if n else b""

    # ---- GET -----------------------------------------------------------
    def do_GET(self):
        if not self._host_ok():
            return self._error(403, "Host no permitido")
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if path in ("/", "/index.html"):
            return self._send(200, (WEB_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/health":
            return self._json(200, {"ok": True})
        if path == "/api/shelf":
            return self._json(200, {"books": self._shelf()})
        m = re.fullmatch(r"/fonts/(EBGaramond-(?:Regular|Bold|Italic|BoldItalic)\.ttf)", path)
        if m and (render.STATIC_FONT_DIR / m.group(1)).is_file():
            return self._send(200, (render.STATIC_FONT_DIR / m.group(1)).read_bytes(), "font/ttf")
        m = re.fullmatch(r"/files/([0-9a-f]{12})/card-(\d{1,2})\.png", path)
        if m:
            card = self._card(self.server.jobs_dir / m.group(1), int(m.group(2)))
            if card:
                return self._send(200, card, "image/png", {"Content-Disposition": f'attachment; filename="idea-{int(m.group(2)) + 1}.png"'})
            return self._error(404, "No encontrado")
        m = re.fullmatch(r"/files/([^/]+)/([^/]+)", path)
        if m and JOB_RE.match(m.group(1)) and NAME_RE.match(m.group(2)):
            f = self.server.jobs_dir / m.group(1) / m.group(2)
            if f.is_file():
                ctype = MIME.get(f.suffix.lower(), "application/octet-stream")
                return self._send(200, f.read_bytes(), ctype, {"Content-Disposition": f'attachment; filename="{f.name}"'})
        return self._error(404, "No encontrado")

    def _shelf(self, limit: int = 6) -> list[dict]:
        """Los últimos libros convertidos (el más nuevo primero), con portada, cajitas y archivos."""
        found = []
        for d in self.server.jobs_dir.iterdir():
            js = sorted(d.glob("*.json")) if d.is_dir() and JOB_RE.match(d.name) else []
            if js:
                found.append((js[0].stat().st_mtime, d, js[0]))
        books = []
        for _, d, jp in sorted(found, key=lambda t: t[0], reverse=True)[:limit]:
            try:
                book = json.loads(jp.read_text(encoding="utf8"))
                if not (d / "cover.jpg").is_file():  # los trabajos solo-PDF no tienen portada: se genera una vez
                    (d / "cover.jpg").write_bytes(render.make_cover(book))
            except Exception:  # noqa: BLE001 - un trabajo dañado no rompe la repisa
                continue
            boxes = [b["text"] for c in book["chapters"] for b in c["blocks"] if b["type"] == "tweet"]
            files = {p.suffix[1:]: f"/files/{d.name}/{p.name}" for p in sorted(d.iterdir()) if p.suffix in (".epub", ".pdf")}
            books.append({"job": d.name, "title": book.get("title", ""), "author": book.get("author", ""), "lang": book.get("lang", ""),
                          "stats": book.get("stats", {}), "cover": f"/files/{d.name}/cover.jpg", "boxes": boxes[:6], "files": files})
        return books

    def _card(self, job_dir: Path, i: int) -> bytes | None:
        """PNG de la i-ésima cajita del libro de ese trabajo (se genera una vez y queda en caché)."""
        out = job_dir / f"card-{i}.png"
        if out.is_file():
            return out.read_bytes()
        js = sorted(job_dir.glob("*.json"))
        if not js:
            return None
        book = json.loads(js[0].read_text(encoding="utf8"))
        boxes = [b["text"] for c in book["chapters"] for b in c["blocks"] if b["type"] == "tweet"]
        if i >= len(boxes):
            return None
        png = render.make_card(boxes[i], book.get("title", ""), book.get("author", ""))
        out.write_bytes(png)
        return png

    # ---- POST ----------------------------------------------------------
    def do_POST(self):
        if not self._host_ok():
            return self._error(403, "Host no permitido")
        if self.headers.get("X-Almanackify") != "1":  # fuerza preflight CORS: otras páginas no pueden llamar a esta API
            return self._error(403, "Falta la cabecera X-Almanackify")
        url = urllib.parse.urlsplit(self.path)
        try:
            if url.path == "/api/convert":
                return self._convert_json()
            if url.path == "/api/convert-file":
                return self._convert_file(urllib.parse.parse_qs(url.query))
        except ValueError as e:
            return self._error(400, str(e))
        except Exception as e:  # noqa: BLE001 - no filtrar trazas al navegador
            return self._error(500, f"No pude convertirlo ({type(e).__name__}).")
        return self._error(404, "No encontrado")

    def _formats(self, raw) -> tuple:
        fm = tuple(f for f in (raw or FORMATS) if f in FORMATS)
        if not fm:
            raise ValueError("Elegí EPUB, PDF o ambos.")
        return fm

    def _options(self, o: dict) -> dict:
        try:
            every = int(o.get("every", 220))
        except (TypeError, ValueError):
            every = 220
        return {"box_every_words": max(80, min(600, every)), "chain": bool(o.get("chain", True))}

    def _convert_json(self):
        raw = self._read_body(MAX_BODY)
        if raw is None:
            return self._error(413, "El texto es demasiado grande.")
        try:
            o = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return self._error(400, "JSON inválido.")
        if not isinstance(o, dict):
            return self._error(400, "JSON inválido.")
        source, text = str(o.get("source") or "").strip(), str(o.get("text") or "").strip()
        title, author = str(o.get("title") or "").strip()[:200], str(o.get("author") or "").strip()[:200]
        if source:
            if not re.fullmatch(r"https?://\S+", source):
                raise ValueError("Pegá un link que empiece con http:// o https://.")
            book = extract.load(source, title=title or None, author=author or None)
        elif text:
            if len(text.split()) < 20:
                raise ValueError("Pegá un texto más largo (mínimo ~20 palabras).")
            book = extract.from_text(text, title=title or "Text")
            book["lang"] = book.get("lang") or extract.detect_lang(text)
            if author:
                book["author"] = author
        else:
            raise ValueError("Pegá un link o un texto.")
        self._finish(book, self._formats(o.get("formats")), self._options(o))

    def _convert_file(self, query: dict):
        n = int(self.headers.get("Content-Length", "0") or 0)
        name = Path(urllib.parse.unquote(self.headers.get("X-Filename", ""))).name
        if Path(name).suffix.lower() not in UPLOAD_EXT:
            raise ValueError("Formato no soportado. Subí .epub, .pdf, .txt, .md, .srt o .vtt.")
        if n > MAX_UPLOAD:
            return self._error(413, "El archivo es demasiado grande (máx. 60 MB).")
        data = self._read_body(MAX_UPLOAD)
        if not data:
            raise ValueError("El archivo está vacío.")
        job = uuid.uuid4().hex[:12]
        up = self.server.jobs_dir / job / "upload"
        up.mkdir(parents=True)
        safe = re.sub(r"[^\w.\-]", "_", name)
        (up / safe).write_bytes(data)
        book = extract.load(str(up / safe))
        fm = self._formats((query.get("formats") or [""])[0].split(",") if query.get("formats") else None)
        opts = self._options({"every": (query.get("every") or ["220"])[0], "chain": (query.get("chain") or ["1"])[0] != "0"})
        self._finish(book, fm, opts, job=job)

    def _finish(self, book: dict, formats: tuple, opts: dict, job: str | None = None):
        job = job or uuid.uuid4().hex[:12]
        out = self.server.jobs_dir / job
        out.mkdir(parents=True, exist_ok=True)
        res = core.build_book(book, str(out), formats, **opts)
        processed = json.loads(Path(res["files"]["json"]).read_text(encoding="utf8"))
        boxes = [b["text"] for c in processed["chapters"] for b in c["blocks"] if b["type"] == "tweet"]
        files = {k: f"/files/{job}/{Path(v).name}" for k, v in res["files"].items() if k in formats}
        if "epub" in res["files"]:  # la portada del EPUB, para mostrarla en el resultado
            with zipfile.ZipFile(res["files"]["epub"]) as z:
                (out / "cover.jpg").write_bytes(z.read("EPUB/images/cover.jpg"))
            files["cover"] = f"/files/{job}/cover.jpg"
        self._json(200, {"job": job, "title": res["title"], "author": book.get("author", ""), "lang": res["lang"], "stats": res["stats"],
                         "files": files, "boxes": boxes[:8]})


def make_server(host: str = "127.0.0.1", port: int = 8742, jobs_dir=None) -> ThreadingHTTPServer:
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Por seguridad el servidor solo escucha en localhost.")
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.jobs_dir = Path(jobs_dir).expanduser() if jobs_dir else DEFAULT_JOBS
    srv.jobs_dir.mkdir(parents=True, exist_ok=True)
    return srv


def main():
    ap = argparse.ArgumentParser(prog="almanackify.server", description="Interfaz web local de Almanackify.")
    ap.add_argument("--port", type=int, default=8742)
    ap.add_argument("--no-open", action="store_true", help="no abrir el navegador")
    a = ap.parse_args()
    srv = make_server(port=a.port)
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    print(f"Almanackify en {url}  (Ctrl+C para salir)")
    if not a.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
