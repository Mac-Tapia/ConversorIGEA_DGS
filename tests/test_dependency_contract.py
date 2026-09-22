from pathlib import Path


def test_dependency_groups_are_declared_and_powerfactory_is_not_pypi():
    root = Path(__file__).parents[1]
    runtime = (root / "requirements.txt").read_text(encoding="utf-8")
    export = (root / "requirements-export.txt").read_text(encoding="utf-8")
    dev = (root / "requirements-dev.txt").read_text(encoding="utf-8")
    pf = (root / "requirements-powerfactory.txt").read_text(encoding="utf-8")

    assert "pyproj" in runtime
    assert all(
        name in export
        for name in ("pandas", "openpyxl", "geopandas", "shapely", "leafmap")
    )
    assert all(
        name in dev
        for name in (
            "pytest",
            "pytest-cov",
            "hypothesis",
            "ruff",
            "mypy",
            "bandit",
            "pip-audit",
        )
    )
    assert "powerfactory==" not in pf.lower()
