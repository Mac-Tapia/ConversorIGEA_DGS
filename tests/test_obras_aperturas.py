"""Spec 081, RF-80 a RF-85: lo que una obra abre no se queda abierto en «Con proyecto».

Pisco (2026-11-07, `20261107-043049_CSG_TXT_SISTEMA_PISCO`): la web se reinició mientras ``tools/obras_pf.py`` medía una
transferencia (087:RF-31). El escenario de «Con proyecto» se quedó con SEC_1091_1055499 y SEC_1091_957116 fuera de servicio,
sin variación que lo explicase, y 724 barras de media sin tensión. Con ``fake_pf`` y ``servicio_en_escenario``, abrir es dato
del escenario activo, como en DIgSILENT: borrar la variación no lo deshace.
"""
from __future__ import annotations

import inspect
import json
import random

import pytest

import fake_pf
from test_obras_pf_guion import (CON, PERFIL_ESCALERA, SIN, _actual_no_cumple, _calibrada_con_escenario, _obra_terna,
                                 _plan, _terna, guion)

from convertersmartgrid import obras_pf as op


def _caso(app, nombre):
    caso = next(c for c in guion.casos_del_proyecto(app, None).values() if c.loc_name == nombre)
    caso.Activate()
    return caso


def _linea(app, nombre):
    return next(o for o in app.proyecto.GetContents('*.ElmLne', 1) if o.loc_name == nombre)


def _barra(app, nombre):
    return next(o for o in app.proyecto.GetContents('*.ElmTerm', 1) if o.loc_name == nombre)


def _red_con_escenarios(semilla):
    app, alims = _calibrada_con_escenario(random.Random(semilla))
    app.servicio_en_escenario = True
    return app, alims


def _abre(nombre):
    """Una «obra» que, además de su terna, abre un tramo existente como la transferencia abre su entrada."""
    def construir(ctx):
        _terna(ctx)
        guion.abrir(ctx, 'ElmLne', ctx.objeto('ElmLne', nombre))
    return construir


def _registro(plan):
    return op.leer_aperturas(op.fichero_aperturas(plan))


def test_la_transferencia_anota_lo_que_abre():
    """081:RF-80 — la migración (transferencia y traslado, 087:RF-31) y las demás obras abren por ``abrir``, que anota
    antes de abrir; la entrada de la migración se abría sin anotarla."""
    fuente = inspect.getsource(guion.construir_migracion)
    assert "abrir(ctx, 'ElmLne', lineas[entrada])" in fuente and "abrir(ctx, 'ElmCoup', acopladores[entrada])" in fuente
    for constructor in (guion.construir_migracion, guion.construir_migracion_camino, guion.construir_set_nueva,
                        guion.construir_expreso):
        cuerpo = inspect.getsource(constructor)
        assert '.outserv = 1' not in cuerpo and '.on_off = 0' not in cuerpo, constructor.__name__


def test_abrir_anota_en_la_fila_y_en_disco_antes_de_abrir(tmp_path):
    """081:RF-80 — la fila dice qué abrió y en qué caso; el registro de disco, también el proyecto y la variación."""
    app, alims = _red_con_escenarios(5)
    f = alims[0]
    _caso(app, CON)
    plan = _plan(alims, aperturas_fichero=str(tmp_path / 'aperturas.json'), evaluando=True)
    fila = {'variacion': 'Obra_x', 'avisos': []}
    ctx = guion.Contexto(app, app.proyecto, None, fila, None, None, plan=plan)
    ln = _linea(app, f'{f}_L2')
    guion.abrir(ctx, 'ElmLne', ln)
    assert ln.outserv == 1
    assert fila['abiertos'] == [['ElmLne', f'{f}_L2', CON]]
    (e,) = _registro(plan)
    assert (e['proyecto'], e['caso'], e['clase'], e['nombre'], e['variacion'], e['evaluando']) == (
        'P', CON, 'ElmLne', f'{f}_L2', 'Obra_x', True)
    _caso(app, SIN)
    assert ln.outserv == 0, 'abrir es del escenario de «Con proyecto»'


