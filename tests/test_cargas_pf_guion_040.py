"""Spec 040: cargas del bloque sin duplicados, y ampliaciones de clientes existentes.

``tools/cargas_pf.py`` contra el DIgSILENT simulado (``fake_pf``). El caso real fue NA203 +
NA205 (2026-10-31): «Fundo Luciana» y «YANACA» dos veces cada una en el libro, y «Cesar Alberto
Monge Marquez SE50324» creada como SED nueva a 3 m de SE50324.
"""
from __future__ import annotations

import pytest

import fake_pf
from apoyo import cargar_herramienta
from test_cargas_pf_guion import _nueva, _plan

STAMP = '20261008_120000'
FICHAS = {'umbral_carga_pct': 80, 'tablas': [
    {'norma': 'Tabla de prueba', 'codigo': 'NTPX', 'kv_min': 0, 'kv_max': 36,
     'fichas': {'100': [1, 1, 1, 4], '250': [1, 1, 1, 4], '400': [1, 1, 1, 4]}}]}


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('cargas_pf.py', 'cargas_pf_guion_040', tools_en_path=True)


def _app():
    app = fake_pf.proyecto(alimentadores=('F1', 'F2'), cargas_por_alim=4, bt=True, flujo=True)
    # En DIgSILENT la barra de baja de cada SED tiene el GPS de su SED (NA203 + NA205: 188 de 188).
    for sub in app.proyecto.GetContents('*.ElmSubstat', 1):
        f, i = sub.loc_name.split('_S')
        mt = next(b for b in app.proyecto.GetContents('*.ElmTerm', 1) if b.loc_name == f'{f}_B{i}')
        for b in sub.GetContents('*.ElmTerm'):
            b.GPSlat, b.GPSlon = mt.GPSlat, mt.GPSlon
    app.escrituras.clear()
    app.creados.clear()
    return app


def _punto(app, barra, dlat):
    b = next(x for x in app.proyecto.GetContents('*.ElmTerm', 1) if x.loc_name == barra)
    return {'lat': b.GPSlat + dlat, 'lon': b.GPSlon}


def _variaciones(app):
    return {v.loc_name: v for v in app.carpetas['scheme'].GetContents('*.IntScheme')}


def _variacion_con(app, nombre, objetos):
    """Una variación de carga nueva hecha antes, con ``objetos`` (clase, nombre) en su etapa."""
    v = app.carpetas['scheme'].CreateObject('IntScheme', nombre)
    v.NewStage('Etapa_previa', 1, 1)
    app.grabando = v.GetContents('*.IntSstage')[0]
    sub = next(o for o in app.proyecto.GetContents('*.ElmSubstat', 1) if o.loc_name == 'F1_S1')
    padre = sub
    for clase, n in objetos:
        hecho = padre.CreateObject(clase, n)
        if clase == 'ElmSubstat':
            padre = hecho
    app.grabando = None
    v.Deactivate()
    app.creados.clear()
    return v


# =========================================================================== RF-1, RF-2
def test_fila_duplicada_en_el_mismo_alimentador_no_se_crea(guion):
    """040:RF-1, 040:RF-2, 040:RF-9 — dos filas de F1 en el mismo punto son la misma carga: se
    crea la primera y la otra se informa como duplicada; la del mismo punto en F2 no es
    duplicada y va a F2, como dice el libro."""
    app = _app()
    p = _punto(app, 'F1_B2', 0.0005)                    # unos 55 m: lejos de toda SED
    nuevas = [_nueva('N1', alimentador='F1', **p), _nueva('N1B', alimentador='F1', **p),
              _nueva('N1C', alimentador='F2', **p)]

    informe, rc = guion.ejecutar(app, _plan(['F1', 'F2'], nuevas=nuevas), simular=True)

    assert rc == 0, informe
    crearian = {c['sed']: f['feeder'] for f in informe['feeders'] for c in f['crearian']}
    assert crearian == {'N1': 'F1', 'N1C': 'F2'}
    (dup,) = informe['duplicadas']
    assert dup['sed'] == 'N1B' and dup['duplicada_de'] == 'N1' and '040:RF-1' in dup['motivo']
    assert any('N1B' in a and '040:RF-1' in a for a in informe['avisos'])


