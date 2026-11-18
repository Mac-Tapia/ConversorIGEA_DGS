"""Spec 111: los resultados sobre el plano. Resultado por elemento con el motor abierto, la variación aplicada a una
copia del modelo, la elección del motor, las capas con su umbral y la comparación de dos casos (111:RF-4, RF-10 a
RF-13, RF-17 a RF-19).

Exports sintéticos sorteados (``ExportSpec(seed=…)``) con las dos disposiciones; sin DIgSILENT.
"""
from __future__ import annotations

import copy
import dataclasses
import importlib
import importlib.util
import random

import pytest

pytest.importorskip('pandapower')

from convertersmartgrid.adaptadores import oraculo  # noqa: E402
from convertersmartgrid.aplicacion import variacion_plano as vp  # noqa: E402
from convertersmartgrid.adaptadores.geography import build_geography, geography_to_dict  # noqa: E402
from convertersmartgrid.dominio.model import build_feeder_model  # noqa: E402
from convertersmartgrid.adaptadores.plano_red import vista  # noqa: E402
from synthetic_export import CRS_SINTETICO, ExportSpec, load_export  # noqa: E402

LAYOUTS = ('reducido', 'completo')


def _resultados():
    assert importlib.util.find_spec('convertersmartgrid.adaptadores.resultados_plano') is not None, \
        'falta convertersmartgrid.adaptadores.resultados_plano'
    return importlib.import_module('convertersmartgrid.adaptadores.resultados_plano')


def _red(tmp_path, layout='reducido'):
    """El alimentador con más tramos de un export sorteado: su modelo y su vista."""
    seed = random.SystemRandom().randrange(1, 2 ** 31)
    spec = ExportSpec(feeders=random.Random(seed).randint(2, 4), seed=seed, layout=layout, sections_per_feeder=6,
                      switches_per_feeder=2)
    ds = load_export(spec, tmp_path / f'export_{seed}')
    pares = []
    for net in ds.feeder_ids():
        modelo = build_feeder_model(ds, net, strict=True, include_geography=True)
        pares.append((modelo, vista(modelo, geography_to_dict(build_geography(ds, modelo, source_crs=CRS_SINTETICO), modelo))))
    modelo, v = max(pares, key=lambda p: len(p[0].lines))
    return modelo, v, seed


# ------------------------------------------------------------------------------- motor abierto (T9)

@pytest.mark.parametrize('layout', LAYOUTS)
def test_111_rf10_el_motor_abierto_da_el_resultado_de_cada_elemento(tmp_path, layout):
    """111:RF-10 — tensión por barra, corriente y cargabilidad por tramo y estado de cada maniobra, con los códigos de
    la fuente; sin tocar el modelo."""
    assert hasattr(oraculo, 'resultados_por_elemento'), 'falta oraculo.resultados_por_elemento'
    modelo, _v, seed = _red(tmp_path, layout)
    antes = copy.deepcopy(modelo)
    r = oraculo.resultados_por_elemento(modelo)
    assert r['convergio'], (seed, r['mensajes'])
    assert sorted(r['barras']) == sorted(modelo.nodes)
    assert sorted(r['tramos']) == sorted(ln.section_id for ln in modelo.lines)
    con_tension = [b for b in r['barras'].values() if b['u_pu'] is not None]
    assert con_tension and all(0.5 < b['u_pu'] < 1.5 and b['kv'] > 0 for b in con_tension)
    for t in r['tramos'].values():
        assert t['como_conexion'] or (t['i_a'] is not None and t['i_a'] >= 0 and t['carga_pct'] >= 0)
    assert {m['estado'] for m in r['equipos'].values()} <= {'abierto', 'cerrado'}
    assert len(r['equipos']) == len({d.eq_number or d.eq_id or d.section_id for d in modelo.devices})
    assert modelo == antes