def test_al_borrar_la_variante_evaluada_lo_abierto_se_vuelve_a_cerrar(monkeypatch):
    """081:RF-81 — tras medir la variante, su variación se borra y lo que abrió, que guarda el escenario, se cierra otra
    vez; el registro queda vacío. Sin esto el tramo quedaba fuera de servicio en «Con proyecto»."""
    app, alims = _red_con_escenarios(7)
    _actual_no_cumple(monkeypatch)
    f = alims[0]
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _abre(f'{f}_L2'))
    vistos = []
    medir = guion.medida_para_criterio

    def registrar(app_, alims_, feeders, **k):
        if app_.GetActiveStudyCase().loc_name == CON:
            vistos.append(int(_linea(app, f'{f}_L2').outserv))
        return medir(app_, alims_, feeders, **k)

    monkeypatch.setattr(guion, 'medida_para_criterio', registrar)
    plan = _plan(alims, variantes=[{'nombre': 'transfiere', 'obras': [_obra_terna(f, [CON])], 'costo_base': 1.0}],
                 sorteos=[], barras_cargas=[], parametros=PERFIL_ESCALERA)
    informe, codigo = guion.evaluar(app, plan)
    assert codigo == 0, informe
    assert 1 in vistos, 'la variante se midió con el tramo abierto'
    _caso(app, CON)
    assert _linea(app, f'{f}_L2').outserv == 0
    assert _registro(plan) == []


def test_la_obra_que_no_queda_cierra_lo_que_abrio_aunque_este_fuera_de_servicio(monkeypatch):
    """081:RF-81 — ``GetCalcRelevantObjects`` no devuelve lo que está fuera de servicio: se busca en los datos de red."""
    app, alims = _red_con_escenarios(9)
    f = alims[0]
    _caso(app, CON)
    ln = _linea(app, f'{f}_L1')
    ln.outserv = 1
    real = app.GetCalcRelevantObjects
    monkeypatch.setattr(app, 'GetCalcRelevantObjects',
                        lambda patron: [o for o in real(patron) if not int(getattr(o, 'outserv', 0) or 0)])
    fila = {'abiertos': [['ElmLne', f'{f}_L1', CON]], 'avisos': []}
    assert guion.cerrar_lo_abierto(app, fila, _plan(alims)) == [f'{f}_L1']
    assert ln.outserv == 0


def test_una_orden_cortada_se_restituye_al_empezar_la_siguiente(tmp_path, monkeypatch):
    """081:RF-82 — la orden muere tras abrir (la web se reinició, Pisco 2026-11-07): la siguiente lee el registro, cierra
    lo abierto en su caso, guarda el escenario y lo dice; la variación suelta de la evaluación se avisa."""
    app, alims = _red_con_escenarios(11)
    f = alims[0]
    monkeypatch.setitem(guion.CONSTRUCTORES, 'terna', _abre(f'{f}_L2'))
    plan = _plan(alims, aperturas_fichero=str(tmp_path / 'aperturas.json'))
    # Lo que hace la evaluación de una variante, sin el ``finally`` que la borra: el proceso murió aquí.
    hecho, rc = guion.aplicar(app, {**plan, 'obras': [_obra_terna(f, [CON])], 'evaluando': True})
    assert rc == 0, hecho
    _caso(app, CON)
    assert _linea(app, f'{f}_L2').outserv == 1 and len(_registro(plan)) == 1
    esc_con = app.GetActiveScenario()
    guardados = esc_con.guardados
    informe, codigo = guion.datos_escalera(app, plan)
    assert codigo == 0, informe
    _caso(app, CON)
    assert _linea(app, f'{f}_L2').outserv == 0
    assert esc_con.guardados > guardados
    assert _registro(plan) == []
    assert [a['nombre'] for a in informe['aperturas_restituidas']] == [f'{f}_L2']
    avisos = ' '.join(informe['avisos'])
    assert '081:RF-82' in avisos and f'{f}_L2' in avisos
    assert hecho['obras'][0]['variacion'] in avisos and '042:RF-60' in avisos


