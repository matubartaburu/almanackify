"""Prueba de extremo a extremo de la interfaz web con Chrome headless (protocolo DevTools).

Requisitos: Chrome instalado, `pip install -r requirements-dev.txt`, servidor corriendo:
    python -m almanackify.server --no-open &
    python scripts/e2e_ui.py [--url http://127.0.0.1:8742] [--shot salida.png]
Hace clic en un ejemplo, convierte de verdad (necesita internet) y verifica resultado y descarga.
"""
import argparse, json, subprocess, sys, tempfile, time, urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8742")
    ap.add_argument("--shot", default="")
    ap.add_argument("--timeout", type=int, default=120)
    a = ap.parse_args()
    prof = tempfile.mkdtemp()
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--remote-debugging-port=9333", f"--user-data-dir={prof}",
                             "--window-size=1280,1300", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9333/json"))
                break
            except Exception:
                time.sleep(0.5)
        page = Page(next(t for t in tabs if t["type"] == "page")["webSocketDebuggerUrl"])
        page.cdp("Page.enable")
        page.cdp("Page.navigate", url=a.url)
        time.sleep(2)
        checks = {}
        checks["drop zone hidden on Link tab"] = page.js("document.getElementById('in-file').offsetParent === null")
        checks["tool visible (live mode)"] = page.js("document.getElementById('tool').style.display !== 'none'")
        page.js("document.querySelector('.chip').click()")
        checks["example chip fills the link"] = page.js("document.getElementById('in-link').value.startsWith('https://')")
        page.js("document.getElementById('f-pdf').click(); document.getElementById('form').requestSubmit()")
        t0, done, err = time.time(), False, ""
        while time.time() - t0 < a.timeout:
            done = page.js("document.getElementById('result').classList.contains('on')")
            err = page.js("document.getElementById('err').textContent")
            if done or err:
                break
            time.sleep(1)
        checks["result shown"] = bool(done)
        if err:
            print("UI error:", err)
        if done:
            checks["title"] = page.js("document.getElementById('r-title').textContent")
            checks["meta"] = page.js("document.getElementById('r-meta').textContent")
            checks["idea boxes shown"] = page.js("document.querySelectorAll('.idea').length")
            checks["cover loaded"] = page.js("document.getElementById('cover').naturalWidth > 500")
            links = page.js("[...document.querySelectorAll('#r-actions a')].map(a => a.href)")
            checks["download links"] = len(links or [])
            for href in links or []:
                data = urllib.request.urlopen(href).read()
                checks[f"download {href.rsplit('.', 1)[-1]}"] = data[:2] == b"PK" if href.endswith("epub") else data[:4] == b"%PDF"
            time.sleep(1)
            if a.shot:
                import base64
                open(a.shot, "wb").write(base64.b64decode(page.cdp("Page.captureScreenshot", format="png")["data"]))
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