def test_111_rf11_si_el_flujo_no_converge_no_hay_resultado_que_pintar(tmp_path):
    """111:RF-11 — sin convergencia no hay valores por elemento, y se dan los mensajes del motor."""
    assert hasattr(oraculo, 'resultados_por_elemento'), 'falta oraculo.resultados_por_elemento'
    modelo, _v, _seed = _red(tmp_path)
    roto = dataclasses.replace(modelo, loads=[dataclasses.replace(c, p_mw=c.p_mw * 1e5 + 50.0, q_mvar=c.q_mvar * 1e5)
                                              for c in modelo.loads])
    r = oraculo.resultados_por_elemento(roto)
    assert r['convergio'] is False and r['barras'] == {} and r['tramos'] == {}
    assert r['mensajes'] and all(isinstance(m, str) and m for m in r['mensajes'])


def test_111_rf17_la_variacion_se_estudia_con_el_motor_abierto_sobre_una_copia(tmp_path):
    """111:RF-4, 111:RF-17, 111:RF-18 — la maniobra, el tramo nuevo y el equipo se aplican a una copia del modelo; el
    resultado dice el motor, el caso, la revisión y la versión de la variación."""
    rp = _resultados()
    assert hasattr(rp, 'estudiar'), 'falta resultados_plano.estudiar'
    modelo, v, seed = _red(tmp_path)
    antes = copy.deepcopy(modelo)
    espacio = tmp_path / 'espacio'
    var = vp.nueva(espacio, revision='rev-1', caso='Caso base', alimentador=v['alimentador'])
    m = v['maniobras'][0]
    otro = 'abierto' if m['estado'] == 'cerrado' else 'cerrado'
    var = vp.editar(espacio, var['id'], {'tipo': 'maniobra', 'codigo': m['codigo'], 'estado': otro},
                    version=0, revision='rev-1', vista=v)
    b = next((x for x in v['barras'] if x['lat'] is not None), None)
    assert b is not None, f'la red sorteada no tiene una barra con coordenadas: semilla={seed}'
    var = vp.editar(espacio, var['id'], {'tipo': 'tramo', 'codigo': 'NUEVO_1', 'desde': b['codigo'],
                                         'vertices': [[b['lat'], b['lon']], [b['lat'] + 0.001, b['lon']]],
                                         'conductor': v['tipos_de_linea'][0], 'fases': 'ABC'},
                    version=1, revision='rev-1', vista=v)
    var = vp.editar(espacio, var['id'], {'tipo': 'equipo', 'codigo': 'EQ_1', 'clase': 'seccionador', 'tramo': 'NUEVO_1',
                                         'extremo': 'desde', 'tension_kv': v['kv'], 'fases': 'ABC', 'estado': 'cerrado'},
                    version=2, revision='rev-1', vista=v)
    r = rp.estudiar(modelo, v, var)
    assert r['motor'] == 'abierto' and r['caso'] == 'Caso base' and r['revision'] == 'rev-1'
    assert r['variacion'] == var['id'] and r['version'] == 3 and r['alimentador'] == modelo.name
    assert r['convergio'], (seed, r['mensajes'])
    assert r['equipos'][m['codigo']]['estado'] == otro and r['equipos']['EQ_1']['estado'] == 'cerrado'
    assert 'NUEVO_1' in r['tramos'] and 'NUEVO_1_FIN' in r['barras']
    assert modelo == antes
    copia = rp.aplicar_variacion(modelo, v, var)
    assert copia is not modelo and len(copia.lines) == len(modelo.lines) + 1
    assert copia.section_by_id['NUEVO_1'].length_m == pytest.approx(var['ediciones'][1]['longitud_gis_m'])
    base = rp.estudiar(modelo, v, None, caso='Caso base', revision='rev-1')
    assert base['variacion'] is None and base['equipos'][m['codigo']]['estado'] == m['estado']


