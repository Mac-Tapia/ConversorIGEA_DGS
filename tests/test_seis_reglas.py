"""Spec 084: seis reglas del usuario que vivían en notas, ahora con su requisito y su prueba.

Sitio de la SET nueva, ternas subterráneas, bancos limitados por el valle, DIgSILENT sin datos inventados, borrar
solo en el proyecto de la orden y orden de las alternativas del informe. Todo con el doble de DIgSILENT.
"""
from __future__ import annotations

import ast
import json
import random
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from apoyo import cargar_herramienta
from convertersmartgrid import escalera_optima as eo
from convertersmartgrid import instalacion_ternas as it
from convertersmartgrid import optimizacion_oraculo as oo
from convertersmartgrid import pf_arnes, sitio_set
from convertersmartgrid.asistente.interprete import Interpretacion
from convertersmartgrid.asistente.ordenes_fijas import FRASES
from convertersmartgrid.asistente.plan import _PIDE_BORRAR, resolver
from convertersmartgrid.asistente.sinteticos import normalizar
from convertersmartgrid.asistente.tareas import TAREAS
from convertersmartgrid.informe_docx import DatosEstudio, escribir_informe_estudio
from convertersmartgrid.informes import Caso, Encabezado, Etapa, Extremo, Potencia, alternativas_de_obras, describir_obra
from convertersmartgrid.informes import obra_para_informe, trechos_de_conductor
from convertersmartgrid.obras_pf import ObrasError, validar_obra
from test_informe_alternativas import GEO, GEO_SIN, _caso, _config, _texto
from test_obras_pf_guion import CON, _activas, _calibrada, _linea, _plan
from test_obras_pf_guion_042 import PERFIL, _con_red_externa, _obra

guion = cargar_herramienta('obras_pf.py', 'obras_084', tools_en_path=True)
cargas_guion = cargar_herramienta('cargas_pf.py', 'cargas_084', tools_en_path=True)
RAIZ = Path(__file__).resolve().parents[1]

#: Un alimentador recto hacia el sur, en coordenadas que no son de ninguna empresa.
TRAZADO = [('L1', [(-10.0, -70.0), (-10.01, -70.0)]), ('L2', [(-10.01, -70.0), (-10.02, -70.0)])]
RETIRO = 40.0


def _p(retiro=RETIRO, calles=(), avisos=()):
    return sitio_set.ParametrosSitio(retiro, tuple(calles), tuple(avisos))


# ======================================================================= regla 1: sitio de la SET nueva
def test_mide_la_distancia_al_trazado_y_nombra_el_tramo():
    """084:RF-1 — sorteado: un punto a N metros al este de la red, medido sobre su geometría."""
    rng = random.Random(84)
    for _ in range(20):
        metros = rng.uniform(5, 2000)
        lat = -10.0 - rng.uniform(0, 0.02)
        lon = -70.0 + metros / (sitio_set.M_POR_GRADO * sitio_set.math.cos(sitio_set.math.radians(lat)))
        d, tramo = sitio_set.distancia_a_trazados((lat, lon), TRAZADO)
        assert d == pytest.approx(metros, rel=1e-3)
        assert tramo == ('L1' if lat > -10.01 else 'L2')
    assert sitio_set.distancia_a_trazados((-10.0, -70.0), []) == (None, None)
    r = sitio_set.revisar((-10.0, -70.0), [], _p())
    assert r['a_alimentador_m'] is None and any('084:RF-1' in a for a in r['avisos'])


def test_un_punto_encima_de_la_red_se_aparta_lo_justo():
    """084:RF-2 — un punto sobre la red queda al menos al retiro, cerca, de forma determinista."""
    punto = (-10.005, -70.0)
    r = sitio_set.situar(punto, TRAZADO, _p())
    assert r['movido'] and r['a_alimentador_m'] >= RETIRO
    assert r['a_alimentador_m'] < 2 * RETIRO
    assert r == sitio_set.situar(punto, TRAZADO, _p())
    assert any('084:RF-2' in a for a in r['avisos'])
    # Uno que ya cumple no se mueve.
    lejos = (-10.005, -69.99)
    quieto = sitio_set.situar(lejos, TRAZADO, _p())
    assert not quieto['movido'] and (quieto['lat'], quieto['lon']) == lejos


def test_sin_sitio_al_alcance_queda_el_punto_y_se_dice():
    """084:RF-3 — una malla densa no deja sitio: el punto sigue, encima de la red y dicho, sin error."""
    malla = []
    for i in range(-60, 61):
        desde, hasta = -10.0 - 0.05, -10.0 + 0.05
        malla.append((f'V{i}', [(desde, -70.0 + i * 0.0002), (hasta, -70.0 + i * 0.0002)]))
    r = sitio_set.situar((-10.0, -70.0), malla, _p())
    assert not r['movido'] and r['estado'] == sitio_set.SOBRE_ALIMENTADOR
    assert any('084:RF-3' in a for a in r['avisos'])
    assert 'Queda encima de la red' in r['frase']


