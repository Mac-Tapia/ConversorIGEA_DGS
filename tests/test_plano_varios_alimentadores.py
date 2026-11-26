"""Spec 111, T24 a T27: el plano con varios alimentadores a la vez, sus puntos de transferencia, las etiquetas que se
encienden y el fondo de calles que llega.

- RF-24: cada alimentador con su color (claro y oscuro) y su capa encendible; con uno solo, el color de siempre.
- RF-25: los puntos de transferencia son las barras de frontera que la fuente nombra igual en dos alimentadores; un
  trecho común da sus bordes; una vista combinada (``A_B``) no se cruza con sus partes; las maniobras salen de la fuente.
- RF-26: etiquetas de la SED (código y kVA instalados) y de la sección del conductor, apagadas al abrir y dibujadas al
  acercarse.
- RF-27: las teselas piden con el origen de la web como «Referer»: sin él, OpenStreetMap da «403 Access blocked».
Exports sintéticos sorteados; ningún dato de una empresa.
"""
from __future__ import annotations

import json
import random
import re

from convertersmartgrid.adaptadores.geography import build_geography, geography_to_dict
from convertersmartgrid.adaptadores import plano_red
from convertersmartgrid.adaptadores.plano_red import resumen_plano, vista
from convertersmartgrid.dominio.model import build_feeder_model
from synthetic_export import CRS_SINTETICO, ExportSpec, load_export


def _vistas(tmp_path, n=None):
    seed = random.SystemRandom().randrange(1, 2 ** 31)
    spec = ExportSpec(feeders=n or random.Random(seed).randint(2, 4), seed=seed, layout='reducido', sections_per_feeder=6,
                      switches_per_feeder=2)
    ds = load_export(spec, tmp_path / f'export_{seed}')
    salida = []
    for net in ds.feeder_ids():
        m = build_feeder_model(ds, net, strict=True, include_geography=True)
        salida.append({**vista(m, geography_to_dict(build_geography(ds, m, source_crs=CRS_SINTETICO), m)), 'revision': 'b' * 64})
    return salida, seed


def transferencias(vistas):
    assert hasattr(plano_red, 'transferencias'), 'falta plano_red.transferencias (111:RF-25)'
    return plano_red.transferencias(vistas)


def _datos(html: str) -> dict:
    m = re.search(r'<script type="application/json" id="datos-plano">(.*?)</script>', html, re.S)
    assert m, 'la página no lleva su bloque de datos'
    return json.loads(m.group(1))


def _barra(codigo, lat=-12.0, lon=-77.0):
    return {'codigo': codigo, 'lat': lat, 'lon': lon}


def _v(nombre, barras, tramos, maniobras=()):
    return {'alimentador': nombre, 'barras': [_barra(b) for b in barras],
            'tramos': [{'desde': a, 'hasta': b} for a, b in tramos], 'maniobras': list(maniobras)}


# --------------------------------------------------------------------------------------------------- RF-25
def test_111_rf25_una_barra_comun_es_un_punto_de_transferencia_con_su_maniobra():
    """111:RF-25 — la barra que dos alimentadores nombran igual es su punto de transferencia, con la maniobra de la
    fuente en ella y su estado; las barras propias no lo son."""
    a = _v('X1', ['a1', 'a2', 'F'], [('a1', 'a2'), ('a2', 'F')],
           [{'codigo': 'S9', 'clase': 'seccionador', 'barra': 'F', 'estado': 'abierto', 'tramo': None, 'nombre_pf': 'S9'}])
    b = _v('Y2', ['b1', 'F'], [('b1', 'F')])
    t = transferencias([a, b])
    assert [(p['barra'], p['alimentadores']) for p in t] == [('F', ['X1', 'Y2'])]
    assert t[0]['maniobras'] == [{'codigo': 'S9', 'clase': 'seccionador', 'estado': 'abierto', 'alimentador': 'X1'}]
    assert transferencias([a]) == [] and transferencias([a, _v('Z3', ['z1'], [])]) == []


def test_111_rf25_un_trecho_comun_da_solo_sus_bordes():
    """111:RF-25 — si comparten un trecho entero, el punto es su borde (una barra común junto a una propia), no cada
    barra del trecho."""
    a = _v('X1', ['a1', 'c1', 'c2', 'c3'], [('a1', 'c1'), ('c1', 'c2'), ('c2', 'c3')])
    b = _v('Y2', ['b1', 'c1', 'c2', 'c3'], [('c3', 'b1'), ('c1', 'c2'), ('c2', 'c3')])
    assert sorted(p['barra'] for p in transferencias([a, b])) == ['c1', 'c3']