# =========================================================================== RF-3
def test_ampliacion_se_reconoce_por_el_nombre_y_por_la_distancia(guion):
    """040:RF-3 — una palabra del nombre que es una SED de su alimentador la hace ampliación
    de esa SED a cualquier distancia; a 30 m o menos de la barra de baja de una SED, también;
    a unos 55 m es una carga nueva."""
    app = _app()
    nuevas = [_nueva('Cliente F1_S1 ampliacion', alimentador='F1', **_punto(app, 'F1_B4', 0.002)),
              _nueva('CERCA', alimentador='F1', **_punto(app, 'F1_B3', 0.0002)),
              _nueva('LEJOS', alimentador='F1', **_punto(app, 'F1_B3', 0.0005))]

    informe, rc = guion.ejecutar(app, _plan(['F1'], nuevas=nuevas), simular=True)

    assert rc == 0, informe
    crearian = {c['sed']: c for f in informe['feeders'] for c in f['crearian']}
    assert crearian['Cliente F1_S1 ampliacion']['ampliacion']['sed'] == 'F1_S1'
    assert 'nombre' in crearian['Cliente F1_S1 ampliacion']['ampliacion']['criterio']
    cerca = crearian['CERCA']['ampliacion']
    assert cerca['sed'] == 'F1_S3' and cerca['distancia_m'] == pytest.approx(22.2, abs=1.0)
    assert crearian['LEJOS'].get('ampliacion') is None


def test_una_carga_nueva_creada_antes_no_es_sed_existente(guion):
    """040:RF-3 — la SED de una carga nueva de una variación anterior no cuenta como SED
    existente, aunque su variación esté activa."""
    app = _app()
    v = _variacion_con(app, f'Carga_PREVIA_F1_{STAMP}', [('ElmSubstat', 'PREVIA'), ('ElmLod', 'PREVIA')])
    v.Activate()
    existentes = guion.sed_existentes(guion.Alimentadores(app, app.proyecto, ['F1']),
                                      {'indice': {('F1', 'PREVIA'): {'variaciones': [v.loc_name]}}})
    assert 'PREVIA' not in {s['sed'] for s in existentes['F1']}
    assert 'F1_S2' in {s['sed'] for s in existentes['F1']}


# =========================================================================== RF-4, RF-5
def test_la_ampliacion_solo_crea_su_carga_en_la_baja_y_propone_transformador(guion):
    """040:RF-4, 040:RF-5, 040:RF-9 — la ampliación no crea SED, transformador, línea ni barra:
    solo una carga con la potencia de la fila en la barra de baja de la SED, en su variación,
    medida como las demás; la SED (50 kW + 80 kW sobre 100 kVA) pasa del 80 % y se propone
    el transformador de 250 kVA, sin aplicarlo."""
    app = _app()
    fila = _nueva('AMP', alimentador='F1', **_punto(app, 'F1_B2', 0.0001))
    plan = {**_plan(['F1'], nuevas=[fila]), 'transformadores_sed': FICHAS}

    informe, rc = guion.ejecutar(app, plan, simular=False)

    assert rc == 0, informe
    (creada,) = informe['cargas']
    assert creada['variacion'] == f'Carga_AMP_F1_{STAMP}'
    amp = creada['ampliacion']
    assert amp['sed'] == 'F1_S2' and amp['barra'] == 'F1_S2_BT'
    assert amp['propuesta']['kva'] == 250
    assert creada['con_proyecto']['converged'] and creada['delta'] is not None
    variacion = _variaciones(app)[creada['variacion']]
    (etapa,) = variacion.GetContents('*.IntSstage')
    clases = {o.GetClassName() for o in etapa.GetContents('*', 1)}
    assert not clases & {'ElmSubstat', 'ElmLne', 'ElmTr2', 'ElmTerm'}
    (carga,) = etapa.GetContents('*.ElmLod', 1)
    baja = next(b for b in app.proyecto.GetContents('*.ElmTerm', 1) if b.loc_name == 'F1_S2_BT')
    assert carga.loc_name == 'AMP' and carga in baja.GetConnectedElements()
    tr = next(o for o in app.proyecto.GetContents('*.ElmTr2', 1) if o.loc_name == 'TR_F1_S2')
    assert tr.typ_id.loc_name == 'TR100_F1'              # se propone, no se cambia
    assert any('AMP' in a and 'F1_S2' in a and '040:RF-5' in a for a in informe['avisos'])