def test_con_calles_locales_tambien_se_aparta_de_ellas(tmp_path):
    """084:RF-4 — un GeoJSON local, en lon, lat: la calle cuenta igual que la red."""
    ruta = tmp_path / 'calles.geojson'
    ruta.write_text(json.dumps({'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'name': 'Av. Sintética'},
         'geometry': {'type': 'LineString', 'coordinates': [[-69.99, -10.0], [-69.99, -10.02]]}},
        {'type': 'Feature', 'geometry': {'type': 'MultiLineString', 'coordinates': [[[-69.0, -10.0], [-69.0, -10.1]]]}},
    ]}), encoding='utf-8')
    p = sitio_set.parametros({'planificacion': {'sitio_set': {'retiro_min_m': RETIRO, 'calles_geojson': str(ruta)}}})
    assert len(p.calles) == 2 and p.calles[0][0] == 'Av. Sintética'
    r = sitio_set.situar((-10.005, -69.99), TRAZADO, p)
    assert r['movido'] and r['a_calle_m'] >= RETIRO and r['estado'] == sitio_set.APARTADO
    assert 'Av. Sintética' in r['frase']


def test_sin_calles_el_punto_queda_sin_verificar_en_plano(tmp_path, monkeypatch):
    """084:RF-5 — sin fichero, o con uno ilegible, «sin verificar en plano»; nunca sale a la red."""
    import urllib.request

    def prohibido(*_a, **_k):
        raise AssertionError('el sitio no consulta servicios externos')
    monkeypatch.setattr(urllib.request, 'urlopen', prohibido)
    r = sitio_set.situar((-10.005, -69.99), TRAZADO, _p())
    assert r['estado'] == sitio_set.SIN_VERIFICAR and 'Sin verificar en plano' in r['frase']
    assert any('084:RF-5' in a for a in r['avisos'])
    roto = tmp_path / 'c.geojson'
    roto.write_text('no es json', encoding='utf-8')
    for ruta in (roto, tmp_path / 'no_existe.geojson'):
        p = sitio_set.parametros({'planificacion': {'sitio_set': {'retiro_min_m': RETIRO, 'calles_geojson': str(ruta)}}})
        assert not p.calles and any('084:RF-5' in a for a in p.avisos)
        assert sitio_set.situar((-10.005, -69.99), TRAZADO, p)['estado'] == sitio_set.SIN_VERIFICAR
    fuente = (RAIZ / 'src/convertersmartgrid/sitio_set.py').read_text(encoding='utf-8')
    assert not re.search(r'\b(requests|urllib|http|osrm|overpass)\b', fuente, re.I)


def test_sin_retiro_en_el_perfil_da_la_distancia_y_no_mueve():
    """084:RF-6 — sin el dato de la empresa no se supone ninguna distancia (P13)."""
    p = sitio_set.parametros({})
    assert p.retiro_m is None
    r = sitio_set.situar((-10.005, -70.0), TRAZADO, p)
    assert not r['movido'] and r['a_alimentador_m'] == pytest.approx(0, abs=1e-6)
    assert r['estado'] == sitio_set.SIN_VERIFICAR and any('retiro_min_m' in a and '084:RF-6' in a for a in r['avisos'])


def test_nunca_dice_area_libre():
    """084:RF-7 — ningún estado afirma lo que solo se ve en el plano."""
    calles = (('C', [(-11.0, -71.0), (-11.0, -71.1)]),)
    for p in (_p(), _p(calles=calles), sitio_set.parametros({})):
        for punto in ((-10.005, -70.0), (-10.005, -69.99)):
            f = sitio_set.situar(punto, TRAZADO, p)['frase'].lower()
            assert 'libre' not in f and 'cumple' not in f and 'ok' not in f.split()
    assert 'viviendas' in sitio_set.situar((-10.005, -69.99), TRAZADO, _p(calles=calles))['frase']


@pytest.fixture()
def perfil_retiro(monkeypatch):
    perfil = {'planificacion': {**PERFIL['planificacion'], 'sitio_set': {'retiro_min_m': RETIRO}}}
    monkeypatch.setattr(guion, 'datos_perfil', lambda: perfil)
    return perfil


def _set_sobre_la_red(app, alims):
    """La obra de la SET nueva con su punto justo encima de una línea."""
    _con_red_externa(app)
    _activas(app, CON)
    trazados = guion._trazados_de_la_red(app)
    assert trazados
    a = trazados[0][1][0]
    return trazados, guion.aplicar(app, _plan(alims, obras=[_obra(destino=f'{a[0]:.7f}, {a[1]:.7f}')]))