def test_111_rf25_una_vista_combinada_no_se_cruza_con_sus_partes():
    """111:RF-25 — ``A_B`` (la suma de A y B) contiene sus barras: no son transferencias; dos nombres con una parte común
    que no es suma (``SIS_N``, ``SIS_I``) sí se cruzan."""
    a = _v('A', ['a1', 'F'], [('a1', 'F')])
    b = _v('B', ['b1', 'F'], [('b1', 'F')])
    ab = _v('A_B', ['a1', 'b1', 'F'], [('a1', 'F'), ('b1', 'F')])
    t = transferencias([a, b, ab])
    assert [(p['barra'], p['alimentadores']) for p in t] == [('F', ['A', 'B'])]
    n = _v('SIS_N', ['n1', 'G'], [('n1', 'G')])
    i = _v('SIS_I', ['i1', 'G'], [('i1', 'G')])
    assert [p['alimentadores'] for p in transferencias([n, i])] == [['SIS_N', 'SIS_I']]


def test_111_rf25_el_resumen_y_el_contrato_llevan_las_transferencias(tmp_path):
    """111:RF-25 — el plano de la API lleva sus transferencias y su contrato las acepta."""
    from convertersmartgrid.presentacion.web.api_contract import PlanoRespuesta

    vistas, seed = _vistas(tmp_path)
    resumen = resumen_plano(vistas)
    assert 'transferencias' in resumen, 'el resumen del plano no lleva sus transferencias'
    assert resumen['transferencias'] == transferencias(vistas), seed
    PlanoRespuesta.model_validate({**resumen, 'vistas': vistas, 'motor': {'motor': 'abierto', 'texto': 'Motor abierto',
                                   'motivo': 'x'}, 'fondo': {'encendido': False, 'motivo': 'x'}})


# --------------------------------------------------------------------------------------------------- RF-24
def test_111_rf24_cada_alimentador_con_su_color_y_su_capa(tmp_path):
    """111:RF-24 — con varios alimentadores, un color por cada uno (claro y oscuro), su capa en el selector y el
    resalte que vuelve a su color; la página lleva las transferencias."""
    from convertersmartgrid.adaptadores import pagina_plano as p

    assert hasattr(p, 'COLORES_ALIMENTADOR'), 'un solo color para todos los alimentadores'
    vistas, seed = _vistas(tmp_path, n=3)
    html = p.pagina(vistas)
    claros = [c for c, _o in p.COLORES_ALIMENTADOR]
    oscuros = [o for _c, o in p.COLORES_ALIMENTADOR]
    assert len(set(claros)) == len(claros) and len(set(oscuros)) == len(oscuros)
    for i, (c, o) in enumerate(p.COLORES_ALIMENTADOR):
        assert f'--plano-a{i}: {c}' in html and f'--plano-a{i}: {o}' in html, seed
    assert "token('a' + (i % N_COLORES))" in html and 'porAlimentador[v.alimentador]' in html
    assert 'resaltado.options.colorBase' in html, 'el resalte vuelve al azul aunque el alimentador tenga otro color'
    assert _datos(html)['transferencias'] == transferencias(vistas)


# --------------------------------------------------------------------------------------------------- RF-26
def test_111_rf26_etiquetas_de_sed_y_seccion_apagadas_al_abrir(tmp_path):
    """111:RF-26 — tres capas de etiquetas (código de la SED, kVA instalados y sección del conductor) en el selector,
    apagadas al abrir y dibujadas desde su zoom."""
    from convertersmartgrid.adaptadores import pagina_plano as p

    assert all(len(c) == 3 for c in p.CAPAS), 'las capas no dicen si se ven al abrir'
    capas = {c: (n, v) for c, n, v in p.CAPAS}
    for clave in ('etiqueta_sed', 'etiqueta_kva', 'etiqueta_seccion'):
        assert clave in capas and capas[clave][1] is False, clave
    assert capas['transferencias'][1] is True
    vistas, _seed = _vistas(tmp_path)
    html = p.pagina(vistas)
    assert 'grupos.etiqueta_sed' in html and 'grupos.etiqueta_kva' in html and 'grupos.etiqueta_seccion' in html
    assert f'const ZOOM_ETIQUETAS = {p.ZOOM_ETIQUETAS};' in html and 'Acerque el plano para ver las etiquetas.' in html


