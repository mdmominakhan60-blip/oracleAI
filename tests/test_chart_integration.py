import pytest

from conftest import TEST_DEV_KEY  # noqa: E402

from app.core import chart_rendering
from app.core.chart_rendering import EngineRenderError


@pytest.fixture
async def client(db, user):
    pytest.importorskip("httpx")
    from httpx import ASGITransport, AsyncClient
    from app.api.deps import get_db
    from app.api.main import app
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                      headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.clear()


def _spec():
    return chart_rendering.build_render_spec(variant="compact", image_format="png", locale="ru")


def _chart():
    return {
        "precision": "exact",
        "natal_schema_version": 2,
        "calculation": {
            "contract_version": 2,
            "configuration_fingerprint": "config-a",
            "request_fingerprint": "request-a",
            "input": {"birth_date": "1990-06-21", "birth_time": "14:30", "tz": "Europe/Moscow"},
            "config": {
                "zodiac_type": "Tropical",
                "house_system": "P",
                "perspective_type": "Apparent Geocentric",
                "active_points": ["Sun", "Moon"],
            },
        },
    }


def test_render_cache_key_changes_when_calculation_fingerprint_changes():
    chart = _chart()
    kwargs = dict(birth_date="1990-06-21", birth_time="14:30", lat=55.79, lon=49.12,
                  tz="Europe/Moscow", spec=_spec())
    first = chart_rendering.cache_key(chart, **kwargs)
    changed = _chart()
    changed["calculation"]["request_fingerprint"] = "request-b"
    assert first != chart_rendering.cache_key(changed, **kwargs)


def test_renderer_rejects_stale_calculation_configuration():
    chart = _chart()
    chart["calculation"]["config"]["house_system"] = "W"
    with pytest.raises(EngineRenderError, match="stale"):
        chart_rendering._subject_from_chart(
            chart, birth_date="1990-06-21", birth_time="14:30",
            lat=55.79, lon=49.12, tz="Europe/Moscow",
        )


@pytest.mark.asyncio
async def test_chart_image_route_prefers_immutable_snapshot_input(client, user, db, monkeypatch):
    from app.core import astro
    from app.repo import users
    import json

    chart = await astro.compute_chart_async(
        "1990-06-21", "14:30", "Казань", 55.79, 49.12, "Europe/Moscow", time_known=True,
    )
    await users.update(
        db, user["tg_id"], chart_json=json.dumps(chart, ensure_ascii=False),
        birth_date="2000-01-01", birth_time="00:01", birth_lat=-33.0, birth_lon=151.0,
        tz="Australia/Sydney",
    )
    captured = {}

    def fake_render(chart, **kwargs):
        captured.update(kwargs)
        return b"PNG", _spec(), False, "etag-test"

    monkeypatch.setattr(chart_rendering, "render_chart_image", fake_render)
    response = await client.get("/api/chart/image", params={"dev_user": user["tg_id"]})
    assert response.status_code == 200
    assert captured["birth_date"] == "1990-06-21"
    assert captured["birth_time"] == "14:30"
    assert captured["lat"] == 55.79
    assert captured["lon"] == 49.12
    assert captured["tz"] == "Europe/Moscow"
