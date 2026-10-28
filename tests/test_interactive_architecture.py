from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DSL = ROOT / "docs" / "architecture" / "workspace.dsl"
HTML = ROOT / "docs" / "architecture" / "arquitectura-interactiva-c4.html"
BUILDER = ROOT / "tools" / "build_interactive_architecture.py"


def test_structurizr_model_exposes_required_views_and_real_access_points():
    text = DSL.read_text(encoding="utf-8")

    for key in (
        "SystemContext",
        "Containers",
        "Conversion",
        "PowerFactory",
        "Inteligencia",
        "Deployment",
    ):
        assert f'"{key}"' in text

    for access_point in (
        "http://127.0.0.1:8765/",
        "src/igea_dgs/web/app.py",
        "src/igea_dgs/web/services.py",
        "src/igea_dgs/digital_twin",
        "src/igea_dgs/asistente",
        "output/web",
    ):
        assert access_point in text
    assert 'nativeRunner -> oracle "Solicita preflight informativo"' in text
    assert 'oracle -> nativeRunner "Devuelve avisos; la importacion continua"' in text
    assert "engine -> oracle" not in text
    assert "oracle -> dgs" not in text
    assert "/tree/main/" not in text
    assert "/blob/main/" not in text
    assert "file:///D:/converter/ConversorIGEA_DGS/src/igea_dgs/digital_twin" in text


def test_interactive_visualization_has_finite_flow_controls_and_accessible_nodes():
    text = HTML.read_text(encoding="utf-8")

    assert '<div id="igea-c4-flow"' in text
    assert "prefers-reduced-motion" in text
    assert 'id="flow-play"' in text
    assert 'id="flow-next"' in text
    assert 'id="flow-reset"' in text
    assert 'id="flow-speed"' in text
    assert 'aria-live="polite"' in text
    assert 'role="img"' in text
    assert 'role="tabpanel"' in text
    assert 'aria-controls="c4-stage"' in text
    assert "ArrowRight" in text
    assert "playFlow" in text
    assert "advanceFlow" in text
    assert "setView" in text
    assert "animationiteration" not in text.lower()
    assert "infinite" not in text.lower()
    assert "progress < 1 && playing" not in text
    assert "progress < 1 && activePath === path" in text
    assert "svgEl('textPath'" not in text
    assert "[hidden]" in text
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in text
    assert "${common[edge.from].label} -> ${common[edge.to].label}" in text
    assert "tools/verificar_pf.py" not in text
    assert "new URL(`../../${access}`" in text

    node_ids = set(re.findall(r'data-node-id="([^"]+)"', text))
    assert {"sources", "frontend", "api", "engine", "powerfactory", "twin", "assistant", "deliverables"} <= node_ids


def test_visualization_contains_every_required_flow_and_direct_destination():
    text = HTML.read_text(encoding="utf-8")

    for view in ("context", "containers", "conversion", "powerfactory", "intelligence", "deployment"):
        assert f'data-view="{view}"' in text

    for destination in (
        "src/igea_dgs/sources",
        "src/igea_dgs/dgs.py",
        "src/igea_dgs/web/app.py",
        "tools/powerfactory_acceptance.py",
        "src/igea_dgs/digital_twin/oraculo.py",
        "src/igea_dgs/asistente/interprete.py",
        "docs/architecture/plano_flujo_arquitectura_conversor_igea_dgs.pdf",
    ):
        assert destination in text


def test_visualization_exposes_scientific_basis_and_standalone_delivery():
    text = HTML.read_text(encoding="utf-8")

    for source in (
        "https://doi.org/10.1016/j.jss.2014.03.071",
        "https://doi.org/10.1109/TPWRS.2018.2829021",
        "https://doi.org/10.1016/j.epsr.2020.106664",
        "https://redi.cedia.edu.ec/document/42803",
        "https://etheses.whiterose.ac.uk/id/eprint/30114/",
    ):
        assert source in text

def test_tracked_source_builds_standalone_delivery_in_clean_directory(tmp_path):
    assert (ROOT / "docs" / "architecture" / "plano_flujo_arquitectura_conversor_igea_dgs.pdf").is_file()
    subprocess.run(
        [sys.executable, str(BUILDER), "--output-dir", str(tmp_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    standalone = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<!doctype html>" in standalone.lower()
    assert 'id="igea-c4-flow"' in standalone
    assert "<iframe" not in standalone
    assert "tools/powerfactory_acceptance.py" in standalone
