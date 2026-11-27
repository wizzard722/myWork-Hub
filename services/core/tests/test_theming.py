import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from core.main import app
from core.theming import ColorPalette, Theme, render_css

client = TestClient(app)


def test_health():
    assert client.get("/health").json()["service"] == "core"


def test_theme_json():
    data = client.get("/theme").json()
    assert data["light"]["primary"].startswith("#")
    assert "dark" in data


def test_theme_css():
    response = client.get("/theme/theme.css")
    assert response.headers["content-type"].startswith("text/css")
    assert "--mw-color-primary:" in response.text
    assert ':root[data-theme="dark"]' in response.text


@pytest.mark.parametrize("bad", ["red", "#12", "#fff;}body{display:none", "url(x)"])
def test_colors_must_be_hex(bad):
    with pytest.raises(ValidationError):
        ColorPalette(primary=bad)


def test_font_family_cannot_inject_css():
    with pytest.raises(ValidationError):
        Theme(font_family="Arial; } body { display:none")


def test_render_custom_theme():
    css = render_css(Theme(radius="4px", light=ColorPalette(primary="#ff0000")))
    assert "--mw-color-primary: #ff0000;" in css
    assert "--mw-radius: 4px;" in css