def test_111_rf11_una_variacion_de_otra_revision_no_se_estudia_con_el_motor_abierto(tmp_path):
    """111:RF-11 — una variación marcada porque la revisión de la red cambió no se estudia: se dice por qué."""
    rp = _resultados()
    assert hasattr(rp, 'estudiar'), 'falta resultados_plano.estudiar'
    modelo, v, _seed = _red(tmp_path)
    var = vp.nueva(tmp_path / 'e', revision='rev-1', caso='Caso base', alimentador=v['alimentador'])
    with pytest.raises(vp.ConflictoVariacion):
        vp.editar(tmp_path / 'e', var['id'], {'tipo': 'maniobra', 'codigo': v['maniobras'][0]['codigo'],
                                              'estado': 'abierto'}, version=0, revision='rev-2', vista=v)
    with pytest.raises(vp.ConflictoVariacion, match='revisión'):
        rp.estudiar(modelo, v, vp.leer(tmp_path / 'e', var['id']))


def test_111_rf17_digsilent_con_licencia_y_proyecto_vinculado_si_no_el_abierto():
    """111:RF-17, 111:RF-18 — DIgSILENT solo con licencia y el proyecto vinculado a esta red; si no, el motor abierto,
    y siempre se dice cuál y por qué."""
    rp = _resultados()
    assert hasattr(rp, 'elegir_motor'), 'falta resultados_plano.elegir_motor'
    assert rp.elegir_motor(licencia=True, vinculado=True)['motor'] == 'DIgSILENT'
    for licencia, vinculado in ((False, True), (True, False), (False, False)):
        e = rp.elegir_motor(licencia=licencia, vinculado=vinculado)
        assert e['motor'] == 'abierto' and e['motivo'] and e['texto']


# ------------------------------------------------------------------------------------------ capas (T10)

def _base(tmp_path, layout='reducido'):
    rp = _resultados()
    modelo, v, seed = _red(tmp_path, layout)
    r = rp.estudiar(modelo, v, None, caso='Caso base', revision='rev-1')
    assert r['convergio'], (seed, r['mensajes'])
    return rp, modelo, v, r


@pytest.mark.parametrize('layout', LAYOUTS)
def test_111_rf10_cada_capa_lleva_su_unidad_umbral_caso_y_motor(tmp_path, layout):
    """111:RF-10, 111:RF-18 — tensión por barra, corriente y cargabilidad por tramo y estado de cada equipo, con su
    leyenda: magnitud, unidad, umbral y su origen, caso, revisión y motor; junto a cada valor, el motor."""
    rp = _resultados()
    assert hasattr(rp, 'capas'), 'falta resultados_plano.capas'
    from convertersmartgrid.aplicacion.estudios_pf import LIMITES_POR_DEFECTO
    _rp, _modelo, _v, r = _base(tmp_path, layout)
    c = rp.capas(r, limites=LIMITES_POR_DEFECTO, revision='rev-1', caso='Caso base')
    assert c['pintable'] and set(c['capas']) == {'tension', 'corriente', 'cargabilidad', 'estado'}
    unidades = {'tension': 'p.u.', 'corriente': 'A', 'cargabilidad': '%', 'estado': ''}
    for nombre, capa in c['capas'].items():
        ley = capa['leyenda']
        assert ley['unidad'] == unidades[nombre] and ley['magnitud']
        assert ley['caso'] == 'Caso base' and ley['revision'] == 'rev-1' and ley['motor'] == 'abierto'
        assert ley['motor_texto'] == 'motor abierto (pandapower)' and ley['origen_umbral'] == 'por defecto'
        assert all(e['motor'] == 'abierto' for e in capa['elementos'])
    tension = {e['codigo']: e for e in c['capas']['tension']['elementos']}
    assert c['capas']['tension']['leyenda']['umbral'] == {'min': 0.95, 'max': 1.05}
    for codigo, b in r['barras'].items():
        assert tension[codigo]['valor'] == b['u_pu']
    carga = {e['codigo']: e for e in c['capas']['cargabilidad']['elementos']}
    assert c['capas']['cargabilidad']['leyenda']['umbral'] == {'max': 100.0}
    for codigo, t in r['tramos'].items():
        if t['carga_pct'] is not None:
            assert carga[codigo]['valor'] == t['carga_pct']
    estado = {e['codigo']: e['valor'] for e in c['capas']['estado']['elementos']}
    assert estado == {k: x['estado'] for k, x in r['equipos'].items()}


