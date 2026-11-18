"""Prueba de extremo a extremo de la interfaz web con Chrome headless (protocolo DevTools).

Requisitos: Chrome instalado, `pip install -r requirements-dev.txt`, servidor corriendo:
    almanackify-server --no-open &
    python scripts/e2e_ui.py [--url http://127.0.0.1:8742] [--shots carpeta]
Convierte de verdad (necesita internet para el ejemplo de link) y verifica resultado, descargas,
el stepper, la zona de archivos (arrastre sin parpadeo, rechazo con motivo, conversión y reintento).
"""
import argparse, base64, json, os, subprocess, sys, tempfile, time, urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TEXT = ("Trust thyself: every heart vibrates to that iron string. Accept the place the divine providence has found for you. "
        "Whoso would be a man must be a nonconformist. Nothing is at last sacred but the integrity of your own mind.\n\n") * 8


class Page:
    def __init__(self, ws_url):
        self.ws, self.n = websocket.create_connection(ws_url, timeout=120), 0

    def cdp(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                return msg.get("result", {})

    def js(self, expr):
        r = self.cdp("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def set_file(self, path):
        root = self.cdp("DOM.getDocument")["root"]["nodeId"]
        nid = self.cdp("DOM.querySelector", nodeId=root, selector="#file")["nodeId"]
        self.cdp("DOM.setFileInputFiles", files=[path], nodeId=nid)

    def shot(self, path):
        open(path, "wb").write(base64.b64decode(self.cdp("Page.captureScreenshot", format="png")["data"]))

    def wait(self, expr, timeout=90, every=0.4):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.js(expr):
                return True
            time.sleep(every)
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8742")
    ap.add_argument("--shots", default="")
    ap.add_argument("--timeout", type=int, default=120)
    a = ap.parse_args()
    if a.shots:
        os.makedirs(a.shots, exist_ok=True)
    work = tempfile.mkdtemp()
    open(os.path.join(work, "essay.txt"), "w").write(TEXT)
    open(os.path.join(work, "evil.exe"), "wb").write(b"MZ" + b"\0" * 100)
    prof = tempfile.mkdtemp()
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--remote-debugging-port=9333", f"--user-data-dir={prof}",
                             "--window-size=1280,1300", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    checks = {}
    try:
        for _ in range(40):
            try:
                tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9333/json"))
                break
            except Exception:
                time.sleep(0.5)
        page = Page(next(t for t in tabs if t["type"] == "page")["webSocketDebuggerUrl"])
        for d in ("Page", "DOM"):
            page.cdp(f"{d}.enable")
        page.cdp("Page.navigate", url=a.url)
        time.sleep(0.8)
        if a.shots:
            page.shot(os.path.join(a.shots, "intro.png"))  # la animación de entrada a mitad de camino
        time.sleep(2.4)
        # la repisa 3D está desde el inicio, antes de convertir nada
        checks["shelf is on the page from the start"] = page.js("document.querySelectorAll('#shelf .b3').length") >= 2
        checks["intro animation finished: every book fully visible"] = page.js("[...document.querySelectorAll('#shelf .b3')].every(b => getComputedStyle(b).opacity === '1')")
        checks["shelf sits above the converter"] = page.js("document.getElementById('shelf').getBoundingClientRect().top < document.getElementById('tool').getBoundingClientRect().top")
        checks["no download panel while only sample books are active"] = page.js("(document.querySelector('#shelf .b3.active img').src || '').includes('/demo/') ? !document.getElementById('result').classList.contains('on') : true")
        if a.shots:
            page.shot(os.path.join(a.shots, "home.png"))

        # ---- modo link + stepper ----
        checks["file zone hidden on the Link tab"] = page.js("document.getElementById('in-file').offsetParent === null")
        checks["tool visible (engine running)"] = page.js("document.getElementById('tool').style.display !== 'none'")
        checks["stepper has 4 titled steps"] = page.js("document.querySelectorAll('#steps li .t').length") == 4
        page.js("document.querySelector('.chip').click()")
        checks["example chip fills the link"] = page.js("document.getElementById('in-link').value.startsWith('https://')")
        page.js("document.getElementById('f-pdf').click(); document.getElementById('form').requestSubmit()")
        shot_taken = False
        t0 = time.time()
        while time.time() - t0 < a.timeout:
            if page.js("document.getElementById('result').classList.contains('on')") or page.js("document.getElementById('err').textContent"):
                break
            if not shot_taken and page.js("document.querySelectorAll('#steps li.done').length >= 1"):
                checks["stepper shows a check on finished steps and a spinner on the current one"] = bool(
                    page.js("!!document.querySelector('#steps li.now .sp') && getComputedStyle(document.querySelector('#steps li.done .ck')).display === 'block'"))
                checks["stepper marks the current step for assistive tech"] = bool(page.js("!!document.querySelector('#steps li[aria-current=step]')"))
                if a.shots:
                    page.shot(os.path.join(a.shots, "stepper.png"))
                shot_taken = True
            time.sleep(0.3)
        checks["stepper was seen while converting"] = shot_taken
        done = page.js("document.getElementById('result').classList.contains('on')")
        err = page.js("document.getElementById('err').textContent")
        if err:
            print("UI error:", err)
        checks["result shown"] = bool(done)
        if done:
            checks["title"] = page.js("document.getElementById('r-title').textContent")
            checks["meta"] = page.js("document.getElementById('r-meta').textContent")
            checks["idea boxes shown"] = page.js("document.querySelectorAll('.idea').length")
            checks["cover loaded"] = page.js("document.getElementById('cover').naturalWidth > 500")
            links = page.js("[...document.querySelectorAll('#r-actions a')].map(a => a.href)") or []
            checks["download links"] = len(links)
            for href in links:
                data = urllib.request.urlopen(href).read()
                checks[f"download {href.rsplit('.', 1)[-1]}"] = data[:2] == b"PK" if href.endswith("epub") else data[:4] == b"%PDF"
            card = page.js("document.querySelector('.idea .save').href")
            checks["idea card is a PNG"] = urllib.request.urlopen(card).read()[:4] == b"\x89PNG"
            # repisa 3D: libros, abrir/cerrar y navegar con el teclado
            checks["shelf renders at least one book"] = page.js("document.querySelectorAll('#shelf .b3').length") >= 1
            checks["active book is the newest and faces front"] = page.js("document.querySelector('#shelf .b3.active img').id === 'cover'")
            page.js("document.getElementById('shelf').scrollIntoView({block: 'center'})")
            time.sleep(1.2)
            if a.shots:
                page.shot(os.path.join(a.shots, "shelf.png"))
            page.js("document.querySelector('#shelf .b3.active').click()")
            time.sleep(1.8)
            checks["clicking the active book opens it"] = page.js("document.querySelector('#shelf .b3.active').classList.contains('open')")
            checks["open book shows real idea boxes on its page"] = page.js("document.querySelectorAll('#shelf .b3.active .pg .bx').length") >= 1
            if a.shots:
                page.shot(os.path.join(a.shots, "shelf-open.png"))
            page.js("document.querySelector('#shelf .b3.active').click()")
            time.sleep(0.8)
            checks["clicking again closes it"] = not page.js("document.querySelector('#shelf .b3.active').classList.contains('open')")
            if page.js("document.querySelectorAll('#shelf .b3').length") > 1:
                page.js("document.getElementById('shelf').dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true}))")
                time.sleep(0.9)
                checks["arrow key moves to the next book"] = page.js("[...document.querySelectorAll('#shelf .b3')].findIndex(b => b.classList.contains('active'))") == 1
                if a.shots:
                    page.shot(os.path.join(a.shots, "shelf-next.png"))
            if a.shots:
                page.shot(os.path.join(a.shots, "result.png"))

        # ---- modo archivo ----
        page.js("window.scrollTo(0, 0); document.getElementById('t-file').click()")
        time.sleep(0.4)
        checks["file zone visible on the File tab"] = page.js("document.getElementById('in-file').offsetParent !== null")
        checks["Convert disabled with no file"] = page.js("document.getElementById('go').disabled")
        # el arrastre no parpadea al cruzar un hijo (contador de profundidad)
        page.js("""(() => { const d = document.getElementById('drop'), t = d.querySelector('.drop-t'),
            ev = (n, el) => el.dispatchEvent(new Event(n, {bubbles: true, cancelable: true}));
            ev('dragenter', d); ev('dragenter', t); ev('dragleave', t); window.__still = d.classList.contains('over'); ev('dragleave', d); window.__gone = !d.classList.contains('over'); })()""")
        checks["drag state survives crossing a child element"] = page.js("window.__still")
        checks["drag state clears when the pointer really leaves"] = page.js("window.__gone")
        # un archivo rechazado tiene su fila, con el motivo, y no se puede convertir
        page.set_file(os.path.join(work, "evil.exe"))
        time.sleep(0.4)
        checks["rejected file keeps a row"] = page.js("!!document.querySelector('.frow.bad')")
        checks["rejection names the reason"] = "aren't accepted" in (page.js("document.querySelector('.frow .fstat').textContent") or "")
        checks["Convert stays disabled for a rejected file"] = page.js("document.getElementById('go').disabled")
        if a.shots:
            page.shot(os.path.join(a.shots, "file-rejected.png"))
        page.js("document.querySelector('.frow .fbtn[aria-label^=Remove]').click()")
        checks["remove clears the row"] = page.js("document.querySelectorAll('.frow').length") == 0
        # un archivo válido: lista, convierte, termina
        page.set_file(os.path.join(work, "essay.txt"))
        time.sleep(0.4)
        checks["valid file shows Ready"] = "Ready" in (page.js("document.querySelector('.frow .fstat').textContent") or "")
        checks["Convert enabled for a valid file"] = page.js("!document.getElementById('go').disabled")
        if a.shots:
            page.shot(os.path.join(a.shots, "file-ready.png"))
        page.js("document.getElementById('form').requestSubmit()")
        checks["file row finishes as Done"] = page.wait("(document.querySelector('.frow .fstat')||{}).textContent && document.querySelector('.frow .fstat').textContent.includes('idea box')", 60)
        if a.shots:
            page.shot(os.path.join(a.shots, "file-done.png"))

        ok = True
        for k, v in checks.items():
            good = v not in (False, None, 0, "")
            ok &= good
            print(("PASS" if good else "FAIL"), k, "->", v)
        sys.exit(0 if ok else 1)
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
