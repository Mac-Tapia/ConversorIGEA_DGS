"""Spec 111, T12: ``tools/variacion_plano_pf.py``, la variación del plano estudiada en DIgSILENT, contra ``fake_pf``.

La variación solo existe en DIgSILENT mientras dura el estudio: en una variación temporal del conversor, dentro de una
copia del caso (y de una copia del escenario de operación, si el caso tiene uno activo). Al terminar, también si el
guion revienta, se borra todo y el caso del operador queda como estaba (foto de ``pf_estado``). La corrida real es la
T18, sobre una copia de un proyecto de prueba.
"""
from __future__ import annotations

import functools
import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

import fake_pf
from apoyo import cargar_herramienta, contexto_nativo

from convertersmartgrid import variacion_plano
from convertersmartgrid.dgs import nombre_en_pf



@functools.cache
def _guion():
    """El guion, cargado al usarlo: sin él, cada prueba falla por sí sola en vez de romper la recogida."""
    assert (RAIZ / 'tools' / 'variacion_plano_pf.py').is_file(), 'falta el guion tools/variacion_plano_pf.py'
    return cargar_herramienta('variacion_plano_pf.py', 'variacion_plano_pf_t12', tools_en_path=True)


RAIZ = Path(__file__).resolve().parents[1]
SEMILLAS = (3, 41, 207)
REVISION = 'a' * 64


def _red(semilla: int, *, escenario: bool = False):
    """Un alimentador de longitud sorteada con un seccionador en el cubículo de su segundo tramo."""
    rng = random.Random(semilla)
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=rng.randint(3, 6), escenario=escenario)
    app.atributos_en_variacion = True
    app.servicio_en_escenario = escenario
    barra = next(b for b in app.GetCalcRelevantObjects('*.ElmTerm') if b.loc_name == 'F1_B1')
    cub = next(c for c in barra.GetContents('*.StaCubic') if c.loc_name == 'c0_F1_L2')
    sw = cub.CreateObject('StaSwitch', 'SW1')
    object.__setattr__(sw, 'on_off', 1)
    app.escrituras.clear()
    app.creados.clear()
    return app, sw


def _con_resultados(app, visto: dict):
    """El flujo del doble deja tensión y cargabilidad, y anota qué red vio."""
    def efecto(app_, _orden):
        visto['lineas'] = sorted(o.loc_name for o in app_.GetCalcRelevantObjects('*.ElmLne'))
        visto['interruptores'] = {o.loc_name: o.on_off for o in app_.GetCalcRelevantObjects('*.StaSwitch')}
        visto['caso'] = app_.GetActiveStudyCase().loc_name
        for b in app_.GetCalcRelevantObjects('*.ElmTerm'):
            object.__setattr__(b, 'm_u', 0.97)
        for ln in app_.GetCalcRelevantObjects('*.ElmLne'):
            object.__setattr__(ln, 'c:loading', 42.5)
    object.__setattr__(app.ldf, 'efecto', efecto)


def _plan(ediciones, **extra):
    return {'project': 'P', 'feeders': ['F1'], 'caso': 'Caso', 'stamp': '20261115_120000',
            'variacion': {'id': '0123456789abcdef', 'version': 3, 'revision': REVISION},
            'ediciones': ediciones, 'native_action_context': contexto_nativo('P', ['F1'], 'plano'), **extra}


def _sin_rastro(app, caso_inicial):
    """Ni variación temporal, ni copia del caso o del escenario, y el caso del operador activo."""
    assert not [v for v in app.carpetas['scheme'].GetContents('*.IntScheme')
                if v.loc_name.startswith(_guion().PREFIJO)]
    assert [c.loc_name for c in app.carpetas['study'].GetContents('*.IntCase')] == ['Caso']
    if 'scen' in app.carpetas:
        assert [e.loc_name for e in app.carpetas['scen'].GetContents('*.IntScenario')] == ['Operador']
    assert app.GetActiveStudyCase() is caso_inicial


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_111_rf4_la_maniobra_se_estudia_en_una_variacion_temporal_de_una_copia_del_caso(semilla):
    """111:RF-4 — la maniobra va a una variación del conversor en una copia del caso; al terminar no queda nada."""
    app, sw = _red(semilla)
    caso = app.GetActiveStudyCase()
    hora = caso.iStudyTime
    visto: dict = {}
    _con_resultados(app, visto)
    informe, rc = _guion().ejecutar(app, _plan([{'tipo': 'maniobra', 'codigo': 'SW1', 'nombre_pf': 'SW1',
                                              'estado': 'abierto'}]))
    assert rc == 0, informe
    assert visto['interruptores']['SW1'] == 0 and visto['caso'] != 'Caso'
    assert sw.on_off == 1 and caso.iStudyTime == hora
    _sin_rastro(app, caso)
    # Nada se escribió en la red sin la etapa de la variación temporal: el caso base no se toca.
    red = [e for e in app.escrituras if e[0].GetClassName().startswith(('Elm', 'Sta'))]
    assert red and all(etapa is not None and etapa._padre.loc_name.startswith(_guion().PREFIJO)
                       for _o, _n, _v, etapa, _esc in red)
    assert informe['aplicadas'] == ['SW1'] and informe['restitucion_ok'] is True


