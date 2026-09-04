from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_specialized_placements_have_no_direct_kerykeion_path():
    source = (ROOT / "app/core/placements.py").read_text(encoding="utf-8")
    assert "AstrologicalSubjectFactory" not in source
    assert "from kerykeion" not in source
    assert "astro.compute_chart" in source


def test_only_canonical_adapter_and_render_layer_import_kerykeion():
    imports = []
    for path in (ROOT / "app").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "from kerykeion" in source or "import kerykeion" in source:
            imports.append(path.relative_to(ROOT).as_posix())
    assert set(imports) <= {"app/core/astro.py", "app/core/chart_rendering.py"}


def test_chart_render_layer_is_raster_only_at_public_boundary():
    source = (ROOT / "app/core/chart_rendering.py").read_text(encoding="utf-8")
    assert "_transient_svg" in source
    assert "_validate_transient_svg" in source
    assert "return result, spec, False, key" in source
    assert "caller can receive or cache the result" in source