def test_111_rf13_un_incumplimiento_lleva_texto_icono_valor_y_umbral(tmp_path):
    """111:RF-13 — fuera del umbral del perfil, cada valor dice con texto, icono, valor y umbral que incumple, no solo
    con color; dentro, no lleva aviso. El umbral sale del perfil y la leyenda lo dice."""
    rp = _resultados()
    assert hasattr(rp, 'capas'), 'falta resultados_plano.capas'
    from convertersmartgrid.aplicacion.estudios_pf import limites_de_perfil
    _rp, _modelo, _v, r = _base(tmp_path)
    perfil = tmp_path / 'perfil.json'
    perfil.write_text('{"estudios": {"tension_min_pu": 0.9999, "tension_max_pu": 1.00001, '
                      '"cargabilidad_max_pct": 0.0001}}', encoding='utf-8')
    limites = limites_de_perfil(perfil)
    c = rp.capas(r, limites=limites, revision='rev-1', caso='Caso base')
    assert c['capas']['tension']['leyenda']['origen_umbral'] == 'perfil'
    assert c['capas']['tension']['leyenda']['umbral'] == {'min': 0.9999, 'max': 1.00001}
    vistos = 0
    for nombre in ('tension', 'cargabilidad'):
        for e in c['capas'][nombre]['elementos']:
            if e['incumple'] is None:
                assert e['banda'] in ('normal', 'sin_tension', 'sin_valor')
                continue
            vistos += 1
            i = e['incumple']
            assert i['icono'] == 'alerta' and i['valor'] == e['valor'] and i['umbral'] is not None
            assert i['texto'] and _coma(i['valor']) in i['texto'] and _coma(i['umbral']) in i['texto']
    assert vistos, 'con estos umbrales algo tiene que incumplir'


def _coma(x):
    texto = f'{x:.4f}'.rstrip('0').rstrip('.')
    return texto.replace('.', ',')


def test_111_rf11_una_capa_de_otra_revision_o_otro_caso_o_sin_convergencia_no_se_pinta(tmp_path):
    """111:RF-11 — solo se pinta lo que el motor calculó para ese caso y esa revisión; si no, se dice por qué."""
    rp = _resultados()
    assert hasattr(rp, 'capas'), 'falta resultados_plano.capas'
    from convertersmartgrid.aplicacion.estudios_pf import LIMITES_POR_DEFECTO
    _rp, _modelo, _v, r = _base(tmp_path)
    for kw, motivo in (({'revision': 'rev-2', 'caso': 'Caso base'}, 'revisión'),
                       ({'revision': 'rev-1', 'caso': 'Otro caso'}, 'caso')):
        c = rp.capas(r, limites=LIMITES_POR_DEFECTO, **kw)
        assert c['pintable'] is False and motivo in c['motivo'] and c['capas'] == {}
    roto = {**r, 'convergio': False, 'mensajes': ['el flujo de potencia no converge'], 'barras': {}, 'tramos': {}}
    c = rp.capas(roto, limites=LIMITES_POR_DEFECTO, revision='rev-1', caso='Caso base')
    assert c['pintable'] is False and 'convergió' in c['motivo'] and c['mensajes'] == roto['mensajes']


def _de_digsilent(modelo, r, *, extra=True):
    """Lo que guardaría ``tools/estudios_pf.geografia`` de ese mismo caso: nombres de DIgSILENT, no códigos."""
    from convertersmartgrid.adaptadores.dgs import nombre_en_pf
    barras = [[nombre_en_pf(n), -12.0, -77.0, (b['u_pu'] or 1.0) - 0.001, b['kv']] for n, b in r['barras'].items()]
    tramos = [[nombre_en_pf(s), [[-12.0, -77.0], [-12.001, -77.0]], (t['carga_pct'] or 0.0) + 1.0, 'b1', 'b2', 'tipo', 0.1]
              for s, t in r['tramos'].items()]
    if extra:
        barras.append(['__DE_OTRA_RED__', -12.0, -77.0, 1.0, 10.0])
    return {'barras': barras, 'tramos': tramos, 'acoples': [], 'cabecera': None}