def test_lo_abierto_por_una_obra_aplicada_que_sigue_activa_no_se_toca(tmp_path, monkeypatch):
    """081:RF-82 — si la orden cortada aplicaba de verdad y su variación sigue activa en el caso, lo abierto es la obra."""
    app, alims = _red_con_escenarios(13)
    f = alims[0]
    _caso(app, CON)
    v = fake_pf.variacion_del_operador(app, 'Obra_transferencia_F1', [(_barra(app, f'{f}_B2'), 'uknom', 10.0)])
    ln = _linea(app, f'{f}_L2')
    ln.outserv = 1
    plan = _plan(alims, aperturas_fichero=str(tmp_path / 'aperturas.json'))
    op.escribir_aperturas(op.fichero_aperturas(plan), [{'proyecto': 'P', 'caso': CON, 'clase': 'ElmLne',
                                                       'nombre': f'{f}_L2', 'variacion': v.loc_name,
                                                       'evaluando': False}])
    informe = {'avisos': []}
    assert guion.restituir_pendientes(app, plan, guion.casos_del_proyecto(app, None), informe) == []
    _caso(app, CON)
    assert ln.outserv == 1 and _registro(plan) == []


def test_con_proyecto_sin_variacion_que_explique_un_tramo_abierto_que_corta_se_restituye():
    """081:RF-83 — sin registro (la apertura no se anotó), un tramo fuera de servicio en «Con proyecto» y en servicio en
    «Sin proyecto», sin variación activa que lo grabe, que deja barras sin tensión: vuelve a como está en «Sin
    proyecto», en el escenario de «Con proyecto», y el informe lo lista."""
    app, alims = _red_con_escenarios(17)
    f = alims[0]
    _caso(app, CON)
    ln = _linea(app, f'{f}_L1')
    ln.outserv = 1
    assert _barra(app, f'{f}_B1').IsEnergized() == 0
    esc_con = app.GetActiveScenario()
    guardados = esc_con.guardados
    informe, codigo = guion.datos_escalera(app, _plan(alims))
    assert codigo == 0, informe
    _caso(app, CON)
    assert ln.outserv == 0 and esc_con.guardados > guardados
    assert informe['servicio_con_proyecto']['restituidos'] == [f'{f}_L1 (ElmLne)']
    assert any('081:RF-83' in a and f'{f}_L1' in a for a in informe['avisos'])
    _caso(app, SIN)
    assert ln.outserv == 0


def _lazo(app, f):
    """Un tramo que cierra un anillo entre la cabecera y la segunda barra: abierto, no deja nada sin tensión."""
    a, b = _barra(app, f'{f}_B0'), _barra(app, f'{f}_B2')
    red = a.GetParent()
    ln = fake_pf.Obj(app, 'ElmLne', f'{f}_LAZO', red)
    red._hijos.append(ln)
    cubs = []
    for barra, lado in ((a, 0), (b, 1)):
        cub = fake_pf.Obj(app, 'StaCubic', f'c_lazo_{lado}', barra)
        barra._hijos.append(cub)
        object.__setattr__(cub, 'obj_id', ln)
        cubs.append(cub)
    object.__setattr__(ln, 'bus1', cubs[0])
    object.__setattr__(ln, 'bus2', cubs[1])
    object.__setattr__(ln, 'outserv', 0)
    return ln


def test_un_tramo_abierto_que_no_corta_nada_puede_ser_del_operador_y_se_respeta():
    """081:RF-84 — si no corta nada ni está en el registro, se avisa con su lista y no se toca."""
    app, alims = _red_con_escenarios(19)
    f = alims[0]
    ln = _lazo(app, f)
    _caso(app, CON)
    ln.outserv = 1
    informe, codigo = guion.datos_escalera(app, _plan(alims))
    assert codigo == 0, informe
    _caso(app, CON)
    assert ln.outserv == 1
    assert informe['servicio_con_proyecto']['respetados'] == [f'{f}_LAZO (ElmLne)']
    assert informe['servicio_con_proyecto']['restituidos'] == []
    assert any('081:RF-84' in a and f'{f}_LAZO' in a for a in informe['avisos'])


