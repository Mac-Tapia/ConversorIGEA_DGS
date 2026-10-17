"""Spec 021, RF-25 a RF-27 y RF-34: la central térmica de un alimentador en la web.

El front no se ejecuta en la suite (no hay pruebas de navegador): se comprueba en la
fuente que cada pieza existe y que llama a la ruta que la API define, como en
``test_curva_cabecera_front.py``. Lo demás se ve en el navegador.
"""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / 'frontend' / 'src'
APP_PY = (RAIZ / 'src' / 'igea_dgs' / 'web' / 'app.py').read_text(encoding='utf-8')
DEMANDA = (SRC / 'components' / 'DemandaMedida.tsx').read_text(encoding='utf-8')
AJUSTE = (SRC / 'components' / 'AjusteCabecera.tsx').read_text(encoding='utf-8')
API = (SRC / 'api.ts').read_text(encoding='utf-8')
TIPOS = (SRC / 'types.ts').read_text(encoding='utf-8')


def test_campo_central_con_tres_medidores_y_su_nodo():
    """021:RF-25 — por alimentador, «Declarar central»: generación, llegada, salida y la
    barra del troncal; sus tres medidores van en el mismo trabajo de la máxima."""
    assert 'Declarar central</button>' in DEMANDA
    for campo in ("'generacion', 'Generación'", "'llegada', 'Llegada (lado SET)'",
                  "'salida', 'Salida (lado carga)'", 'Barra de la central en DIgSILENT'):
        assert campo in DEMANDA
    assert 'api.demandaCabecera(ws.id, aBuscar)' in DEMANDA
    assert 'alimentador: alimentadorDeCentral(f), medidor' in DEMANDA
    assert 'nodo: string;' in TIPOS


def test_medidores_que_no_son_de_la_red_en_el_desplegable():
    """021:RF-26 — el desplegable ofrece los medidores de la ruta de la API que no son de
    un alimentador de la red."""
    assert "@app.get('/api/workspaces/{wid}/demanda/medidores-externos')" in APP_PY
    assert '/demanda/medidores-externos?${q}' in API
    assert 'api.demandaMedidoresExternos(ws.id, feeders)' in DEMANDA
    assert 'opcionesExternas.map((m) => (' in DEMANDA


def test_la_central_del_perfil_se_propone_rellena():
    """021:RF-27 — la central del perfil de cada alimentador marcado sale ya rellena, y el
    operador puede cambiarla o quitarla."""
    assert 'ext.centrales_perfil[f]' in DEMANDA
    assert 'onClick={() => quitarCentral(f)}' in DEMANDA


def test_resumen_de_la_maxima_con_central():
    """021:RF-34 — el ajuste muestra, por alimentador con central, la máxima de demanda,
    cada zona, la generación, la cabecera y la máxima de cabecera que no es la de la
    demanda, de la ruta de la API."""
    assert "@app.get('/api/workspaces/{wid}/demanda/cabecera/{job_id}/central')" in APP_PY
    assert '/demanda/cabecera/${enc(jobId)}/central?' in API
    assert 'api.demandaCentral(ws.id, maxima.id, g.alimentador, medidor, centrales[g.alimentador])' in AJUSTE
    for texto in ('máxima de demanda', 'aguas arriba', 'aguas abajo', 'generaba',
                  'por la cabecera entraban', 'no es la de la demanda'):
        assert texto in AJUSTE
    assert 'centrales={Object.fromEntries(' in DEMANDA