# =========================================================================== RF-6 a RF-8
def test_se_eliminan_la_duplicada_y_la_ampliacion_creada_como_sed(guion):
    """040:RF-6, 040:RF-8, 040:RF-9 — la variación de una fila duplicada y la de una ampliación
    creada antes como SED nueva se desactivan en todos los casos y se eliminan; una variación
    del operador no se toca. Al simular solo se listan."""
    app = _app()
    p = _punto(app, 'F1_B3', 0.0005)
    dup = _variacion_con(app, 'Carga_N1B_F1_20261001_000000', [('ElmSubstat', 'N1B'), ('ElmLod', 'N1B')])
    vieja = _variacion_con(app, 'Carga_AMP_F1_20261001_000000', [('ElmSubstat', 'AMP'), ('ElmLod', 'AMP')])
    obra = _variacion_con(app, 'Obra_operador', [('ElmLod', 'N1B')])
    nuevas = [_nueva('N1', alimentador='F1', **p), _nueva('N1B', alimentador='F1', **p),
              _nueva('AMP', alimentador='F1', **_punto(app, 'F1_B2', 0.0001))]

    simulado, rc = guion.ejecutar(app, _plan(['F1'], nuevas=nuevas), simular=True)
    assert rc == 0, simulado
    assert sorted(x['variacion'] for x in simulado['eliminarian']) == sorted([dup.loc_name, vieja.loc_name])
    assert {dup.loc_name, vieja.loc_name} <= set(_variaciones(app))

    informe, rc = guion.ejecutar(app, _plan(['F1'], nuevas=nuevas), simular=False)

    assert rc == 0, informe
    assert sorted(x['variacion'] for x in informe['eliminadas']) == sorted([dup.loc_name, vieja.loc_name])
    quedan = set(_variaciones(app))
    assert dup.loc_name not in quedan and vieja.loc_name not in quedan
    assert obra.loc_name in quedan
    assert {c['sed'] for c in informe['cargas']} == {'N1', 'AMP'}
    for caso in app.carpetas['study'].GetContents('*.IntCase'):
        assert dup not in caso._estado.variaciones and vieja not in caso._estado.variaciones
    assert any(dup.loc_name in a and '040:RF-6' in a for a in informe['avisos'])


def test_el_nombre_de_la_variacion_conserva_el_alimentador(guion):
    """040:RF-10 — con un nombre de carga largo se recorta la SED, no el alimentador ni el sello:
    «Carga_SU_Predio_3H_MINING_GROUP_SAC_NA20» había perdido NA203 (2026-10-31)."""
    app = _app()
    nombre = guion.nombre_de_carga(app.carpetas['scheme'], 'SU Predio 3H MINING GROUP SAC', 'NA203',
                                   '20261031_120000', set())
    assert len(nombre) <= guion.MAX_NOMBRE
    assert nombre.startswith('Carga_SU_Predio') and nombre.endswith('_NA203_20261031_120000')