def test_111_rf4_con_escenario_activo_la_maniobra_va_a_una_copia_del_escenario():
    """111:RF-4 — con escenario de operación, la maniobra cae en una copia suya, que se borra; el del operador sigue."""
    app, sw = _red(5, escenario=True)
    caso, operador = app.GetActiveStudyCase(), app.GetActiveScenario()
    visto: dict = {}
    _con_resultados(app, visto)
    informe, rc = _guion().ejecutar(app, _plan([{'tipo': 'maniobra', 'codigo': 'SW1', 'nombre_pf': 'SW1',
                                              'estado': 'abierto'}]))
    assert rc == 0, informe
    assert visto['interruptores']['SW1'] == 0
    assert app.GetActiveScenario() is operador and not operador._servicio
    assert sw.on_off == 1
    assert informe['escenario_copiado'] is True
    _sin_rastro(app, caso)


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_111_rf10_el_estudio_lee_la_red_con_sus_resultados_y_dice_el_motor(semilla):
    """111:RF-10, RF-17 — tras el flujo, la geografía con tensión y cargabilidad; el informe dice DIgSILENT."""
    app, _sw = _red(semilla)
    _con_resultados(app, {})
    informe, rc = _guion().ejecutar(app, _plan([]))
    assert rc == 0, informe
    assert informe['motor'] == 'DIgSILENT' and informe['convergio'] is True
    assert informe['revision'] == REVISION and informe['version'] == 3 and informe['variacion'] == '0123456789abcdef'
    barras = {b[0]: b[3] for b in informe['geo']['barras']}
    assert barras and set(barras.values()) == {0.97}
    assert {t[2] for t in informe['geo']['tramos']} == {42.5}


def test_111_rf5_un_tramo_nuevo_existe_solo_durante_el_estudio():
    """111:RF-5 — el tramo nuevo, con sus vértices y su longitud, se crea en la variación temporal y no queda."""
    app, _sw = _red(11)
    caso = app.GetActiveStudyCase()
    antes = sorted(o.loc_name for o in app.GetCalcRelevantObjects('*.ElmLne'))
    visto: dict = {}
    _con_resultados(app, visto)
    tramo = {'tipo': 'tramo', 'codigo': 'NUEVO1', 'nombre_pf': 'NUEVO1', 'desde_pf': 'F1_B0', 'hasta_pf': 'NUEVO1_FIN',
             'hasta_nuevo': True, 'vertices': [[-14.0, -75.7], [-14.001, -75.701]], 'longitud_km': 0.15,
             'tipo_de_tramo_pf': 'F1_L1', 'fases': 'ABC'}
    informe, rc = _guion().ejecutar(app, _plan([tramo]))
    assert rc == 0, informe
    assert 'NUEVO1' in visto['lineas']
    assert sorted(o.loc_name for o in app.GetCalcRelevantObjects('*.ElmLne')) == antes
    assert 'NUEVO1_FIN' not in {o.loc_name for o in app.GetCalcRelevantObjects('*.ElmTerm')}
    _sin_rastro(app, caso)


def test_111_rf4_una_edicion_que_no_esta_en_la_red_no_corre_el_flujo_y_no_deja_nada():
    """111:RF-4 — un nombre que DIgSILENT no tiene se dice, el flujo no corre y todo se borra."""
    app, sw = _red(2)
    caso = app.GetActiveStudyCase()
    informe, rc = _guion().ejecutar(app, _plan([{'tipo': 'maniobra', 'codigo': 'NO_ESTA', 'nombre_pf': 'NO_ESTA',
                                              'estado': 'abierto'}]))
    assert rc == 2 and 'NO_ESTA' in informe['error']
    assert app.ldf.ejecuciones == 0 and sw.on_off == 1
    _sin_rastro(app, caso)


def test_111_rf4_si_el_flujo_revienta_tambien_se_borra_todo():
    """111:RF-4 — la copia del caso y la variación temporal se borran aunque el guion reviente a mitad."""
    app, sw = _red(17)
    caso = app.GetActiveStudyCase()

    def revienta(_app, _orden):
        raise RuntimeError('fallo sembrado')
    object.__setattr__(app.ldf, 'efecto', revienta)
    with pytest.raises(RuntimeError, match='fallo sembrado'):
        _guion().ejecutar(app, _plan([{'tipo': 'maniobra', 'codigo': 'SW1', 'nombre_pf': 'SW1', 'estado': 'abierto'}]))
    assert sw.on_off == 1
    _sin_rastro(app, caso)


