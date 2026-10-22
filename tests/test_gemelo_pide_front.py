"""Spec 024: el paso 5 de la web (PIDE y gemelo digital) y su contrato con la API."""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / 'frontend' / 'src'
APP = (RAIZ / 'src' / 'igea_dgs' / 'web' / 'app.py').read_text(encoding='utf-8')


def test_paso_5_en_la_pestana_de_cargas():
    """024:RF-45 / 024:RF-48 — el operador planifica, ve las obras con su estado y decide
    sobre cada una desde la pestaña «Cargas en DIgSILENT», con el proyecto y los
    alimentadores que ya eligió (sirve para cualquier proyecto y alimentadores)."""
    cargas = (SRC / 'components' / 'CargasTab.tsx').read_text(encoding='utf-8')
    assert '<GemeloPIDE project={project} feeders={order} />' in cargas
    comp = (SRC / 'components' / 'GemeloPIDE.tsx').read_text(encoding='utf-8')
    for pieza in ('api.pide(', 'api.pideDecision(', 'api.gemeloAprender(', 'api.gemeloEpisodios(',
                  'startJob(', "'aceptada', 'rechazada', 'modificada'"):
        assert pieza in comp, pieza


def test_cada_ruta_del_gemelo_existe_en_la_api():
    """024:RF-8 — las rutas que llama el front existen en la API."""
    api = (SRC / 'api.ts').read_text(encoding='utf-8')
    rutas = {re.sub(r'\{[^}]+\}', '{}', r) for r in re.findall(r"@app\.(?:get|post)\('([^']+)'", APP)}
    for llamada in ('/pide', '/pide/decision', '/digital-twin/aprender', '/digital-twin/episodes'):
        assert f'${{ws(id)}}{llamada}' in api, llamada
        assert f'/api/workspaces/{{}}{llamada}' in rutas, llamada