def test_el_guion_mide_cada_intento_ya_apartado_y_los_dos_flujos_en_el_final(perfil_retiro):
    """084:RF-8, 084:RF-9 — los intentos se miden fuera del trazado, sin contar las salidas de la propia SET, y
    los dos flujos corren en el punto en que queda."""
    app, alims = _calibrada(random.Random(84), n_min=2, cargas_min=3)
    trazados, (informe, codigo) = _set_sobre_la_red(app, alims)
    assert codigo == 0, informe
    s = informe['obras'][0]['set_nueva']
    assert s['sitio']['movido'] and s['sitio']['retiro_m'] == RETIRO
    assert s['sitio']['a_alimentador_m'] >= RETIRO
    for x in s['intentos']:
        d, _ = sitio_set.distancia_a_trazados((x['lat'], x['lon']), trazados)
        assert d >= RETIRO
    flujos = s['flujos_en_punto']
    assert (flujos['lat'], flujos['lon']) == (s['lat'], s['lon'])
    assert flujos['equilibrado']['converge'] and flujos['desequilibrado']['converge']
    assert flujos['desequilibrado']['modo'] == 1
    assert sitio_set.flujos_al_dia((s['lat'], s['lon']), flujos)


def test_si_un_flujo_no_converge_en_el_punto_final_no_cumple(perfil_retiro, monkeypatch):
    """084:RF-8, 084:RF-11 — se dice cuál, la obra sigue y no hay un «cumple» falso."""
    app, alims = _calibrada(random.Random(85), n_min=2, cargas_min=3)
    monkeypatch.setattr(guion, '_ambos_flujos', lambda _app: {
        'equilibrado': {'converge': True}, 'desequilibrado': {'converge': False}})
    _t, (informe, codigo) = _set_sobre_la_red(app, alims)
    assert codigo == 0, informe
    fila = informe['obras'][0]
    assert fila['set_nueva']['cumple'] is False and fila['variacion']
    assert any('desequilibrado' in a and '084:RF-8' in a for a in fila['avisos'])


def test_flujos_de_otro_punto_no_estan_al_dia():
    """084:RF-10 — sin flujos, o medidos en otro sitio, no vale; un redondeo del GPS sí."""
    final = (-10.0, -70.0)
    assert not sitio_set.flujos_al_dia(final, None)
    assert not sitio_set.flujos_al_dia(final, {'lat': -10.0, 'lon': -70.001})
    assert sitio_set.flujos_al_dia(final, {'lat': -10.000001, 'lon': -70.0})


def _datos_web():
    barras = [{'nombre': n, 'kv': 22.9, 'gps': [-14.95 - 0.002 * i, -74.98]} for i, n in enumerate('HABCD')]
    tramos = [{'nombre': f'L_{a}{b}', 'desde': a, 'hasta': b, 'largo_m': 200.0, 'cerrado': True}
              for a, b in ('HA', 'AB', 'BC', 'BD')]
    cargas = [{'nombre': 'S_A', 'barra': 'A', 'kw': 800.0, 'kvar': 200.0},
              {'nombre': 'S_C', 'barra': 'C', 'kw': 300.0, 'kvar': 100.0},
              {'nombre': 'N1', 'barra': 'C', 'kw': 2000.0, 'kvar': 400.0},
              {'nombre': 'N2', 'barra': 'D', 'kw': 1500.0, 'kvar': 300.0}]
    return {'alimentadores': {'F1': {'cabecera': 'H', 'kv': 22.9, 'barras': barras, 'tramos': tramos, 'cargas': cargas}}}


@pytest.mark.parametrize('final, cumple', [
    ({'cumple': True}, False),
    ({'cumple': True, 'flujos_en_punto': {'lat': -14.951, 'lon': -74.98}}, True)])
def test_la_web_situa_antes_de_crear_la_obra_y_no_bloquea(monkeypatch, tmp_path, final, cumple):
    """084:RF-2, 084:RF-5, 084:RF-8, 084:RF-10, 084:RF-11 — el punto de la obra y el del oráculo son el apartado;
    sin calles se dice; y sin flujos en el punto final no «cumple» y se avisa."""
    from convertersmartgrid import perfil_empresa
    from convertersmartgrid.web import services
    from test_set_nueva import CFG_PIT, _libro

    perfil = {'crs_origen': 'EPSG:32718', 'escalera': {'sorteos': 20, 'semilla': 1},
              'planificacion': {'vida_util_anios': 30, 'factor_seguridad_set': 1.25, 'modulos_pit': CFG_PIT,
                                'sitio_set': {'retiro_min_m': 400.0}}}
    monkeypatch.setattr(perfil_empresa, 'datos_perfil', lambda: perfil)
    monkeypatch.setattr(services, '_guion_pf', lambda *a, **k: (0, _datos_web(), None))
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: [{'sed': 'N1'}, {'sed': 'N2'}])
    monkeypatch.setattr(services, '_crecimiento_de_la_cabecera',
                        lambda ws, ctx, project, feeders, avisos, **kw: {'F1': {'tasa': 0.02}})
    monkeypatch.setattr(services, 'native_action_context', lambda *a, **k: {})
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'C')
    creadas = []
    monkeypatch.setattr(services, 'obra_anadir', lambda ws, obra: creadas.append(obra) or {'id': 'x'})
    monkeypatch.setattr(services, 'obras_ejecutar', lambda *a, **k: {'informe': {'obras': [
        {'set_nueva': {'lat': -14.951, 'lon': -74.98, 'intentos': [{}], **final}}]}})
    ctx = SimpleNamespace(log=lambda _t: None, check_cancel=lambda: None)
    a_set = [{'sed': 'N1', 'alimentador': 'F1', 'kw': 2000.0, 'kvar': 400.0},
             {'sed': 'N2', 'alimentador': 'F1', 'kw': 1500.0, 'kvar': 300.0}]
    r = services.set_nueva_proponer(None, ctx, 'P', ['F1'], a_set, capex=str(_libro(tmp_path)), alimentadores_nuevos=2)
    sitio = r['sitio']
    assert sitio['movido'] and sitio['a_alimentador_m'] >= 400.0
    assert creadas[0]['destino'] == f"{sitio['lat']:.7f}, {sitio['lon']:.7f}"
    assert (r['ubicacion']['lat'], r['ubicacion']['lon']) == (sitio['lat'], sitio['lon'])
    assert any('084:RF-5' in a for a in r['avisos'])
    assert r['ubicacion_final']['cumple'] is cumple
    assert any('084:RF-10' in a for a in r['avisos']) is not cumple