def test_111_rf17_sin_el_vinculo_firmado_no_abre_digsilent(tmp_path):
    """111:RF-17 — un plan sin el contexto firmado del vínculo proyecto ↔ red se bloquea antes de conectar."""
    plan = _plan([])
    plan.pop('native_action_context')
    (tmp_path / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
    rc = _guion().main(['--plan', str(tmp_path / 'plan.json'), '--output-json', str(tmp_path / 'informe.json')])
    informe = json.loads((tmp_path / 'informe.json').read_text(encoding='utf-8'))
    assert rc == 2 and informe['status'] == 'BLOQUEADO_DATOS'


def test_111_rf17_el_guion_responde_help_sin_digsilent(tmp_path):
    """111:RF-17 — ``--help`` sin DIgSILENT ni datos."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('CSG_')}
    env['PYTHONPATH'] = os.pathsep.join([str(RAIZ / 'src'), str(RAIZ / 'tools')])
    # Como test_inventario: sin esto, la ayuda sale en la página de códigos de la consola y no se lee como UTF-8.
    env['PYTHONIOENCODING'] = 'utf-8'
    r = subprocess.run([sys.executable, str(RAIZ / 'tools' / 'variacion_plano_pf.py'), '--help'], cwd=tmp_path,
                       env=env, capture_output=True, text=True, encoding='utf-8', timeout=120)
    assert r.returncode == 0 and 'usage' in r.stdout.lower()


def _vista(codigo_largo: str) -> dict:
    return {'alimentador': 'F1', 'kv': 10.0, 'tipos_de_linea': ['AAAC'],
            'barras': [{'codigo': 'Barra ñandú 1', 'nombre_pf': nombre_en_pf('Barra ñandú 1'), 'lat': -14.0, 'lon': -75.7},
                       {'codigo': 'B2', 'nombre_pf': 'B2', 'lat': -14.0, 'lon': -75.699}],
            'tramos': [{'codigo': codigo_largo, 'nombre_pf': nombre_en_pf(codigo_largo), 'desde': 'Barra ñandú 1',
                        'hasta': 'B2', 'tipo': 'AAAC', 'fases': 'ABC', 'vertices': [[-14.0, -75.7], [-14.0, -75.699]]}],
            'maniobras': [{'codigo': 'M 1', 'nombre_pf': nombre_en_pf('M 1'), 'estado': 'cerrado'}]}


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_111_rf2_el_plan_de_digsilent_lleva_los_nombres_de_la_identidad(tmp_path, semilla):
    """111:RF-2 — las ediciones van a DIgSILENT con el nombre de la identidad del plano, nunca con otra regla."""
    from convertersmartgrid import resultados_plano

    assert hasattr(resultados_plano, 'plan_pf'), 'resultados_plano no da el plan de DIgSILENT'
    plan_pf = resultados_plano.plan_pf
    rng = random.Random(semilla)
    largo = 'TRAMO_' + ''.join(rng.choice('ABCDÉÑ 0123') for _ in range(rng.randint(41, 60)))
    vista = _vista(largo)
    v = variacion_plano.nueva(tmp_path, revision=REVISION, caso='Caso', alimentador='F1')
    v = variacion_plano.editar(tmp_path, v['id'], {'tipo': 'maniobra', 'codigo': 'M 1', 'estado': 'abierto'},
                               version=v['version'], revision=REVISION, vista=vista)
    nuevo = 'NUEVO ' + 'Z' * rng.randint(40, 50)
    v = variacion_plano.editar(tmp_path, v['id'], {'tipo': 'tramo', 'codigo': nuevo, 'desde': 'Barra ñandú 1',
                                                   'vertices': [[-14.0, -75.7], [-14.002, -75.702]],
                                                   'conductor': 'AAAC', 'fases': 'ABC'},
                               version=v['version'], revision=REVISION, vista=vista)
    ediciones = plan_pf(vista, v)
    assert [e['tipo'] for e in ediciones] == ['maniobra', 'tramo']
    assert ediciones[0]['nombre_pf'] == nombre_en_pf('M 1') and ediciones[0]['estado'] == 'abierto'
    t = ediciones[1]
    assert t['nombre_pf'] == nombre_en_pf(nuevo) and t['desde_pf'] == nombre_en_pf('Barra ñandú 1')
    assert t['hasta_pf'] == nombre_en_pf(f'{nuevo}_FIN') and t['hasta_nuevo'] is True
    assert t['tipo_de_tramo_pf'] == nombre_en_pf(largo) and len(t['tipo_de_tramo_pf']) <= 40
    assert t['longitud_km'] == pytest.approx(v['ediciones'][1]['longitud_gis_m'] / 1000)
