"""Scripts of the TV pages run on old TV browsers (card « TV Samsung : ni
QR code ni code », 31 Oct 2026): the Samsung Tizen browser rejected the
whole page script because of one nullish operator, leaving « ······ » and no
QR code. Syntax of 2017 only (esprima parses ES2017), and no feature of the
later years esprima would let through."""
import re
from html.parser import HTMLParser

import esprima
import pytest

from sarcade.api import tv

# Accepted by esprima but newer than Chromium 56 (Tizen 4, 2018 TVs).
FORBIDDEN = {
    "object spread": re.compile(r"\{\s*\.\.\."),
    "padStart/padEnd": re.compile(r"\.pad(Start|End)\("),
    "replaceAll": re.compile(r"\.replaceAll\("),
    "Object.fromEntries": re.compile(r"Object\.fromEntries\("),
    "flat/flatMap": re.compile(r"\.flat(Map)?\("),
    "catch without binding": re.compile(r"catch\s*\{"),
}


class _Scripts(HTMLParser):
    """Inline scripts of a page (those without src)."""

    def __init__(self):
        super().__init__()
        self.scripts: list[str] = []
        self._in = False

    def handle_starttag(self, tag, attrs):
        if tag == "script" and not dict(attrs).get("src"):
            self._in = True
            self.scripts.append("")

    def handle_endtag(self, tag):
        if tag == "script":
            self._in = False

    def handle_data(self, data):
        if self._in:
            self.scripts[-1] += data


def inline_scripts(page: str) -> list[str]:
    parser = _Scripts()
    parser.feed(page)
    return [js for js in parser.scripts if js.strip()]


@pytest.mark.parametrize("name", ["_TV", "_APPROVE"])
def test_tv_scripts_parse_as_es2017(name):
    page = getattr(tv, name)
    scripts = inline_scripts(page)
    assert scripts
    for js in scripts:
        esprima.parseScript(js)  # raises on ?? or ?. and later syntax
        for what, pattern in FORBIDDEN.items():
            assert not pattern.search(js), f"{name}: {what} not supported by old TV browsers"


def test_esprima_rejects_the_operators_that_broke_the_tv():
    for js in ("var x=a??b;", "var y=a?.b;"):
        with pytest.raises(esprima.Error):
            esprima.parseScript(js)


def test_silent_screen_replaced_by_a_message():
    assert "window.sarcadeStarted=true" in tv._TV
    assert "pas pu lancer SARCADE" in tv._TV


def test_libraries_served_by_sarcade_not_by_a_cdn():
    from fastapi.testclient import TestClient

    from sarcade.api.app import app

    for page in (tv._TV, tv._APPROVE):
        assert "unpkg.com" not in page and "cdnjs" not in page
    client = TestClient(app)
    for name, kind in (("qrcode.min.js", "javascript"), ("leaflet.js", "javascript"), ("leaflet.css", "css"),
                       ("images/marker-icon.png", "image/png")):
        r = client.get(f"/tv/static/{name}")
        assert r.status_code == 200 and kind in r.headers["content-type"], name
    assert client.get("/tv/static/../tv.py").status_code == 404
    assert client.get("/tv/static/qrcodejs-LICENSE").status_code == 404