# ======================================================================= regla 2: ternas subterráneas
TABLA = {'configuracion': 'ducto', 'capacidad_a': {'CABLE240': {'ducto': 410, 'triangular': 355}}}
PERFIL_TERNAS = {'planificacion': {'ternas_subterraneas': TABLA}}


@pytest.mark.parametrize('config, esperado', [('', 'una terna por ducto'), ('ducto', 'una terna por ducto'),
                                              ('triangular', 'triangular'), ('rectangular', 'rectangular')])
def test_dos_ternas_dicen_su_configuracion(config, esperado):
    """084:RF-12 — la de la obra o, sin ella, la del perfil."""
    inst = it.instalacion(tipo='CABLE240', ternas=2, cable=True, perfil=PERFIL_TERNAS, configuracion=config)
    assert esperado in it.describir(inst)


def test_sin_configuracion_se_dice_y_una_desconocida_no_vale():
    """084:RF-13 — sin suponer: nombra las tres opciones; la obra rechaza una que no existe."""
    inst = it.instalacion(tipo='X', ternas=3, cable=True, perfil={})
    assert inst['configuracion'] is None and any('084:RF-13' in a and 'triangular' in a for a in inst['avisos'])
    assert 'por definir' in it.describir(inst) and '3 ternas' in it.describir(inst)
    rara = it.instalacion(tipo='X', ternas=2, cable=True, perfil={}, configuracion='plana')
    assert rara['configuracion'] is None
    with pytest.raises(ObrasError, match='084:RF-13'):
        validar_obra({'clase': 'terna', 'alimentador': 'A', 'casos': [CON], 'configuracion': 'plana'})
    assert validar_obra({'clase': 'terna', 'alimentador': 'A', 'casos': [CON],
                         'configuracion': 'Triangular'}).configuracion == 'triangular'


def _un_cable(app, nombre_tipo='CABLE240', sline=0.5):
    linea = _linea(app, next(iter(app.proyecto.GetContents('*.ElmLne', 1))).loc_name)
    linea.typ_id.loc_name, linea.typ_id.sline, linea.typ_id.cohl_ = nombre_tipo, sline, 0
    linea.nlnum = 2
    return linea


def test_la_capacidad_del_fabricante_llega_a_la_linea(monkeypatch):
    """084:RF-14 — ``fline`` lleva la capacidad para esa configuración; el tipo no cambia."""
    app, _alims = _calibrada(random.Random(1), n_min=1, cargas_min=2)
    monkeypatch.setattr(guion, 'datos_perfil', lambda: {'planificacion': {'ternas_subterraneas': {
        **TABLA, 'configuracion': 'triangular'}}})
    linea = _un_cable(app)
    fila = {'avisos': []}
    guion._instalar_ternas(fila, linea)
    assert linea.fline == pytest.approx(355 / 500)
    assert linea.typ_id.sline == 0.5
    (inst,) = fila['instalaciones']
    assert inst['capacidad_a'] == 355 and inst['factor'] == pytest.approx(355 / 500) and not fila['avisos']


def test_sin_dato_del_fabricante_no_se_inventa_factor(monkeypatch):
    """084:RF-15 — sin tabla no se escribe ningún factor y queda dicho."""
    app, _alims = _calibrada(random.Random(2), n_min=1, cargas_min=2)
    monkeypatch.setattr(guion, 'datos_perfil', lambda: {'planificacion': {'ternas_subterraneas': {'configuracion': 'ducto'}}})
    linea = _un_cable(app)
    antes = getattr(linea, 'fline', 'sin escribir')
    fila = {'avisos': []}
    guion._instalar_ternas(fila, linea)
    assert getattr(linea, 'fline', 'sin escribir') == antes
    assert fila['instalaciones'][0]['factor'] is None
    assert any('084:RF-15' in a for a in fila['avisos'])
    assert 'sin confirmar' in it.describir(fila['instalaciones'][0])
    fuente = (RAIZ / 'src/convertersmartgrid/instalacion_ternas.py').read_text(encoding='utf-8')
    assert not re.search(r'(?<![\w.])0[.,]\d', fuente), 'ningún factor de agrupamiento en el código'