def test_111_rf18_la_capa_de_digsilent_se_traduce_por_la_identidad(tmp_path):
    """111:RF-2, 111:RF-18 — los resultados de DIgSILENT se traducen al código de la fuente con la identidad; un nombre
    que no está, o que comparten dos códigos, no se pinta y se cuenta; la capa dice que los calculó DIgSILENT."""
    rp = _resultados()
    assert hasattr(rp, 'traducir_resultados_pf'), 'falta resultados_plano.traducir_resultados_pf'
    from convertersmartgrid.aplicacion.estudios_pf import LIMITES_POR_DEFECTO
    from convertersmartgrid.adaptadores.plano_red import identidad
    _rp, modelo, _v, r = _base(tmp_path)
    t = rp.traducir_resultados_pf(_de_digsilent(modelo, r), identidad(modelo), caso='Caso base', revision='rev-1')
    assert t['motor'] == 'DIgSILENT' and t['convergio'] and t['caso'] == 'Caso base' and t['revision'] == 'rev-1'
    assert sorted(t['barras']) == sorted(r['barras'])
    assert t['sin_codigo'] == {'barras': 1, 'tramos': 0, 'nombres': ['__DE_OTRA_RED__']}
    uno = next(iter(r['barras']))
    assert t['barras'][uno]['u_pu'] == pytest.approx((r['barras'][uno]['u_pu'] or 1.0) - 0.001)
    c = rp.capas(t, limites=LIMITES_POR_DEFECTO, revision='rev-1', caso='Caso base')
    assert c['pintable'] and c['capas']['tension']['leyenda']['motor_texto'] == 'DIgSILENT'
    assert all(e['motor'] == 'DIgSILENT' for e in c['capas']['cargabilidad']['elementos'])


# --------------------------------------------------------------------------------------- comparar (T11)

def _variante(rp, modelo, v, tmp_path):
    var = vp.nueva(tmp_path / 'e', revision='rev-1', caso='Caso base', alimentador=v['alimentador'])
    m = v['maniobras'][0]
    var = vp.editar(tmp_path / 'e', var['id'], {'tipo': 'maniobra', 'codigo': m['codigo'],
                                                'estado': 'abierto' if m['estado'] == 'cerrado' else 'cerrado'},
                    version=0, revision='rev-1', vista=v)
    return rp.estudiar(modelo, v, var), m['codigo']


def test_111_rf12_comparar_dos_casos_elemento_a_elemento_sobre_el_mismo_plano(tmp_path):
    """111:RF-12 — la diferencia de cada magnitud por elemento (B menos A), con la banda de cada caso."""
    rp = _resultados()
    assert hasattr(rp, 'comparar'), 'falta resultados_plano.comparar'
    from convertersmartgrid.aplicacion.estudios_pf import LIMITES_POR_DEFECTO
    _rp, modelo, v, a = _base(tmp_path)
    b, maniobra = _variante(rp, modelo, v, tmp_path)
    d = rp.comparar(a, b, limites=LIMITES_POR_DEFECTO)
    assert d['comparable'] and d['mismo_motor'] and d['aviso_motores'] is None
    assert d['casos'] == [{'caso': 'Caso base', 'variacion': None, 'motor': 'abierto'},
                          {'caso': 'Caso base', 'variacion': b['variacion'], 'motor': 'abierto'}]
    por = {(e['magnitud'], e['codigo']): e for e in d['elementos']}
    for codigo, x in a['barras'].items():
        e = por[('tension', codigo)]
        y = b['barras'][codigo]['u_pu']
        assert e['a'] == x['u_pu'] and e['b'] == y
        assert e['diferencia'] == (None if x['u_pu'] is None or y is None else pytest.approx(y - x['u_pu']))
        assert {e['banda_a'], e['banda_b']} <= {'baja', 'normal', 'alta', 'sin_tension'}
    e = por[('estado', maniobra)]
    assert e['a'] != e['b'] and e['diferencia'] is None


