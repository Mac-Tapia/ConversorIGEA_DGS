"""Spec 004, demanda medida: contrato entre el front y la API (el front no se ejecuta aquí)."""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / 'frontend' / 'src'
APP = (RAIZ / 'src' / 'igea_dgs' / 'web' / 'app.py').read_text(encoding='utf-8')
CARGAS = (SRC / 'components' / 'CargasTab.tsx').read_text(encoding='utf-8')
DEMANDA = (SRC / 'components' / 'DemandaMedida.tsx').read_text(encoding='utf-8')


def test_demanda_medida_en_la_misma_pestana():
    """004:RF-40 — la demanda medida se monta dentro de la pestaña «Cargas en DIgSILENT»."""
    assert "import { DemandaMedida } from './DemandaMedida'" in CARGAS
    assert '<DemandaMedida' in CARGAS      # con o sin propiedades (spec 006 le pasa el proyecto)
    app_tsx = (SRC / 'App.tsx').read_text(encoding='utf-8')
    assert 'DemandaMedida' not in app_tsx, 'no es una pestaña aparte'


def test_las_tres_funciones_de_cargas_siguen():
    """004:RF-41 — carga nueva (formulario), cargas nuevas y demandas en bloque siguen en la pestaña."""
    for pieza in ('setDemandas', 'setNuevas', 'guardarNueva', 'api.cargasPlan', 'api.cargasSimular',
                  'api.cargasAplicar'):
        assert pieza in CARGAS, pieza
    assert 'cargasPlan' not in DEMANDA, 'la demanda medida no rellena el plan de cargas'


def test_cabecera_es_un_trabajo_y_cada_ruta_existe():
    """004:RF-22 / RF-38 / RF-39 — el cliente llama a rutas que la API define; la cabecera, como trabajo."""
    assert 'startJob(() => api.demandaCabecera' in DEMANDA
    api_ts = (SRC / 'api.ts').read_text(encoding='utf-8')
    rutas = {re.sub(r'\{[^}]+\}', '{}', r)
             for r in re.findall(r"@app\.(?:get|post|put|delete)\('([^']+)'", APP)}
    llamadas = [ll for ll in re.findall(r'`\$\{ws\(id\)\}(/demanda[^`?]*)', api_ts)]
    assert len(llamadas) >= 6, llamadas
    for llamada in llamadas:
        ruta = '/api/workspaces/{}' + re.sub(r'\$\{[^}]+\}', '{}', llamada)
        assert ruta in rutas, f'{ruta} no existe en la API'