def test_lo_que_explica_una_variacion_activa_no_se_toca():
    """081:RF-83 — una obra o una carga nueva activa en «Con proyecto» que graba el tramo o una de sus barras lo explica."""
    app, alims = _red_con_escenarios(23)
    f = alims[0]
    _caso(app, CON)
    fake_pf.variacion_del_operador(app, 'Obra_migracion_F1', [(_barra(app, f'{f}_B2'), 'uknom', 22.9)])
    ln = _linea(app, f'{f}_L2')
    ln.outserv = 1
    informe, codigo = guion.datos_escalera(app, _plan(alims))
    assert codigo == 0, informe
    _caso(app, CON)
    assert ln.outserv == 1
    assert informe['servicio_con_proyecto']['explicados'] == [f'{f}_L2 (ElmLne)']
    assert not any('081:RF-83' in a or '081:RF-84' in a for a in informe['avisos'])


def test_sin_escenario_en_con_proyecto_no_se_escribe_en_la_red(monkeypatch):
    """081:RF-85 — sin escenario, restituir cambiaría la red de todos los casos: solo se avisa."""
    app, alims = _red_con_escenarios(29)
    f = alims[0]
    _caso(app, CON)
    ln = _linea(app, f'{f}_L1')
    ln.outserv = 1
    real = app.GetActiveScenario
    monkeypatch.setattr(app, 'GetActiveScenario',
                        lambda: None if app.GetActiveStudyCase().loc_name == CON else real())
    informe = {'avisos': []}
    resultado = guion.comprobar_servicio_con_proyecto(app, _plan(alims), guion.casos_del_proyecto(app, None), informe)
    assert resultado['restituidos'] == [] and resultado['sin_escenario'] == [f'{f}_L1 (ElmLne)']
    assert any('081:RF-85' in a for a in informe['avisos'])
    _caso(app, CON)
    assert ln.outserv == 1


@pytest.mark.parametrize('semilla', (3, 31, 59))
def test_clasificar_restos_sorteado(semilla):
    """081:RF-83, 081:RF-84 — explicado manda; después lo anotado o lo que corta se restituye; lo demás se respeta."""
    rng = random.Random(semilla)
    candidatos = [{'clave': f'k{i}', 'nombre': f'E{i}'} for i in range(rng.randint(5, 40))]
    explicados = {c['clave'] for c in candidatos if rng.random() < 0.3}
    cortan = {c['clave'] for c in candidatos if rng.random() < 0.3}
    anotados = {c['clave'] for c in candidatos if rng.random() < 0.3}
    r = op.clasificar_restos(candidatos, explicados=explicados, cortan=cortan, anotados=anotados)
    for c in candidatos:
        k, n = c['clave'], c['nombre']
        esperado = 'explicados' if k in explicados else 'restituir' if k in cortan | anotados else 'respetar'
        assert n in r[esperado] and sum(n in v for v in r.values()) == 1


def test_el_registro_se_escribe_de_una_vez_y_vacio_se_borra(tmp_path):
    """081:RF-80, 081:RF-82 — ``os.replace`` y, sin entradas, sin fichero; uno ilegible no rompe la orden."""
    ruta = tmp_path / 'r' / 'a.json'
    op.escribir_aperturas(ruta, [{'nombre': 'X'}])
    assert json.loads(ruta.read_text(encoding='utf-8'))['aperturas'] == [{'nombre': 'X'}]
    op.escribir_aperturas(ruta, [])
    assert not ruta.exists()
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text('{roto', encoding='utf-8')
    assert op.leer_aperturas(ruta) == []
    assert op.fichero_aperturas({'project': 'A/B', 'folder': 'X'}) != op.fichero_aperturas({'project': 'A/B', 'folder': 'Y'})
