"""WEB-RUTAS (decisión de c3 sobre la matriz web, 15-11-2026): dos rutas de la API que no tenían pantalla la tienen.

- 007:RF-38: deshacer un lote de cargas ya aplicado (POST lote/{token}/deshacer), con confirmación y su resumen, en la
  pestaña «Cargas en DIgSILENT»;
- 026:RF-28: la decisión humana sobre las mejoras que propone el asistente (POST asistente/mejoras/{id}/decision), en el
  panel del equipo del asistente.
Como test_cargas_pf_front.py, el front no se ejecuta: se comprueba su fuente y que cada ruta que llama exista en la API.
La revisión en un navegador real espera la autorización de Playwright por el usuario.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / 'frontend' / 'src'
APP = (RAIZ / 'src' / 'convertersmartgrid' / 'presentacion' / 'web' / 'app.py').read_text(encoding='utf-8')
CLIENTE = (SRC / 'api' / 'client.ts').read_text(encoding='utf-8')


def _rutas_api() -> set[tuple[str, str]]:
    return {(m.upper(), re.sub(r'\{[^}]+\}', '{}', r))
            for m, r in re.findall(r"@app\.(get|post|put|delete)\('([^']+)'", APP)}


def _leer(rel: str) -> str:
    ruta = SRC / rel
    assert ruta.is_file(), f'falta {rel}'
    return ruta.read_text(encoding='utf-8')


def test_el_cliente_llama_a_las_dos_rutas_y_existen_en_la_api():
    """WEB-RUTAS — cargasDeshacer y asistenteDecision en el cliente, con su método, y sus rutas en la API."""
    deshacer = re.search(r"cargasDeshacer:[^\n]*\n\s*request<[^>]*>\(`\$\{ws\(id\)\}/lote/\$\{token\}/deshacer`,\s*\{ method: 'POST' \}",
                         CLIENTE)
    decision = re.search(r"asistenteDecision:[\s\S]{0,200}?`/api/asistente/mejoras/\$\{enc\(propuestaId\)\}/decision`,"
                         r"\s*json\('POST'", CLIENTE)
    assert deshacer and decision, 'faltan cargasDeshacer o asistenteDecision en el cliente'
    rutas = _rutas_api()
    assert ('POST', '/api/workspaces/{}/lote/{}/deshacer') in rutas
    assert ('POST', '/api/asistente/mejoras/{}/decision') in rutas


def test_deshacer_un_lote_tiene_pantalla_con_confirmacion():
    """007:RF-38 — la pestaña de cargas muestra los lotes aplicados y deshace uno solo tras confirmar, como trabajo."""
    comp = _leer('features/powerfactory/DeshacerLotes.tsx')
    assert "kind === 'cargas_aplicar'" in comp and 'result?.token' in comp
    assert 'await confirm(' in comp and 'api.cargasDeshacer(' in comp and 'startJob(' in comp
    assert 'disabled={ocupado}' in comp, 'deshacer se bloquea mientras DIgSILENT trabaja'
    tab = _leer('features/powerfactory/CargasTab.tsx')
    assert '<DeshacerLotes />' in tab


def test_las_mejoras_del_asistente_se_deciden_en_su_panel():
    """026:RF-28 — el panel del equipo del asistente lista las propuestas sin decisión y manda la decisión del humano."""
    comp = _leer('features/asistente/MejorasPendientes.tsx')
    assert 'api.asistenteRegistro' in comp and 'api.asistenteDecision(' in comp and '!p.decision' in comp
    for decision in ('aceptada', 'modificada', 'rechazada'):
        assert f"'{decision}'" in comp, decision
    equipo = _leer('features/asistente/EquipoAsistente.tsx')
    assert '<MejorasPendientes />' in equipo