def test_la_variacion_sin_alimentador_en_el_nombre_se_reconoce_y_se_renombra(guion):
    """040:RF-11 — una variación de carga nueva cuyo nombre ya no dice el alimentador se
    reconoce por el punto de su carga (la SED existente más cercana), se reutiliza y se
    renombra con su alimentador, para que los casos la cuenten como carga de ese alimentador."""
    app = _app()
    p = _punto(app, 'F1_B3', 0.0005)
    larga = 'Carga_UNA_CARGA_CON_NOMBRE_MUY_LARGO_DE_'
    v = _variacion_con(app, larga, [('ElmSubstat', 'UNA_CARGA_CON_NOMBRE_MUY_LARGO'),
                                    ('ElmLod', 'UNA_CARGA_CON_NOMBRE_MUY_LARGO')])
    (etapa,) = v.GetContents('*.IntSstage')
    (carga,) = etapa.GetContents('*.ElmLod', 1)
    carga.GPSlat, carga.GPSlon = p['lat'], p['lon']

    informe, rc = guion.ejecutar(app, _plan(['F1', 'F2'], nuevas=[
        _nueva('UNA CARGA CON NOMBRE MUY LARGO', alimentador='F1', **p)]), simular=False)

    assert rc == 0, informe
    assert informe['cargas'] == []
    (reuso,) = informe['reutilizadas']
    assert reuso['variacion'] == v.loc_name and v.loc_name != larga
    assert v.loc_name.endswith(f'_F1_{STAMP}') and len(v.loc_name) <= guion.MAX_NOMBRE
    assert any(larga in a and '040:RF-11' in a for a in informe['avisos'])


def test_la_carga_recortada_por_su_sufijo_se_reconoce_por_su_nombre(guion):
    """040:RF-12 — DIgSILENT recorta el nombre para añadir «(2)» sin pasar de 40 caracteres
    («Cesar_Alberto_Monge_Marquez_SE5032(2)», NA203, 2026-10-31): la fila se reconoce igual por
    su nombre, y si es una ampliación su variación vieja con SED se elimina."""
    app = _app()
    v = _variacion_con(app, 'Carga_Cesar_Alberto_Monge_Marquez_SE5032',
                       [('ElmSubstat', 'Cesar_Alberto_Monge_Marquez_SE50324'),
                        ('ElmLod', 'Cesar_Alberto_Monge_Marquez_SE5032(2)')])
    p = _punto(app, 'F1_B2', 0.0001)
    (etapa,) = v.GetContents('*.IntSstage')
    for o in etapa.GetContents('*', 1):
        o.GPSlat, o.GPSlon = p['lat'], p['lon']

    informe, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[
        _nueva('Cesar Alberto Monge Marquez SE50324 F1_S2', alimentador='F1', **p)]), simular=True)

    assert rc == 0, informe
    assert [x['variacion'] for x in informe['eliminarian']] == [v.loc_name]


def test_la_carga_en_dos_variaciones_conserva_la_primera(guion):
    """040:RF-7 — una carga en dos variaciones de carga nueva: se conserva la primera por su
    nombre, se elimina la otra y se reutiliza la conservada, activa en «Con proyecto»."""
    app = _app()
    p = _punto(app, 'F1_B3', 0.0005)
    primero, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[_nueva('N1', alimentador='F1', **p)]),
                                 simular=False)
    assert rc == 0, primero
    copia = _variacion_con(app, 'Carga_N1_F1_20261001_000000', [('ElmSubstat', 'N1'), ('ElmLod', 'N1')])

    segundo, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[_nueva('N1', alimentador='F1', **p)]),
                                 simular=False)

    assert rc == 0, segundo
    assert set(_variaciones(app)) == {copia.loc_name}
    assert [x['variacion'] for x in segundo['eliminadas']] == [f'Carga_N1_F1_{STAMP}']
    assert [x['variacion'] for x in segundo['reutilizadas']] == [copia.loc_name]
    con = next(c for c in app.carpetas['study'].GetContents('*.IntCase') if c.loc_name == 'Con proyecto')
    assert copia in con._estado.variaciones
    assert any('040:RF-7' in a for a in segundo['avisos'])