def test_111_rf19_comparar_dos_casos_de_motores_distintos_lo_dice(tmp_path):
    """111:RF-19 — si un caso se calculó con DIgSILENT y el otro con el motor abierto, la comparación lo dice."""
    rp = _resultados()
    assert hasattr(rp, 'comparar'), 'falta resultados_plano.comparar'
    from convertersmartgrid.aplicacion.estudios_pf import LIMITES_POR_DEFECTO
    from convertersmartgrid.adaptadores.plano_red import identidad
    _rp, modelo, _v, a = _base(tmp_path)
    b = rp.traducir_resultados_pf(_de_digsilent(modelo, a, extra=False), identidad(modelo), caso='Caso base',
                                  revision='rev-1')
    d = rp.comparar(a, b, limites=LIMITES_POR_DEFECTO)
    assert d['comparable'] and d['mismo_motor'] is False
    assert 'DIgSILENT' in d['aviso_motores'] and 'motor abierto' in d['aviso_motores']


def test_111_rf12_comparar_casos_de_otra_revision_o_sin_convergencia_no_es_comparable(tmp_path):
    """111:RF-12, 111:RF-11 — dos casos de revisiones distintas de la red, o uno que no convergió, no se comparan."""
    rp = _resultados()
    assert hasattr(rp, 'comparar'), 'falta resultados_plano.comparar'
    from convertersmartgrid.aplicacion.estudios_pf import LIMITES_POR_DEFECTO
    _rp, _modelo, _v, a = _base(tmp_path)
    d = rp.comparar(a, {**a, 'revision': 'rev-2'}, limites=LIMITES_POR_DEFECTO)
    assert d['comparable'] is False and 'revisión' in d['motivo'] and d['elementos'] == []
    d = rp.comparar(a, {**a, 'convergio': False}, limites=LIMITES_POR_DEFECTO)
    assert d['comparable'] is False and 'convergió' in d['motivo']


def test_111_rf10_capa_sin_tension_si_al_abrir_la_cabecera_nada_queda_alimentado(tmp_path):
    """111:RF-10, 111:RF-11 — abierta la maniobra de cabecera, el caso no es «no converge»: cada barra sale sin tensión
    (salvo la fuente, a su consigna) y la capa lo pinta así, con el motivo."""
    rp = _resultados()
    assert hasattr(rp, 'capas'), 'falta resultados_plano.capas'
    from convertersmartgrid.aplicacion.estudios_pf import LIMITES_POR_DEFECTO
    modelo, _v, seed = _red(tmp_path)
    cabecera = next((ln for ln in modelo.lines if ln.from_node == modelo.source_node), None)
    assert cabecera is not None, f'la red sorteada no tiene un tramo que salga de la fuente: semilla={seed}'
    otro = modelo.devices[0]
    abierta = dataclasses.replace(otro, section_id=cabecera.section_id, node_id=cabecera.from_node, terminal_side=0,
                                  eq_number='SW_CABECERA', eq_id='SW_CABECERA', on_off=0)
    roto = dataclasses.replace(modelo, devices=[*modelo.devices, abierta])
    r = oraculo.resultados_por_elemento(roto)
    assert r['convergio'] and r['equipos']['SW_CABECERA']['estado'] == 'abierto'
    sin = [n for n, b in r['barras'].items() if b['u_pu'] is None]
    assert modelo.source_node not in sin and len(sin) >= 1
    c = rp.capas({**r, 'motor': 'abierto', 'caso': 'c', 'revision': 'r'}, limites=LIMITES_POR_DEFECTO,
                 revision='r', caso='c')
    bandas = {e['codigo']: e['banda'] for e in c['capas']['tension']['elementos']}
    assert all(bandas[n] == 'sin_tension' for n in sin)
