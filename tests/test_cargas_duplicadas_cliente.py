"""Spec 099: el mismo cliente dos veces en el libro de cargas nuevas, por su nombre.

Caso real (CA101, 2026-11-07): «SU-1770KW-Tierra Larga - Distrito el Camen- Provincia de chincha» (CH_20) y
«SU-1390KW-TierraLarga-Chincha» (CH_23), a 2,6 km una de otra, se creaban las dos; cuenta CH_23, la última.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from apoyo import cargar_herramienta
from convertersmartgrid import cargas_pf as cp
from test_cargas_pf_guion import _nueva, _plan
from test_cargas_pf_guion_040 import _app, _punto, _variacion_con, _variaciones

TIERRA_1770 = 'SU-1770KW-Tierra Larga - Distrito el Camen- Provincia de chincha'
TIERRA_1390 = 'SU-1390KW-TierraLarga-Chincha'


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('cargas_pf.py', 'cargas_pf_guion_099', tools_en_path=True)


def test_el_mismo_cliente_con_otra_potencia_y_otra_escritura():
    """099:RF-2 — sin la potencia, los signos y las palabras genéricas, «Tierra Larga» y «TierraLarga» son el mismo
    cliente; Danper y Buganvilla no; una sola palabra distintiva solo con el nombre igual (YANACA y su sublote)."""
    assert cp.mismo_cliente(TIERRA_1770, TIERRA_1390)
    assert cp.mismo_cliente('SU Fundo Luciana, propiedad de Agricola Mancha Verde S.A.C.', 'Fundo Luciana')
    assert cp.mismo_cliente('HONGWEN POLYMETALLIC CORP. S.A.C. ', 'HONGWEN POLYMETALLIC CORP. S.A.C.')
    assert not cp.mismo_cliente('SU empresa Danper Trujillo SAC', 'S.U. HHUU BUGANVILLA')
    assert not cp.mismo_cliente('PREDIO SUBLOTE N°01-FUNDO YANACA', 'YANACA')
    assert 'tierralarga' in cp._con_compuestas(TIERRA_1770)
    assert not any('1770' in p for p in cp.palabras_del_cliente(TIERRA_1770))


def test_cuenta_la_ultima_fila_y_solo_en_su_alimentador():
    """099:RF-1, 099:RF-3, 099:RF-4 — en el mismo alimentador cuenta la última fila del libro, también por el mismo
    punto; en otro alimentador no es duplicada; en cadena, todas van a la última."""
    filas = [{'sed': 'CH_20', 'descripcion': TIERRA_1770, 'alimentador': 'F1'},
             {'sed': 'CH_10', 'descripcion': 'SU empresa Danper Trujillo SAC', 'alimentador': 'F1'},
             {'sed': 'CH_23', 'descripcion': TIERRA_1390, 'alimentador': 'F1'},
             {'sed': 'OTRA', 'descripcion': TIERRA_1390, 'alimentador': 'F2'},
             {'sed': 'P1', 'descripcion': 'Alfa', 'alimentador': 'F3', 'lat': -13.5, 'lon': -76.0},
             {'sed': 'P2', 'descripcion': 'Beta', 'alimentador': 'F3', 'lat': -13.5, 'lon': -76.0},
             {'sed': 'C1', 'descripcion': 'Fundo Rio Seco Norte', 'alimentador': 'F4'},
             {'sed': 'C2', 'descripcion': 'SU Fundo Rio Seco Norte 200kW', 'alimentador': 'F4'},
             {'sed': 'C3', 'descripcion': 'Fundo RioSeco Norte', 'alimentador': 'F4'}]
    assert cp.duplicadas_por_cliente(filas) == {'CH_20': 'CH_23', 'P1': 'P2', 'C1': 'C3', 'C2': 'C3'}


def test_sin_nombres_fijos_en_el_codigo():
    """099:RF-6 — ni clientes, ni alimentadores, ni empresas en las palabras genéricas ni en la regla (el caso real
    solo se cita en el comentario)."""
    assert not {'tierra', 'larga', 'chincha', 'yanaca', 'luciana', 'electro', 'dunas'} & cp.PALABRAS_GENERICAS
    import ast
    import textwrap

    literales = []
    for f in (cp.palabras_del_cliente, cp._con_compuestas, cp.mismo_cliente, cp.duplicadas_por_cliente):
        (fn,) = ast.parse(textwrap.dedent(inspect.getsource(f))).body
        docstring = ast.get_docstring(fn, clean=False)
        literales += [n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                      and n.value != docstring]
    for nombre in ('CA101', 'CH_2', 'TierraLarga', 'YANACA', 'Dunas'):
        assert not any(nombre.lower() in x.lower() for x in literales)


def test_la_anterior_no_se_crea_y_su_variacion_se_elimina(guion):
    """099:RF-1, 099:RF-5 — el guion no crea la fila anterior del mismo cliente, dice cuál cuenta y elimina la variación
    de carga nueva que se creó antes para ella; una del operador no se toca."""
    app = _app()
    vieja = _variacion_con(app, 'Carga_CH_20_F1_20261105_131302', [('ElmSubstat', 'CH_20'), ('ElmLod', 'CH_20')])
    obra = _variacion_con(app, 'Obra_operador', [('ElmLod', 'CH_20')])
    nuevas = [_nueva('CH_20', alimentador='F1', descripcion=TIERRA_1770, **_punto(app, 'F1_B2', 0.0005)),
              _nueva('CH_23', alimentador='F1', descripcion=TIERRA_1390, **_punto(app, 'F1_B4', 0.0005))]

    informe, rc = guion.ejecutar(app, _plan(['F1'], nuevas=nuevas), simular=False)

    assert rc == 0, informe
    assert {c['sed'] for c in informe['cargas']} == {'CH_23'}
    (dup,) = informe['duplicadas']
    assert dup['sed'] == 'CH_20' and dup['duplicada_de'] == 'CH_23' and '099:RF-1' in dup['motivo']
    assert [x['variacion'] for x in informe['eliminadas']] == [vieja.loc_name]
    assert vieja.loc_name not in _variaciones(app) and obra.loc_name in _variaciones(app)
    assert any(a.startswith('CH_20:') and 'CH_23' in a for a in informe['avisos'])


def test_la_web_ensena_las_repetidas_de_los_alimentadores_marcados():
    """099:RF-7 — al cargar el libro, el plan dice cada fila repetida de los alimentadores marcados, la que cuenta y por
    qué; las de un alimentador no marcado no salen."""
    filas = [{'sed': 'CH_20', 'descripcion': TIERRA_1770, 'alimentador': 'CA9', 'kw': 1770.0},
             {'sed': 'CH_23', 'descripcion': TIERRA_1390, 'alimentador': 'CA9', 'kw': 1390.0},
             {'sed': 'P1', 'descripcion': 'Alfa', 'alimentador': 'XX', 'lat': -13.5, 'lon': -76.0},
             {'sed': 'P2', 'descripcion': 'Beta', 'alimentador': 'XX', 'lat': -13.5, 'lon': -76.0}]
    (r,) = cp.repetidas_del_libro(filas, ['ca9 '])
    assert (r['sed'], r['cuenta'], r['kw'], r['cuenta_kw'], r['motivo']) == ('CH_20', 'CH_23', 1770.0, 1390.0,
                                                                          'mismo cliente')
    assert {x['motivo'] for x in cp.repetidas_del_libro(filas)} == {'mismo cliente', 'mismo punto'}
    fuente = (Path(__file__).resolve().parents[1] / 'src/convertersmartgrid/web/services.py').read_text(encoding='utf-8')
    assert "'repetidas': repetidas_del_libro(plan['nuevas'], plan['feeders'])" in fuente
    web = (Path(__file__).resolve().parents[1] / 'frontend/src/components/CargasTab.tsx').read_text(encoding='utf-8')
    assert 'plan.repetidas' in web and 'Cuenta' in web
