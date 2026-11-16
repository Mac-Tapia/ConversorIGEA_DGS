"""Spec 111, T14: la página del plano (``pagina_plano.py``), generada por el servidor con el Leaflet propio.

La página va en un marco aislado (``preview.politica_pagina_generada``): sin origen propio ni ``connect-src``, habla con
la pestaña solo por ``postMessage`` con un esquema cerrado. Lleva todos los vértices de la fuente, capas por vista, un
nivel de detalle solo gráfico, la leyenda con unidad, umbral, caso y motor, y tokens claro y oscuro. Sin la salida de
teselas, ningún fondo y se dice (086:RF-22, RF-65). Exports sintéticos sorteados con las dos disposiciones.
"""
from __future__ import annotations

import base64
import hashlib
import importlib
import importlib.util
import json
import random
import re

import pytest

from convertersmartgrid.estudios_pf import LIMITES_POR_DEFECTO
from convertersmartgrid.geography import build_geography, geography_to_dict
from convertersmartgrid.model import build_feeder_model
from convertersmartgrid.plano_red import vista
from synthetic_export import CRS_SINTETICO, ExportSpec, load_export

LAYOUTS = ('reducido', 'completo')


def _pagina():
    assert importlib.util.find_spec('convertersmartgrid.pagina_plano') is not None, 'falta pagina_plano.py'
    return importlib.import_module('convertersmartgrid.pagina_plano')


def _vistas(tmp_path, layout='reducido'):
    seed = random.SystemRandom().randrange(1, 2 ** 31)
    spec = ExportSpec(feeders=random.Random(seed).randint(2, 4), seed=seed, layout=layout, sections_per_feeder=6,
                      switches_per_feeder=2)
    ds = load_export(spec, tmp_path / f'export_{seed}')
    vistas = []
    for net in ds.feeder_ids():
        m = build_feeder_model(ds, net, strict=True, include_geography=True)
        vistas.append({**vista(m, geography_to_dict(build_geography(ds, m, source_crs=CRS_SINTETICO), m)),
                       'revision': 'b' * 64})
    return vistas, seed


def _datos(html: str) -> dict:
    """Los datos que la página lleva dentro, en su bloque JSON (nunca en el guion)."""
    m = re.search(r'<script type="application/json" id="datos-plano">(.*?)</script>', html, re.S)
    assert m, 'la página no lleva su bloque de datos'
    return json.loads(m.group(1))


@pytest.mark.parametrize('layout', LAYOUTS)
def test_111_rf1_la_pagina_lleva_el_leaflet_propio_con_lienzo_y_todos_los_vertices(tmp_path, layout):
    """111:RF-1 — el Leaflet propio (con su huella), el lienzo y todos los vértices de la fuente, sin simplificar."""
    from convertersmartgrid.preview import HUELLAS_LEAFLET, recurso_leaflet

    vistas, seed = _vistas(tmp_path, layout)
    html = _pagina().pagina(vistas)
    js = recurso_leaflet('leaflet.js')
    huella = 'sha256-' + base64.b64encode(hashlib.sha256(js.encode('utf-8')).digest()).decode()
    assert huella == HUELLAS_LEAFLET['leaflet.js'] and js in html
    assert 'preferCanvas: true' in html and 'unpkg' not in html and 'cdn' not in html.lower()
    datos = _datos(html)
    por_codigo = {(v['alimentador'], t['codigo']): t['vertices'] for v in vistas for t in v['tramos']}
    assert {(v['alimentador'], t['codigo']): t['vertices'] for v in datos['vistas'] for t in v['tramos']} == por_codigo, seed


def test_111_rf1_el_nivel_de_detalle_es_solo_grafico_y_reversible(tmp_path):
    """111:RF-1 — el detalle cambia con el zoom solo al dibujar (``smoothFactor``); los datos siguen enteros."""
    vistas, _seed = _vistas(tmp_path)
    html = _pagina().pagina(vistas)
    assert "map.on('zoomend'" in html and 'smoothFactor' in html
    assert _pagina().DETALLE_POR_ZOOM and all(f >= 0 for _z, f in _pagina().DETALLE_POR_ZOOM)


def test_111_rf2_cada_trazo_lleva_su_codigo_y_lo_devuelve_al_seleccionarlo(tmp_path):
    """111:RF-2 — lo que se selecciona en el plano vuelve a la pestaña con el mismo código de la fuente."""
    vistas, _seed = _vistas(tmp_path)
    html = _pagina().pagina(vistas)
    assert "tipo: 'seleccionado'" in html and 'codigo: ' in html
    datos = _datos(html)
    assert all(t['codigo'] for v in datos['vistas'] for t in v['tramos'])


