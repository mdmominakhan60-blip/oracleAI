"""BUS-321: SEO-остатки BUS-130 — дубли /public/*.html и og:image под Disallow: /static.

P1: маунт /public отдаёт только ассеты (CSS), HTML-файлы → 404: канонические
страницы живут на /landing, /privacy, /terms (+EN) через _public_template.
P2: robots.txt разрешает краулерам соцсетей fetch og:image/favicon из /static/img/.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db
from app.api.main import app


@pytest.fixture
async def client(db):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


async def test_public_html_duplicates_return_404(client):
    """P1: *.html под /public → 404, дублей канонических страниц не существует."""
    for path in ("/public/landing.html", "/public/landing-en.html",
                 "/public/privacy.html", "/public/privacy-en.html",
                 "/public/terms.html", "/public/terms-en.html"):
        res = await client.get(path)
        assert res.status_code == 404, f"{path} → {res.status_code}"


async def test_public_css_still_served(client):
    """P1 не должен ломать stylesheet privacy/terms: /public/landing.css → 200."""
    res = await client.get("/public/landing.css")
    assert res.status_code == 200
    assert "text/css" in res.headers["content-type"]


async def test_public_nonexistent_asset_404(client):
    res = await client.get("/public/nope.css")
    assert res.status_code == 404


async def test_robots_txt_allows_static_img_for_og_image(client):
    """P2: Allow: /static/img/ стоит перед Disallow: /static → og:image/favicon fetchабельны."""
    res = await client.get("/robots.txt")
    assert res.status_code == 200
    lines = res.text.splitlines()
    allow_idx = lines.index("Allow: /static/img/")
    disallow_idx = lines.index("Disallow: /static")
    assert allow_idx < disallow_idx, "Allow: /static/img/ должен идти раньше Disallow: /static"


async def test_og_image_and_favicon_served(client):
    """DoD: og-card.jpg и oracle-mark.png отдаются обычным клиентом (200, image)."""
    for path in ("/static/img/og-card.jpg", "/static/img/oracle-mark.png"):
        res = await client.get(path)
        assert res.status_code == 200, f"{path} → {res.status_code}"
        assert res.headers["content-type"].startswith("image/"), \
            f"{path} → content-type {res.headers['content-type']}"


async def test_canonical_pages_unaffected(client):
    """Канонические маршруты продолжают отдавать HTML с заменённым плейсхолдером."""
    for path in ("/landing", "/privacy", "/terms"):
        res = await client.get(path)
        assert res.status_code == 200
        assert "__PUBLIC_BASE_URL__" not in res.text
