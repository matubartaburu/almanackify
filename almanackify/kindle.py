"""Envío del EPUB al Kindle por correo (Send to Kindle por email).

Las credenciales salen del entorno, nunca del repo:
    ALMANACKIFY_SMTP_HOST, ALMANACKIFY_SMTP_USER, ALMANACKIFY_SMTP_PASSWORD
    (opcionales) ALMANACKIFY_SMTP_PORT (465 por defecto), ALMANACKIFY_FROM
Solo se aceptan direcciones @kindle.com para que la herramienta no sirva de relé de correo a terceros.
"""
from __future__ import annotations

import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

KINDLE_RE = re.compile(r"^[A-Za-z0-9._%+-]+@(?:free\.)?kindle\.com$", re.I)


def smtp_config(env=None) -> dict | None:
    e = os.environ if env is None else env
    host, user, pw = e.get("ALMANACKIFY_SMTP_HOST"), e.get("ALMANACKIFY_SMTP_USER"), e.get("ALMANACKIFY_SMTP_PASSWORD")
    if not (host and user and pw):
        return None
    return {"host": host, "port": int(e.get("ALMANACKIFY_SMTP_PORT", "465")), "user": user, "password": pw,
            "from": e.get("ALMANACKIFY_FROM") or user}


def valid_kindle_address(addr: str) -> bool:
    return bool(KINDLE_RE.match((addr or "").strip()))


def send_epub(path: str, to: str, cfg: dict) -> None:
    to = (to or "").strip()
    if not valid_kindle_address(to):
        raise ValueError("That doesn't look like a Kindle address (it should end in @kindle.com).")
    p = Path(path)
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg["from"], to, p.stem
    msg.set_content("Sent with Almanackify.")
    msg.add_attachment(p.read_bytes(), maintype="application", subtype="epub+zip", filename=p.name)
    ctx = ssl.create_default_context()
    if cfg["port"] == 465:
        with smtplib.SMTP_SSL(cfg["host"], 465, context=ctx, timeout=30) as s:
            s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as s:
            s.starttls(context=ctx)
            s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