def test_111_rf26_cada_tramo_lleva_la_seccion_de_su_codigo(tmp_path):
    """111:RF-26 — la sección sale del código del catálogo (``AA12003D`` → 120 mm²); sin código que la diga, ninguna."""
    from convertersmartgrid.aplicacion.catalog import seccion_de_codigo

    vistas, seed = _vistas(tmp_path)
    tramos = [t for v in vistas for t in v['tramos']]
    assert tramos and all('seccion_mm2' in t for t in tramos), f'los tramos no dicen su sección ({seed})'
    for t in tramos:
        esperada = seccion_de_codigo(t['tipo']) or seccion_de_codigo(str(t['original']['tipo'] or ''))
        assert t['seccion_mm2'] == esperada, (seed, t['codigo'])


# --------------------------------------------------------------------------------------------------- RF-27
def test_111_rf27_las_teselas_piden_con_el_origen_como_referer(monkeypatch):
    """111:RF-27 — la web manda «no-referrer» con todo; cada tesela pide con el origen (nunca la ruta) para que
    OpenStreetMap no conteste «403 Access blocked»."""
    from convertersmartgrid.adaptadores import preview

    assert hasattr(preview, 'REFERER_TESELAS'), 'las teselas no dicen con qué «Referer» piden'
    REFERER_TESELAS, guion_de_fondos = preview.REFERER_TESELAS, preview.guion_de_fondos

    monkeypatch.setenv('CSG_SALIDA_TESELAS', '1')
    guion, _aviso = guion_de_fondos()
    assert REFERER_TESELAS == 'strict-origin-when-cross-origin'
    assert f'referrerPolicy: {json.dumps(REFERER_TESELAS)}' in guion
    # La política va solo en la capa de teselas: la cabecera de la web (086) sigue en «no-referrer» para todo lo demás.
    import inspect

    from convertersmartgrid.presentacion.web import seguridad

    fuente = inspect.getsource(seguridad)
    assert fuente.count("(b'referrer-policy', b'no-referrer')") == 2, 'la cabecera global de la web cambió'
    assert 'referrerPolicy' not in fuente and REFERER_TESELAS not in fuente


def test_111_rf27_las_calles_las_sirve_la_propia_web(monkeypatch, tmp_path):
    """111:RF-27 (26-11) — el plano va en una página aislada («sandbox allow-scripts»): en un Chromium real su tesela
    salió sin «Referer» aunque pidiera «strict-origin-when-cross-origin», y OpenStreetMap devolvió su imagen «403 Access
    blocked». Las calles las pide la propia web, con el User-Agent del programa, y las guarda; la página las toma de ahí
    («'self'»). Coordenadas fuera de rango, 404; con la salida de teselas apagada no se pide nada."""
    import pytest
    from fastapi.testclient import TestClient

    from convertersmartgrid.adaptadores import preview
    from convertersmartgrid.presentacion.web.app import create_app

    monkeypatch.setenv('CSG_SALIDA_TESELAS', '1')
    guion, _aviso = preview.guion_de_fondos()
    assert '/teselas/calles/{z}/{x}/{y}.png' in guion and 'tile.openstreetmap.org' not in guion
    assert "'self'" in preview.politica_base()
    pedidas = []

    def descargar(url, cabeceras):
        pedidas.append((url, cabeceras))
        return b'\x89PNG tesela'

    assert hasattr(preview, 'tesela_calles'), 'falta 111:RF-27: la web no sirve las calles'
    monkeypatch.setattr(preview, 'descargar_tesela', descargar)
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setenv('CSG_CACHE_HOME', str(tmp_path / 'cache'))
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as c:
        r = c.get('/teselas/calles/12/1180/2185.png')            # sin cookie: la página aislada no la manda
        assert r.status_code == 200 and r.content == b'\x89PNG tesela' and r.headers['content-type'] == 'image/png'
        assert c.get('/teselas/calles/12/1180/2185.png').content == b'\x89PNG tesela'
        assert len(pedidas) == 1, 'la segunda sale de la caché'
        url, cabeceras = pedidas[0]
        assert url == 'https://tile.openstreetmap.org/12/1180/2185.png'
        assert cabeceras['User-Agent'].startswith('ConverterSmartGrid/')
        for mala in ('/teselas/calles/20/0/0.png', '/teselas/calles/2/4/0.png', '/teselas/calles/2/-1/0.png'):
            assert c.get(mala).status_code == 404, mala
        monkeypatch.setenv('CSG_SALIDA_TESELAS', '0')
        assert c.get('/teselas/calles/12/1180/2186.png').status_code == 404 and len(pedidas) == 1