def test_el_oraculo_usa_la_capacidad_de_la_configuracion():
    """084:RF-16 — dos ternas de cable valen el doble de la tabla, no el doble del tipo; sin dato, como antes."""
    tramos = [{'nombre': 'T1', 'tipo': 'CABLE240', 'cable': True, 'largo_m': 100.0},
              {'nombre': 'T2', 'tipo': 'AEREO', 'cable': False, 'largo_m': 100.0}]
    obra = {'clase': 'terna', 'tramos': ['T1', 'T2'], **it.capacidad_de_tramos(tramos, TABLA)}
    assert obra['capacidad_terna_a'] == {'T1': 410.0}
    stub = SimpleNamespace(_ramas=[{'r_ohm': 1.0, 'x_ohm': 1.0, 'inom_ka': 0.5}, {'r_ohm': 1.0, 'x_ohm': 1.0, 'inom_ka': 0.5}],
                           rama_de={'T1': 0, 'T2': 1}, tipos={})
    t1, t2 = oo.Oraculo._ramas_con(stub, [obra], [])
    assert t1['inom_ka'] == pytest.approx(0.82) and t1['r_ohm'] == pytest.approx(0.5)
    assert t2['inom_ka'] == pytest.approx(1.0)
    troncal = [{'nombre': 'T1', 'tipo': 'CABLE240', 'cable': True, 'largo_m': 100.0, 'km': 0.1}]
    (v,) = eo._escalon_terna('F', troncal, [{'camino': troncal}], SimpleNamespace(ternas=TABLA))  # 042:RF-98: recibe los parámetros
    assert v.obras[0]['capacidad_terna_a'] == {'T1': 410.0}
    espacio = oo.Espacio('F', [], None, 0, troncal, (), TABLA)
    assert espacio.obras([], ['terna']).obras[0]['capacidad_terna_a'] == {'T1': 410.0}


def test_el_informe_dice_la_instalacion_sin_citar_la_norma():
    """084:RF-17 — configuración y capacidad en el texto; sin artículos ni distancias."""
    inst = it.instalacion(tipo='CABLE240', ternas=2, cable=True, perfil=PERFIL_TERNAS)
    obra = obra_para_informe({'clase': 'terna', 'alimentador': 'F', 'tramos': ['T1'], 'instalaciones': [inst, inst]})
    texto = describir_obra(obra)
    assert texto.count('2 ternas subterráneas, una terna por ducto') == 1 and '410 A por terna' in texto
    for i in (inst, it.instalacion(tipo='X', ternas=2, cable=True, perfil={}),
              it.instalacion(tipo='X', ternas=2, cable=True, perfil={}, configuracion='rectangular')):
        d = it.describir(i)
        assert not re.search(r'art[ií]culo|\bart\.|\bCNE\b|\bNTP\b|\d\s*(?:m|cm|mm)\b', d, re.I), d


@pytest.mark.parametrize('ternas, cable', [(1, True), (2, False), (5, False)])
def test_una_terna_o_una_linea_aerea_no_cambian(monkeypatch, ternas, cable):
    """084:RF-18 — ni aviso, ni factor, ni texto."""
    assert it.instalacion(tipo='X', ternas=ternas, cable=cable, perfil=PERFIL_TERNAS) is None
    assert it.describir(None) == ''
    assert describir_obra({'tipo': 'terna', 'tramos': ['T1'], 'alimentador': 'F'}) == \
        'Tender una terna más en los tramos T1 del alimentador F.'
    assert it.capacidad_de_tramos([{'nombre': 'T', 'tipo': 'CABLE240', 'cable': False}], TABLA) == {}


