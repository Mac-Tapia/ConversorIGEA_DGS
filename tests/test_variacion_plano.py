"""Spec 111: la variación del plano. Maniobras, tramos nuevos, reglas de la edición, equipos insertados y el diario con
deshacer y rehacer, siempre en el espacio y nunca en el caso base (111:RF-4 a RF-9, RF-15).

Exports sintéticos sorteados (``ExportSpec(seed=…)``) con las dos disposiciones; la vista sale de ``plano_red.vista``.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import random

import pytest

from convertersmartgrid import dgs
from convertersmartgrid.geography import build_geography, geography_to_dict
from convertersmartgrid.model import build_feeder_model
from convertersmartgrid.plano_red import revision_red, vista
from synthetic_export import CRS_SINTETICO, ExportSpec, load_export

LAYOUTS = ('reducido', 'completo')


def _variacion():
    assert importlib.util.find_spec('convertersmartgrid.variacion_plano') is not None, \
        'falta convertersmartgrid.variacion_plano'
    return importlib.import_module('convertersmartgrid.variacion_plano')


#: Intentos de sorteo hasta una red que sirva a la prueba (FIX-111-PRUEBAS v3, lección B6 del 2026-11-16).
INTENTOS = 20


def _util(v) -> bool:
    """Lo que casi todas las pruebas toman de la vista sin mirar: una barra con coordenadas, una maniobra, un tramo y un
    tipo de línea. Una red sorteada sin alguno no prueba nada: se sortea otra."""
    return (any(b['lat'] is not None for b in v['barras']) and bool(v['maniobras']) and bool(v['tramos'])
            and bool(v['tipos_de_linea']))


def _entrega(tmp_path, layout='reducido', exige=_util, **kw):
    """Una entrega convertida en ``salida/`` (DGS y geografía) y la vista y la revisión de su alimentador con más tramos.

    Sortea semillas hasta que la vista cumple ``exige`` (como mucho ``INTENTOS``), cada una en su carpeta; la semilla se
    imprime siempre, así que sale en el informe de cualquier fallo, y va en el mensaje de las aserciones (lección B6)."""
    probadas = []
    for intento in range(INTENTOS):
        e = _una_entrega(tmp_path / f'intento_{intento}', layout, **kw)
        probadas.append(e['semilla'])
        if exige(e['vista']):
            print(f'semilla={e["semilla"]} (intento {intento + 1} de {INTENTOS}; descartadas: {probadas[:-1]})')
            return e
    raise AssertionError(f'ninguna de {INTENTOS} redes sorteadas sirve a la prueba: semillas {probadas}')


def _una_entrega(tmp_path, layout, **kw):
    seed = random.SystemRandom().randrange(1, 2 ** 31)
    spec = ExportSpec(feeders=random.Random(seed).randint(2, 4), seed=seed, layout=layout,
                      sections_per_feeder=6, switches_per_feeder=2, **kw)
    ds = load_export(spec, tmp_path / f'export_{seed}')
    salida = tmp_path / 'salida'
    salida.mkdir(parents=True)
    rutas, vistas, modelos = {}, {}, {}
    for net in ds.feeder_ids():
        modelo = build_feeder_model(ds, net, strict=True, include_geography=True)
        geo = geography_to_dict(build_geography(ds, modelo, source_crs=CRS_SINTETICO), modelo)
        rutas[modelo.name] = salida / f'{modelo.name}_geography.json'
        rutas[modelo.name].write_text(json.dumps(geo), encoding='utf-8')
        dgs.write_dgs(modelo, salida / f'{modelo.name}.dgs')
        vistas[modelo.name], modelos[modelo.name] = vista(modelo, geo), modelo
    nombre = max(vistas, key=lambda n: len(vistas[n]['tramos']))
    return {'salida': salida, 'vista': vistas[nombre], 'modelo': modelos[nombre], 'semilla': seed,
            'revision': revision_red(f'run-{seed}', rutas), 'espacio': tmp_path / 'espacio'}


def _huellas(carpeta):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(carpeta.rglob('*')) if p.is_file()}


def _barra(v, i=0):
    b = next((b for b in v['barras'][i:] if b['lat'] is not None), None)
    assert b is not None, 'la vista sorteada no tiene una barra con coordenadas (la semilla va en la salida de la prueba)'
    return b


# ------------------------------------------------------------------------------------- maniobra y tramo (T5)

@pytest.mark.parametrize('layout', LAYOUTS)
def test_111_rf4_maniobra_como_variacion_y_nunca_en_el_caso_base(tmp_path, layout):
    """111:RF-4 — abrir un seccionador queda como edición de la variación, con versión y la revisión de partida, en
    ``<espacio>/variaciones_plano``; el DGS y la geografía de la entrega conservan su huella."""
    vp = _variacion()
    assert hasattr(vp, 'nueva') and hasattr(vp, 'editar'), 'falta variacion_plano.nueva o editar'
    e = _entrega(tmp_path, layout)
    antes = _huellas(e['salida'])
    v = vp.nueva(e['espacio'], revision=e['revision'], caso='Caso base', alimentador=e['vista']['alimentador'])
    assert v['version'] == 0 and v['estado'] == 'abierta' and v['ediciones'] == []
    m = e['vista']['maniobras'][0]
    nuevo = 'abierto' if m['estado'] == 'cerrado' else 'cerrado'
    v = vp.editar(e['espacio'], v['id'], {'tipo': 'maniobra', 'codigo': m['codigo'], 'estado': nuevo},
                  version=0, revision=e['revision'], vista=e['vista'])
    assert v['version'] == 1 and v['revision'] == e['revision'] and v['caso'] == 'Caso base'
    assert v['ediciones'] == [{'tipo': 'maniobra', 'codigo': m['codigo'], 'estado': nuevo, 'antes': m['estado']}]
    guardada = json.loads((e['espacio'] / 'variaciones_plano' / f'{v["id"]}.json').read_text(encoding='utf-8'))
    assert guardada == v == vp.leer(e['espacio'], v['id'])
    assert _huellas(e['salida']) == antes, f'semilla={e["semilla"]}'
    assert not list(e['salida'].rglob('variaciones_plano'))


def test_111_rf4_maniobra_que_no_existe_o_estado_imposible_se_rechaza_con_su_motivo(tmp_path):
    """111:RF-4 — una maniobra que no está en el plano, o un estado que no es abierto ni cerrado, no entra y se dice."""
    vp = _variacion()
    assert hasattr(vp, 'VariacionError'), 'falta variacion_plano.VariacionError'
    e = _entrega(tmp_path)
    v = vp.nueva(e['espacio'], revision=e['revision'], caso='Caso base', alimentador=e['vista']['alimentador'])
    with pytest.raises(vp.VariacionError, match='no está en el plano'):
        vp.editar(e['espacio'], v['id'], {'tipo': 'maniobra', 'codigo': '__NADA__', 'estado': 'abierto'},
                  version=0, revision=e['revision'], vista=e['vista'])
    with pytest.raises(vp.VariacionError, match='abierto o cerrado'):
        vp.editar(e['espacio'], v['id'], {'tipo': 'maniobra', 'codigo': e['vista']['maniobras'][0]['codigo'],
                                          'estado': 'medio'}, version=0, revision=e['revision'], vista=e['vista'])
    assert vp.leer(e['espacio'], v['id'])['version'] == 0


def test_111_rf4_maniobra_sobre_otra_revision_o_version_es_conflicto_y_se_conserva(tmp_path):
    """111:RF-4 — una edición sobre una revisión de la red que cambió, o con una versión vieja, es un conflicto: no se
    aplica, y la variación se conserva marcada (la de otra revisión no se estudia)."""
    vp = _variacion()
    assert hasattr(vp, 'ConflictoVariacion'), 'falta variacion_plano.ConflictoVariacion'
    e = _entrega(tmp_path)
    v = vp.nueva(e['espacio'], revision=e['revision'], caso='Caso base', alimentador=e['vista']['alimentador'])
    edicion = {'tipo': 'maniobra', 'codigo': e['vista']['maniobras'][0]['codigo'], 'estado': 'abierto'}
    with pytest.raises(vp.ConflictoVariacion, match='versión'):
        vp.editar(e['espacio'], v['id'], edicion, version=7, revision=e['revision'], vista=e['vista'])
    with pytest.raises(vp.ConflictoVariacion, match='revisión'):
        vp.editar(e['espacio'], v['id'], edicion, version=0, revision='otra', vista=e['vista'])
    guardada = vp.leer(e['espacio'], v['id'])
    assert guardada['ediciones'] == [] and guardada['revision_cambiada'] is True


@pytest.mark.parametrize('layout', LAYOUTS)
def test_111_rf5_tramo_nuevo_guarda_sus_vertices_y_las_dos_longitudes(tmp_path, layout):
    """111:RF-5 — un tramo nuevo guarda los vértices tal como se dibujaron, la longitud GIS geodésica y la eléctrica
    aparte; sin la eléctrica, vale la GIS y lo dice."""
    vp = _variacion()
    assert hasattr(vp, 'editar'), 'falta variacion_plano.editar'
    from pyproj import Geod
    e = _entrega(tmp_path, layout)
    b = _barra(e['vista'])
    dibujo = [[b['lat'], b['lon']], [b['lat'] + 0.0011, b['lon'] + 0.0007], [b['lat'] + 0.0023, b['lon'] + 0.0002]]
    conductor = e['vista']['tipos_de_linea'][0]
    v = vp.nueva(e['espacio'], revision=e['revision'], caso='Caso base', alimentador=e['vista']['alimentador'])
    v = vp.editar(e['espacio'], v['id'], {'tipo': 'tramo', 'codigo': 'NUEVO_1', 'desde': b['codigo'],
                                          'vertices': dibujo, 'conductor': conductor, 'fases': 'ABC'},
                  version=0, revision=e['revision'], vista=e['vista'])
    t = v['ediciones'][-1]
    assert t['vertices'] == dibujo
    gis = Geod(ellps='WGS84').line_length([p[1] for p in dibujo], [p[0] for p in dibujo])
    assert t['longitud_gis_m'] == pytest.approx(gis, rel=1e-9)
    assert t['longitud_electrica_m'] is None and t['longitud_electrica_origen'] == 'gis'
    assert t['desde'] == b['codigo'] and t['hasta'] and t['hasta_nuevo'] is True
    v = vp.editar(e['espacio'], v['id'], {'tipo': 'tramo', 'codigo': 'NUEVO_2', 'desde': t['hasta'],
                                          'vertices': dibujo[::-1], 'conductor': conductor, 'fases': 'AB',
                                          'longitud_electrica_m': 512.5},
                  version=1, revision=e['revision'], vista=e['vista'])
    t2 = v['ediciones'][-1]
    assert t2['longitud_electrica_m'] == 512.5 and t2['longitud_electrica_origen'] == 'operador'
    assert t2['longitud_gis_m'] == pytest.approx(gis, rel=1e-9)


def test_111_rf5_tramo_nuevo_incompleto_o_repetido_no_entra(tmp_path):
    """111:RF-5 — un tramo con un código que ya existe, sin origen en el plano, con menos de dos vértices, con un
    conductor que no es del catálogo o con fases imposibles no entra, y se dice por qué."""
    vp = _variacion()
    assert hasattr(vp, 'VariacionError'), 'falta variacion_plano.VariacionError'
    e = _entrega(tmp_path)
    b = _barra(e['vista'])
    bueno = {'tipo': 'tramo', 'codigo': 'NUEVO_1', 'desde': b['codigo'], 'conductor': e['vista']['tipos_de_linea'][0],
             'vertices': [[b['lat'], b['lon']], [b['lat'] + 0.001, b['lon']]], 'fases': 'ABC'}
    v = vp.nueva(e['espacio'], revision=e['revision'], caso='Caso base', alimentador=e['vista']['alimentador'])
    for cambio, motivo in (({'codigo': e['vista']['tramos'][0]['codigo']}, 'ya existe'),
                           ({'desde': '__NADA__'}, 'origen'),
                           ({'vertices': [[b['lat'], b['lon']]]}, 'dos vértices'),
                           ({'vertices': [[b['lat'], b['lon']], [200.0, 0.0]]}, 'coordenadas'),
                           ({'conductor': '__NADA__'}, 'conductor'),
                           ({'fases': 'XYZ'}, 'fases'),
                           ({'longitud_electrica_m': -3}, 'longitud')):
        with pytest.raises(vp.VariacionError, match=motivo):
            vp.editar(e['espacio'], v['id'], {**bueno, **cambio}, version=0, revision=e['revision'], vista=e['vista'])
    assert vp.leer(e['espacio'], v['id'])['ediciones'] == []


# --------------------------------------------------------------------------- reglas de topología (T6)

def _cruce_y_barra(v):
    """El cruce de ``_cruce`` y una barra de origen que no sea de los extremos del tramo cruzado; ``None`` si la red
    sorteada no los tiene (StopIteration en la puerta F v10: el ``next`` sin valor por defecto caía antes del assert)."""
    try:
        cruzado, dibujo = _cruce(v)
    except AssertionError:
        return None
    b = next((x for x in v['barras'] if x['codigo'] not in (cruzado['desde'], cruzado['hasta'])), None)
    return None if b is None else (cruzado, dibujo, b)


def _cruce(v):
    """Un tramo existente con dos vértices distintos seguidos y el segmento perpendicular que lo cruza en su mitad."""
    for t in v['tramos']:
        for a, b in zip(t['vertices'], t['vertices'][1:]):
            if a != b:
                m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
                d = [-(b[1] - a[1]), b[0] - a[0]]
                return t, [[m[0] + d[0], m[1] + d[1]], [m[0] - d[0], m[1] - d[1]]]
    raise AssertionError('la entrega sorteada no tiene un tramo con trazo')


def test_111_rf6_un_cruce_sin_nodo_ni_equipo_no_conecta(tmp_path):
    """111:RF-6 — un tramo nuevo que cruza otro en el plano solo se une por sus nodos de origen y de destino; el cruce
    se dice y no crea ninguna unión."""
    vp = _variacion()
    assert hasattr(vp, 'editar'), 'falta variacion_plano.editar'
    e = _entrega(tmp_path, exige=lambda v: _util(v) and _cruce_y_barra(v) is not None)
    cruzado, dibujo, b = _cruce_y_barra(e['vista'])
    v = vp.nueva(e['espacio'], revision=e['revision'], caso='Caso base', alimentador=e['vista']['alimentador'])
    v = vp.editar(e['espacio'], v['id'], {'tipo': 'tramo', 'codigo': 'CRUCE_1', 'desde': b['codigo'],
                                          'vertices': dibujo, 'conductor': e['vista']['tipos_de_linea'][0],
                                          'fases': 'ABC'}, version=0, revision=e['revision'], vista=e['vista'])
    t = v['ediciones'][-1]
    assert 'cruza_sin_unir' in t, 'falta la lista de cruces sin unión'
    assert cruzado['codigo'] in t['cruza_sin_unir'], f'semilla={e["semilla"]}'
    assert t['conecta'] == sorted({b['codigo'], t['hasta']}), f'semilla={e["semilla"]}'
    assert cruzado['desde'] not in t['conecta'] and cruzado['hasta'] not in t['conecta'], f'semilla={e["semilla"]}'


def _lejana(v, b):
    from pyproj import Geod
    g = Geod(ellps='WGS84')
    return max((c for c in v['barras'] if c['lat'] is not None and c['codigo'] != b['codigo']),
               key=lambda c: g.inv(b['lon'], b['lat'], c['lon'], c['lat'])[2])


def test_111_rf7_ajuste_a_un_nodo_cercano_es_una_propuesta_con_su_distancia(tmp_path):
    """111:RF-7 — el extremo de un tramo nuevo cerca de un nodo da una propuesta con la distancia y el radio del perfil
    (``editor_ajuste_m``; sin perfil, 5 m y lo dice); solo se aplica confirmada y mueve el extremo al nodo."""
    vp = _variacion()
    assert hasattr(vp, 'proponer_ajuste'), 'falta variacion_plano.proponer_ajuste'
    e = _entrega(tmp_path)
    b = _barra(e['vista'])
    c = _lejana(e['vista'], b)
    cerca = [c['lat'] + 10.0 / 111_320.0, c['lon']]
    v = vp.nueva(e['espacio'], revision=e['revision'], caso='Caso base', alimentador=e['vista']['alimentador'])
    v = vp.editar(e['espacio'], v['id'], {'tipo': 'tramo', 'codigo': 'AJ_1', 'desde': b['codigo'],
                                          'vertices': [[b['lat'], b['lon']], cerca],
                                          'conductor': e['vista']['tipos_de_linea'][0], 'fases': 'ABC'},
                  version=0, revision=e['revision'], vista=e['vista'])
    sin_perfil = vp.proponer_ajuste(e['vista'], v, cerca)
    assert sin_perfil['nodo'] is None and sin_perfil['radio_m'] == 5.0 and sin_perfil['radio_origen'] == 'por defecto'
    perfil = {'editor_ajuste_m': 30.0}
    p = vp.proponer_ajuste(e['vista'], v, cerca, perfil=perfil)
    assert p['nodo'] == c['codigo'] and p['radio_m'] == 30.0 and p['radio_origen'] == 'perfil'
    assert p['distancia_m'] == pytest.approx(10.0, abs=0.2)
    ajuste = {'tipo': 'ajuste', 'tramo': 'AJ_1', 'extremo': 'hasta', 'nodo': c['codigo']}
    with pytest.raises(vp.VariacionError, match='propuesta'):
        vp.editar(e['espacio'], v['id'], ajuste, version=1, revision=e['revision'], vista=e['vista'], perfil=perfil)
    with pytest.raises(vp.VariacionError, match='radio'):
        vp.editar(e['espacio'], v['id'], {**ajuste, 'confirmado': True}, version=1, revision=e['revision'],
                  vista=e['vista'])
    v = vp.editar(e['espacio'], v['id'], {**ajuste, 'confirmado': True}, version=1, revision=e['revision'],
                  vista=e['vista'], perfil=perfil)
    a = v['ediciones'][-1]
    assert a['desplazamiento_m'] == pytest.approx(10.0, abs=0.2) and a['antes'] == 'AJ_1_FIN'
    tramo = vp.tramos_nuevos(e['vista'], v)['AJ_1']
    assert tramo['hasta'] == c['codigo'] and tramo['vertices'][-1] == [c['lat'], c['lon']]


def test_111_rf7_el_radio_de_ajuste_es_una_clave_del_perfil():
    """111:RF-7 — ``editor_ajuste_m`` está en el esquema del perfil: positivo, y un valor imposible es un error."""
    from convertersmartgrid.perfil_esquema import claves_del_esquema, validar_perfil
    assert 'editor_ajuste_m' in claves_del_esquema()
    assert validar_perfil({'editor_ajuste_m': 8}).errores == []
    assert validar_perfil({'editor_ajuste_m': -1}).errores


# ------------------------------------------------------------------------------------------- equipos (T7)

def _equipo(e, **cambios):
    t = e['vista']['tramos'][0]
    return {'tipo': 'equipo', 'codigo': 'EQ_NUEVO', 'clase': 'seccionador', 'tramo': t['codigo'], 'extremo': 'desde',
            'tension_kv': e['vista']['kv'], 'fases': t['fases'], 'estado': 'cerrado', **cambios}


def test_111_rf8_equipo_insertado_con_tension_fases_y_conexion_validas(tmp_path):
    """111:RF-8 — un equipo con su tensión, sus fases y su conexión a un tramo del plano entra en la variación."""
    vp = _variacion()
    assert hasattr(vp, 'CLASES_EQUIPO'), 'falta variacion_plano.CLASES_EQUIPO'
    e = _entrega(tmp_path)
    v = vp.nueva(e['espacio'], revision=e['revision'], caso='Caso base', alimentador=e['vista']['alimentador'])
    v = vp.editar(e['espacio'], v['id'], _equipo(e), version=0, revision=e['revision'], vista=e['vista'])
    eq = v['ediciones'][-1]
    t = e['vista']['tramos'][0]
    assert eq['codigo'] == 'EQ_NUEVO' and eq['barra'] == t['desde'] and eq['tension_kv'] == e['vista']['kv']
    v = vp.editar(e['espacio'], v['id'], {'tipo': 'maniobra', 'codigo': 'EQ_NUEVO', 'estado': 'abierto'},
                  version=1, revision=e['revision'], vista=e['vista'])
    assert v['ediciones'][-1]['antes'] == 'cerrado'


def test_111_rf8_un_equipo_sin_parametros_no_se_acepta_y_dice_que_falta(tmp_path):
    """111:RF-8 — sin parámetros, con otra tensión, con fases que su tramo no tiene o colgado de un tramo que no existe,
    el equipo no entra y la respuesta lista lo que falta."""
    vp = _variacion()
    assert hasattr(vp, 'CLASES_EQUIPO'), 'falta variacion_plano.CLASES_EQUIPO'
    e = _entrega(tmp_path)
    v = vp.nueva(e['espacio'], revision=e['revision'], caso='Caso base', alimentador=e['vista']['alimentador'])
    with pytest.raises(vp.VariacionError) as vacio:
        vp.editar(e['espacio'], v['id'], {'tipo': 'equipo', 'codigo': 'EQ_X'}, version=0, revision=e['revision'],
                  vista=e['vista'])
    assert {f.split(':')[0] for f in vacio.value.faltan} == {'clase', 'tramo', 'tensión', 'fases', 'estado'}
    t = e['vista']['tramos'][0]
    otra = [x for x in 'ABC' if x not in t['fases']]
    casos = [({'tension_kv': e['vista']['kv'] * 2}, 'tensión'), ({'tramo': '__NADA__'}, 'tramo'),
             ({'clase': 'reactor_magico'}, 'clase'), ({'codigo': e['vista']['maniobras'][0]['codigo']}, 'código')]
    if otra:
        casos.append(({'fases': 'ABC'}, 'fases'))
    for cambio, falta in casos:
        with pytest.raises(vp.VariacionError) as err:
            vp.editar(e['espacio'], v['id'], _equipo(e, **cambio), version=0, revision=e['revision'], vista=e['vista'])
        assert [f for f in err.value.faltan if f.startswith(falta)], (cambio, err.value.faltan)
    assert vp.leer(e['espacio'], v['id'])['ediciones'] == []


# ---------------------------------------------------------------------------------- deshacer y rehacer (T8)

def _dos_ediciones(vp, e):
    v = vp.nueva(e['espacio'], revision=e['revision'], caso='Caso base', alimentador=e['vista']['alimentador'])
    m = e['vista']['maniobras'][0]
    otro = 'abierto' if m['estado'] == 'cerrado' else 'cerrado'
    v = vp.editar(e['espacio'], v['id'], {'tipo': 'maniobra', 'codigo': m['codigo'], 'estado': otro},
                  version=0, revision=e['revision'], vista=e['vista'])
    v = vp.editar(e['espacio'], v['id'], {'tipo': 'maniobra', 'codigo': m['codigo'], 'estado': m['estado']},
                  version=1, revision=e['revision'], vista=e['vista'])
    return v


def test_111_rf9_deshacer_y_rehacer_las_ediciones_sin_confirmar(tmp_path):
    """111:RF-9 — deshacer quita la última edición y rehacer la devuelve, cada paso con una versión más y guardado; una
    edición nueva vacía lo que se podía rehacer; sin nada que deshacer o rehacer, se dice."""
    vp = _variacion()
    assert hasattr(vp, 'deshacer') and hasattr(vp, 'rehacer'), 'falta variacion_plano.deshacer o rehacer'
    e = _entrega(tmp_path)
    v = _dos_ediciones(vp, e)
    hechas = list(v['ediciones'])
    v = vp.deshacer(e['espacio'], v['id'], version=2, revision=e['revision'])
    assert v['ediciones'] == hechas[:1] and v['deshechas'] == hechas[1:] and v['version'] == 3
    v = vp.deshacer(e['espacio'], v['id'], version=3, revision=e['revision'])
    assert v['ediciones'] == [] and v['deshechas'] == hechas[::-1]
    with pytest.raises(vp.VariacionError, match='deshacer'):
        vp.deshacer(e['espacio'], v['id'], version=4, revision=e['revision'])
    v = vp.rehacer(e['espacio'], v['id'], version=4, revision=e['revision'])
    assert v['ediciones'] == hechas[:1] and v['version'] == 5
    assert vp.leer(e['espacio'], v['id']) == v
    v = vp.editar(e['espacio'], v['id'], {'tipo': 'maniobra', 'codigo': hechas[0]['codigo'], 'estado': hechas[0]['antes']},
                  version=5, revision=e['revision'], vista=e['vista'])
    assert v['deshechas'] == []
    with pytest.raises(vp.VariacionError, match='rehacer'):
        vp.rehacer(e['espacio'], v['id'], version=6, revision=e['revision'])
    with pytest.raises(vp.ConflictoVariacion):
        vp.deshacer(e['espacio'], v['id'], version=2, revision=e['revision'])


def test_111_rf9_al_confirmar_el_diario_queda_cerrado_sin_deshacer_ni_rehacer(tmp_path):
    """111:RF-9 — confirmada, la variación ya no se edita, ni se deshace ni se rehace; lo que quedaba por rehacer se
    descarta y se dice cuántas ediciones lleva."""
    vp = _variacion()
    assert hasattr(vp, 'confirmar'), 'falta variacion_plano.confirmar'
    e = _entrega(tmp_path)
    v = _dos_ediciones(vp, e)
    v = vp.deshacer(e['espacio'], v['id'], version=2, revision=e['revision'])
    v = vp.confirmar(e['espacio'], v['id'], version=3, revision=e['revision'])
    assert v['estado'] == 'confirmada' and v['deshechas'] == [] and len(v['ediciones']) == 1 and v['version'] == 4
    for accion in (lambda: vp.deshacer(e['espacio'], v['id'], version=4, revision=e['revision']),
                   lambda: vp.rehacer(e['espacio'], v['id'], version=4, revision=e['revision']),
                   lambda: vp.confirmar(e['espacio'], v['id'], version=4, revision=e['revision']),
                   lambda: vp.editar(e['espacio'], v['id'], {'tipo': 'maniobra', 'codigo': 'x', 'estado': 'abierto'},
                                     version=4, revision=e['revision'], vista=e['vista'])):
        with pytest.raises(vp.VariacionError, match='confirmada'):
            accion()
    assert vp.leer(e['espacio'], v['id'])['version'] == 4