def test_111_rf14_los_mensajes_tienen_un_esquema_cerrado(tmp_path):
    """111:RF-14 — la página solo acepta del padre los mensajes de su lista, con sus campos, y nada de otra ventana."""
    vistas, _seed = _vistas(tmp_path)
    p = _pagina()
    html = p.pagina(vistas)
    assert set(p.MENSAJES_ENTRADA) == {'seleccionar', 'resaltar', 'capa', 'propuesta'}
    assert set(p.MENSAJES_SALIDA) == {'listo', 'seleccionado'}
    assert f'const ENTRADA = {json.dumps(list(p.MENSAJES_ENTRADA))};' in html
    assert 'event.source !== window.parent' in html
    assert 'connect-src' not in html and 'fetch(' not in html and 'XMLHttpRequest' not in html


def test_111_rf14_sin_teselas_no_hay_fondo_y_se_dice(tmp_path, monkeypatch):
    """111:RF-14; 086:RF-22 — con la salida apagada no se pide ninguna tesela, el plano se dibuja y lo dice."""
    vistas, _seed = _vistas(tmp_path)
    monkeypatch.setenv('CSG_SALIDA_TESELAS', '0')
    html = _pagina().pagina(vistas)
    assert 'tile.openstreetmap' not in html and 'arcgisonline' not in html and 'L.tileLayer(f.url' not in html
    assert 'Sin mapa base' in html and 'CSG_' not in html
    monkeypatch.setenv('CSG_SALIDA_TESELAS', '1')
    assert 'L.tileLayer(f.url' in _pagina().pagina(vistas)


def test_111_rf13_los_resultados_llevan_leyenda_texto_e_icono_y_el_motor(tmp_path):
    """111:RF-10, RF-13, RF-18 — la capa de resultados con su leyenda (unidad, umbral, caso, motor) y cada
    incumplimiento con texto e icono además del color."""
    from convertersmartgrid.resultados_plano import capas

    vistas, _seed = _vistas(tmp_path)
    v = vistas[0]
    barras = {b['codigo']: {'u_pu': 0.9, 'kv': 10.0} for b in v['barras']}
    tramos = {t['codigo']: {'i_a': 10.0, 'carga_pct': 120.0} for t in v['tramos']}
    r = {'motor': 'abierto', 'caso': 'Caso A', 'revision': v['revision'], 'convergio': True, 'mensajes': [],
         'barras': barras, 'tramos': tramos, 'equipos': {}}
    c = capas(r, limites=LIMITES_POR_DEFECTO, revision=v['revision'], caso='Caso A')
    html = _pagina().pagina(vistas, capas=c)
    datos = _datos(html)
    assert datos['capas']['capas']['tension']['leyenda']['unidad'] == 'p.u.'
    assert 'motor abierto' in html and 'Caso A' in html
    assert 'icono-incumple' in html and 'incumple.texto' in html


def test_111_rf14_un_nombre_con_codigo_no_rompe_la_pagina(tmp_path):
    """111:RF-14 — un nombre de la entrega con «</script>» queda como texto: no cierra ningún guion."""
    vistas, _seed = _vistas(tmp_path)
    vistas[0]['tramos'][0]['codigo'] = '</script><script>alert(1)</script>'
    html = _pagina().pagina(vistas)
    assert '</script><script>alert(1)' not in html
    assert _datos(html)['vistas'][0]['tramos'][0]['codigo'] == '</script><script>alert(1)</script>'


def test_111_rf14_tokens_claro_y_oscuro(tmp_path):
    """111:RF-14 — colores por tokens, con su versión oscura."""
    vistas, _seed = _vistas(tmp_path)
    html = _pagina().pagina(vistas)
    assert '@media (prefers-color-scheme: dark)' in html and '--plano-fondo' in html


def test_111_rf14_la_api_sirve_la_pagina_aislada(tmp_path):
    """111:RF-14 — ``GET …/plano/pagina`` con la política de las páginas generadas (sandbox, sin connect-src)."""
    from convertersmartgrid.preview import politica_pagina_generada
    from test_plano_api import BASE, _montar

    cliente, _ws, _f, _t, alimentador, _seed = _montar(tmp_path)
    r = cliente.get(f'{BASE}/pagina', params={'alimentador': alimentador})
    assert r.status_code == 200, r.text
    assert r.headers['content-security-policy'] == politica_pagina_generada()
    assert _datos(r.text)['vistas'][0]['alimentador'] == alimentador


def test_111_rf14_la_pagina_envia_solo_al_origen_de_la_web_y_lo_comprueba(tmp_path):
    """111:RF-14 — la página manda sus mensajes a ``window.location.origin`` (la web que la sirve), nunca a «*», y
    solo atiende los que le llegan del padre con ese mismo origen."""
    vistas, _seed = _vistas(tmp_path)
    guion = _pagina().pagina(vistas).split('id="datos-plano">', 1)[1]
    envios = re.findall(r'window\.parent\.postMessage\((.*?)\);', guion, re.S)
    assert len(envios) == 2, envios
    assert all(e.rstrip().endswith(', window.location.origin') for e in envios), envios
    assert "'*'" not in guion and '"*"' not in guion
    assert 'event.origin !== window.location.origin' in guion and 'event.source !== window.parent' in guion