# ======================================================================= regla 3: bancos limitados por el valle
def _parametros():
    return eo.parametros({'escalera': {'cumplimiento': 0.9, 'sorteos': 10, 'tolerancia_pu': 0.001, 'tolerancia_carga_pct': 1.0},
                          'planificacion': {'tasa_regulada': 0.12, 'vida_util_anios': 30},
                          'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}})


def _evaluada(nombre, costo, maxima=True, valle=True, escalones=('bancos',)):
    return {'nombre': nombre, 'maxima': maxima, 'fraccion': 1.0 if maxima else 0.0, 'costo': {'costo_anual': costo},
            'valle': valle, 'valle_motivos': [] if valle else ['sobretensión'], 'motivos': [], 'escalones': escalones}


def test_el_numero_de_bancos_es_un_tope_y_se_elige_lo_mas_barato_que_cumple():
    """084:RF-19 (073:RF-19) — el valle admite 3: uno no llega, dos bastan; tres, más caros, no se eligen."""
    d = eo.elegir([_evaluada('1 banco', 10.0, maxima=False), _evaluada('2 bancos', 20.0), _evaluada('3 bancos', 30.0)],
                  _parametros())
    assert d['elegida'] == '2 bancos'


@pytest.mark.parametrize('escalones', [('bancos',), ('seccion',), ('terna',), ('bancos', 'seccion')])
def test_toda_variante_se_comprueba_en_maxima_y_en_valle(escalones):
    """084:RF-20 (073:RF-17, 073:RF-39, 073:RF-40) — la más barata cumple en máxima y no en valle: no vale, sea la
    obra que sea; sin valle medido queda dicho, no aprobada en silencio."""
    d = eo.elegir([_evaluada('barata', 10.0, valle=False, escalones=escalones),
                   _evaluada('cara', 20.0, escalones=escalones)], _parametros())
    assert d['elegida'] == 'cara'
    fila = eo.elegir([_evaluada('sin valle', 10.0, valle=None, escalones=escalones)], _parametros())['tabla'][0]
    assert 'no comprobado en valle' in fila['motivo']


# ======================================================================= regla 4: sin datos inventados
def test_una_prueba_no_llega_al_digsilent_real():
    """084:RF-21 — bajo pytest, la API compilada se rechaza antes de tomar el turno; un doble sigue."""
    real = SimpleNamespace(__file__='C:/PF/powerfactory.cp312-win_amd64.pyd')
    with pytest.raises(pf_arnes.PFNoDisponible, match='084:RF-21'):
        pf_arnes.conectar('sonda', modulo=real)
    pf_arnes.exigir_fuera_de_pruebas(real, {})
    pf_arnes.exigir_fuera_de_pruebas(SimpleNamespace(__file__='tests/fake_pf.py'))
    pf_arnes.exigir_fuera_de_pruebas(SimpleNamespace())


def test_la_aceptacion_nativa_pasa_por_la_misma_guarda():
    """084:RF-22 — es el otro único sitio que conecta (064:RF-1) y también rechaza la API real en una prueba."""
    arbol = ast.parse((RAIZ / 'tools/powerfactory_acceptance.py').read_text(encoding='utf-8'))
    llamadas = [n for n in ast.walk(arbol) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == 'exigir_fuera_de_pruebas']
    assert llamadas


@pytest.mark.parametrize('vocab', [{'proyecto': ['REAL'], 'alimentadores': ['F1']},
                                   {'proyecto': [], 'alimentadores': []}])
def test_el_asistente_no_ejecuta_con_nombres_que_la_web_no_conoce(vocab):
    """084:RF-23 — un proyecto o alimentador inventado deja el plan sin ejecutar: falta el dato o su contexto."""
    i = Interpretacion('escalera de obras de NOEXISTE en INVENTADO', 'obras_escalera', 0.99, 'transformer',
                       {'proyecto': [{'valor': 'INVENTADO'}], 'alimentadores': [{'valor': 'NOEXISTE'}]})
    plan = resolver(i, vocab)
    assert not plan.listo and plan.faltan


# ======================================================================= regla 5: borrar solo en su proyecto
class _Obj:
    def __init__(self, nombre, clase='ElmTerm', padre=None):
        self.loc_name, self.clase, self.padre, self.borrado = nombre, clase, padre, False

    def GetClassName(self):
        return self.clase

    def GetParent(self):
        return self.padre

    def GetFullName(self):
        return f'{self.padre.GetFullName()}\\{self.loc_name}' if self.padre else self.loc_name

    def Deactivate(self):
        return 0

    def Delete(self):
        self.borrado = True
        return 0


def test_borrar_solo_en_el_proyecto_de_la_orden():
    """084:RF-24 — el de la orden se borra; el de otro proyecto, o sin proyecto, no se toca."""
    a, b = _Obj('P_A', 'IntPrj'), _Obj('P_B', 'IntPrj')
    propio = _Obj('SET', 'IntScheme', _Obj('Var', 'IntPrjfolder', a))
    ajeno = _Obj('SET', 'IntScheme', _Obj('Var', 'IntPrjfolder', b))
    assert pf_arnes.borrar_en_su_proyecto(propio, a) == 0 and propio.borrado
    for obj, proyecto in ((ajeno, a), (_Obj('suelto'), a), (propio, None)):
        obj.borrado = False
        with pytest.raises(pf_arnes.BorradoFueraDeProyecto, match='084:RF-24'):
            pf_arnes.borrar_en_su_proyecto(obj, proyecto)
        assert not obj.borrado


def test_el_asistente_no_borra():
    """084:RF-25 — no hay tarea de borrar, y un verbo de borrar no lanza la obra que nombra; su corpus no se altera."""
    assert not [t.nombre for t in TAREAS.values() if _PIDE_BORRAR.search(normalizar(t.nombre.replace('_', ' ')))]
    i = Interpretacion('borra la escalera de F1 en REAL', 'obras_escalera', 1.0, 'catalogo',
                       {'proyecto': [{'valor': 'REAL'}], 'alimentadores': [{'valor': 'F1'}]})
    plan = resolver(i, {'proyecto': ['REAL'], 'alimentadores': ['F1']})
    assert not plan.listo and plan.tarea is None and any('084:RF-25' in f for f in plan.faltan)
    # Una tarea que solo lee sí responde aunque el texto hable de borrar.
    lectura = next(t for t in TAREAS.values() if not t.escribe)
    assert resolver(Interpretacion('¿cómo se quita esto?', lectura.nombre, 1.0, 'catalogo'), {}).tarea == lectura.nombre
    frases = [f for grupo in FRASES.values() for f in grupo] + [f for t in TAREAS.values() for f in t.plantillas]
    assert frases and not [f for f in frases if _PIDE_BORRAR.search(normalizar(f))]


def test_deshacer_y_eliminar_no_borran_lo_de_otro_proyecto():
    """084:RF-26 — la variación de otro proyecto queda con su error y las demás siguen."""
    a, b = _Obj('P_A', 'IntPrj'), _Obj('P_B', 'IntPrj')
    propia, ajena = _Obj('V1', 'IntScheme', a), _Obj('V2', 'IntScheme', b)
    app = SimpleNamespace(GetActiveProject=lambda: a, GetActiveStudyCase=lambda: None, GetProjectFolder=lambda _n: None)
    r = cargas_guion.eliminar_variaciones(app, [{'variacion': 'V2'}, {'variacion': 'V1'}], {'V1': propia, 'V2': ajena})
    assert not ajena.borrado and propia.borrado
    assert r[0]['eliminada'] is False and '084:RF-24' in r[0]['error'] and r[1]['eliminada'] is True


#: Cada ``Delete`` de DIgSILENT con su justificación. Uno nuevo hace fallar la prueba hasta decir qué borra.
BORRADOS = {
    # Lo creó la misma ejecución y lo retira al terminar: órdenes, selecciones, variaciones temporales.
    'temporal': {
        'tools/obras_pf.py::crear_tipos_conductor',
        'tools/capacidad_pf.py::alojamiento', 'tools/capacidad_pf.py::curvas_pv', 'tools/capacidad_pf.py::condensadores',
        'tools/cargas_pf.py::crear_variacion', 'tools/cargas_pf.py::_una_carga', 'tools/check_pf_license.py::main',
        'tools/confiabilidad_pf.py::fiabilidad', 'tools/confiabilidad_pf.py::reconectadores',
        'tools/escenarios_pf.py::ejecutar', 'tools/estudios_pf.py::_optimizador', 'tools/estudios_pf.py::_contingencias',
        'tools/estudios_pf.py::_estudio_de_red', 'tools/obras_pf.py::_grabar_una', 'tools/obras_pf.py::_Sorteo.__exit__',
        'tools/obras_pf.py::crear_tipos_regulador', 'tools/obras_pf.py::evaluar.con_variante',
        # 098:RF-36: lo creado por la obra nueva de una sustitución que no queda, por sus nombres del diario.
        'tools/obras_pf.py::_borrar_creadas',
        'tools/powerfactory_acceptance.py::import_dgs_file', 'tools/run_one_study.py::main',
        'tools/set_nueva_operacion_pf.py::ejecutar', 'tools/transferencia_pf.py::_con_comtransfer',
        'tools/transferencia_pf.py::_en_un_caso'},
    # Objetos con nombre propio del conversor, en el proyecto activado por la orden, que se renuevan sin duplicar.
    'renovado': {
        'src/convertersmartgrid/carpeta_pf.py::eliminar_versiones_anteriores',
        'tools/ajuste_cabecera_pf.py::_limpiar_etapa_de_la_central', 'tools/casos_pf.py::_escenario_renovado',
        'tools/confiabilidad_pf.py::escribir_modelos', 'tools/confiabilidad_pf.py::aplicar_datos',
        'tools/pide_pf.py::casos_del_anio', 'tools/obras_pf.py::_proyecto_biblioteca',
        'tools/obras_pf.py::retirar_obras',
        # 098:RF-36: las variaciones de obra por su nombre exacto: la vieja tras comprobar la nueva, o la nueva al deshacer.
        'tools/obras_pf.py::_borrar_variaciones',
        # 025:RF-79: «Cargas nuevas <año>» por su nombre y su marca, para copiarlo otra vez de «Sin proyecto» (PA217).
        'tools/casos_pf.py::_borrar_caso'},
    # Con su guarda: la de esta spec, o la de la copia de prueba (064).
    'con_guarda': {'src/convertersmartgrid/pf_arnes.py::borrar_en_su_proyecto', 'tools/restitucion_pf.py::borrar'},
}


def _borrados_en_el_codigo() -> set[str]:
    hallados = set()

    def recorrer(nodo, pila, rel):
        for h in ast.iter_child_nodes(nodo):
            siguiente = [*pila, h.name] if isinstance(h, (ast.FunctionDef, ast.ClassDef)) else pila
            if isinstance(h, ast.Call) and isinstance(h.func, ast.Attribute) and h.func.attr == 'Delete':
                hallados.add(f"{rel}::{'.'.join(siguiente)}")
            recorrer(h, siguiente, rel)
    for carpeta in ('tools', 'src'):
        for p in sorted((RAIZ / carpeta).rglob('*.py')):
            recorrer(ast.parse(p.read_text(encoding='utf-8')), [], p.relative_to(RAIZ).as_posix())
    return hallados


def test_cada_borrado_en_digsilent_esta_justificado():
    """084:RF-27 — todo ``Delete`` del código está en la lista, y nada de lo que el operador ordena deshacer
    borra sin la guarda."""
    declarados = set().union(*BORRADOS.values())
    assert _borrados_en_el_codigo() == declarados


# ======================================================================= regla 6: orden de las alternativas
def _aplicada(variacion, clase):
    return {'variacion': variacion, 'obra': {'clase': clase, 'alimentador': 'F'}}


@pytest.mark.parametrize('semilla', [6, 60, 600])
def test_primero_bancos_y_despues_seccion_cada_una_sumada(semilla):
    """084:RF-28 (017:RF-128, 017:RF-129) — en cualquier orden de aplicación."""
    obras = [_aplicada('b1', 'condensador'), _aplicada('b2', 'condensador'), _aplicada('s1', 'seccion'),
             _aplicada('c1', 'consigna')]
    random.Random(semilla).shuffle(obras)
    (uno, dos) = alternativas_de_obras(obras)
    assert uno == {'clave': 'bancos_nuevos', 'variaciones': ['b1', 'b2']}
    assert dos['clave'] == 'conductor' and set(dos['variaciones']) == {'b1', 'b2', 's1', 'c1'}


def _informe_dos_alternativas(tmp_path, imagenes):
    trechos = [{**vars(t), 'desde_utm': [400000.0, 8450000.0], 'hasta_utm': [400100.0, 8449600.0]}
               for t in trechos_de_conductor(GEO, ['L1', 'L2', 'L3', 'L4'], GEO_SIN)]
    etapas = [Etapa('bancos_nuevos', caso=_caso(0.93), obras=({'tipo': 'banco', 'nodo': 'N3', 'kvar': 300},)),
              Etapa('conductor', caso=_caso(0.98), obras=(
                  {'tipo': 'conductor', 'km': 0.44, 'conductor': 'AA120', 'trechos': trechos},))]
    datos = DatosEstudio(alimentadores=['F'], encabezado=Encabezado(date(2026, 11, 3), 'A', 'B'),
                         actual=Caso('Sin proyecto', True, fuente=Potencia(3100, 1500),
                                     tension_min={'trifásica': Extremo(0.90, 'N4')}, nodos_fuera=20),
                         etapas=etapas, imagenes=imagenes)
    destino = tmp_path / 'informe.docx'
    r = escribir_informe_estudio(_config(tmp_path), destino, datos)
    return _texto(destino), r


def test_la_seccion_da_el_trecho_desde_hasta_y_el_plano_que_falta_se_anota(tmp_path):
    """084:RF-29 (017:RF-132, 017:RF-133) — la alternativa de sección da desde y hasta, y un plano que falta no
    desaparece sin más: queda en la lista de huecos del informe."""
    texto, r = _informe_dos_alternativas(tmp_path, {})
    assert texto.index('ALTERNATIVA 1: BANCOS') < texto.index('ALTERNATIVA 2: CAMBIO DE SECCIÓN')
    assert 'desde la barra CAB hasta la barra N4' in texto
    assert 'Incluye las obras de la alternativa 1' in texto
    huecos = getattr(r, 'huecos', r if isinstance(r, list) else None) or []
    assert any('plano de la alternativa 2' in h for h in huecos), r


def test_sin_trecho_el_informe_lo_dice():
    """084:RF-30 — sin geografía guardada, se dice que falta el trecho; no se da por descrita la obra."""
    t = describir_obra({'tipo': 'conductor', 'km': 1.5, 'conductor': 'AA120'})
    assert 'Trecho desde–hasta sin datos' in t and 'Renovar 1,50 km' in t


def test_la_obra_de_terna_deja_su_instalacion_en_el_informe_de_la_obra(monkeypatch):
    """084:RF-12, 084:RF-13 — por el guion completo: la configuración de la obra llega a su fila."""
    app, alims = _calibrada(random.Random(3), n_min=1, cargas_min=3)
    monkeypatch.setattr(guion, 'datos_perfil', lambda: {})
    _linea(app, 'F1_L2').typ_id.cohl_ = 0
    obra = {'clase': 'terna', 'alimentador': 'F1', 'casos': [CON], 'tramos': ['F1_L2'], 'configuracion': 'rectangular'}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 0, informe
    fila = informe['obras'][0]
    (inst,) = fila['instalaciones']
    assert inst['tramo'] == 'F1_L2' and inst['configuracion'] == 'rectangular' and inst['ternas'] == 2
    assert any('084:RF-15' in a for a in fila['avisos'])
