"""Spec 081, RF-64 a RF-69: lo nuevo se adapta a las fases de su barra y nunca deja de crearse.

Cambia 054:RF-10, que no creaba la SED nueva si no había una barra trifásica: el usuario, 2026-11-03,
«nada debe bloquear, debes dar solución, para eso están los oráculos». Redes de ``fake_pf`` con el
número de alimentadores, de barras y las fases sorteados.
"""
from __future__ import annotations

import os
import random

import pytest

from apoyo import cargar_herramienta
from convertersmartgrid.comprobacion_fases import corriente_por_fase_a, fases_de_phtech
from test_cargas_pf_guion import _nueva, _plan
from test_cargas_pf_guion_007 import _app

SEMILLA = int(os.environ.get('CSG_SCALE_SEED', random.randrange(1 << 30)))
LAT, LON0 = -14.0, -75.7                     # F1 en el doble: barras F1_Bi en LON0 + 0,001·i
#: ``phtech`` de dos y de una fase (054:RF-3).
NO_TRIFASICAS = {4: 2, 5: 2, 2: 2, 3: 2, 6: 1, 7: 1}


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('cargas_pf.py', 'cargas_pf_fases_081', tools_en_path=True)


@pytest.fixture(scope='module')
def ajuste():
    return cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_fases_081', tools_en_path=True)


def _sorteo(k: int):
    rnd = random.Random(SEMILLA + k)
    alims = tuple(f'F{i}' for i in range(1, rnd.randint(1, 4) + 1))
    phtech = rnd.choice(sorted(NO_TRIFASICAS))
    return rnd, alims, rnd.randint(2, 6), phtech


def _con_fases(app, phtech, nlnph):
    for b in app.proyecto.GetContents('*.ElmTerm', 1):
        b.phtech = phtech
    for t in app.proyecto.GetContents('*.TypLne', 1):
        t.nlnph = nlnph


def _objeto(app, clase, nombre):
    return next(o for o in app.proyecto.GetContents(f'*.{clase}', 1) if o.loc_name == nombre)


def test_fases_y_corriente_del_contrato():
    """081:RF-66 — la corriente por fase de una carga adaptada es √3 veces la trifásica."""
    assert corriente_por_fase_a(173.205, 10.0, 3) == pytest.approx(10.0, rel=1e-4)
    assert corriente_por_fase_a(173.205, 10.0, 1) == pytest.approx(17.3205, rel=1e-4)
    assert corriente_por_fase_a(100.0, 0.0, 1) is None
    assert [fases_de_phtech(x) for x in (0, 1, 4, 6, None)] == [3, 3, 2, 1, 3]


@pytest.mark.parametrize('k', range(3))
def test_sin_barra_trifasica_la_sed_nueva_se_crea_con_las_fases_de_la_barra(guion, k):
    """081:RF-64, 081:RF-65, 081:RF-66, 081:RF-69 — ninguna barra lleva las tres fases: la SED se crea igual,
    con sus barras, su interruptor, su transformador y su línea de enlace de las fases de la barra, y el
    aviso da sus cifras. Antes (054:RF-10) quedaba en «no creadas»."""
    rnd, alims, n, phtech = _sorteo(k)
    fases = NO_TRIFASICAS[phtech]
    app = _app(alimentadores=alims, n=n)
    _con_fases(app, phtech, fases)
    f = rnd.choice(alims)
    i = rnd.randint(1, n)
    barra = _objeto(app, 'ElmTerm', f'{f}_B{i}')
    # A unos 110 m de la barra, en perpendicular: con cable (016:RF-88).
    fila = _nueva('N1', alimentador=f, barra=barra.loc_name, lat=barra.GPSlat + 0.001, lon=barra.GPSlon,
                  kva_instalado=100.0, kw=80.0, kvar=30.0)
    informe, rc = guion.ejecutar(app, _plan(list(alims), nuevas=[fila]), simular=False)
    assert rc == 0 and informe['no_creadas'] == [], (SEMILLA, informe['no_creadas'])
    creada = next(c for x in informe['feeders'] for c in x['creadas'])
    assert creada['fases'] == fases and 'adaptada' in creada['criterio'], SEMILLA
    aviso = next(a for a in informe['avisos'] if '081:RF-66' in a)
    assert '081:RF-9' in aviso and '100 kVA' in aviso and 'por fase' in aviso, aviso
    for v in app.carpetas['scheme'].GetContents('*.IntScheme'):
        v.Activate()
    from convertersmartgrid.dgs import PHTECH_POR_FASES
    for nombre in ('N1', 'N1_BT', 'NODE_N1'):
        assert _objeto(app, 'ElmTerm', nombre).phtech == PHTECH_POR_FASES[fases], nombre
    assert _objeto(app, 'ElmCoup', 'SW_N1').nphase == fases
    tr = _objeto(app, 'ElmTr2', 'TR_N1').typ_id
    assert tr.nt2ph == fases and (tr.tr2cn_h, tr.tr2cn_l) == ('D', 'D') and tr.loc_name.endswith(f'_{fases}F')
    assert _objeto(app, 'ElmLne', 'LNE_N1').typ_id.nlnph == fases


def test_el_tramo_que_se_parte_manda_sobre_su_extremo(guion):
    """081:RF-67 — la carga cae en un tramo de una fase entre barras trifásicas: no se engancha en su barra
    nueva con tres fases, sino en la barra trifásica más cercana, y se dice."""
    app = _app(alimentadores=('F1',))
    linea = _objeto(app, 'ElmLne', 'F1_L2')
    tipo = app.carpetas['equip'].AddCopy(linea.typ_id, 'AAAC_F1_1F')
    tipo.nlnph = 1
    linea.typ_id = tipo
    fila = _nueva('N1', alimentador='F1', lat=LAT + 0.0005, lon=LON0 + 0.0015)
    informe, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[fila]), simular=True)
    (r,) = informe['feeders'][0]['crearian']
    assert rc == 0 and r['fases'] == 3 and not r['parte'] and r['barra'] in ('F1_B1', 'F1_B2'), r
    assert any('081:RF-8' in a and 'N1' in a for a in informe['avisos']), informe['avisos']


@pytest.mark.parametrize('k', range(2))
def test_bancos_de_la_calibracion_sin_barras_trifasicas(ajuste, k):
    """081:RF-68 — sin barras trifásicas en la troncal, los bancos que faltan se ponen igual, con las fases
    de su barra (``ctech``) y su aviso con cifras. Antes (054:RF-10) no se ponía ninguno."""
    from test_ajuste_cabecera_guion import _app as _app_ajuste
    from test_ajuste_cabecera_guion import _plan as _plan_ajuste
    from test_ajuste_proyecto_guion import _de

    rnd = random.Random(SEMILLA + 100 + k)
    phtech = rnd.choice(sorted(NO_TRIFASICAS))
    fases = NO_TRIFASICAS[phtech]
    app = _app_ajuste(escenario=True)
    _con_fases(app, phtech, fases)
    plan = {**_de(_plan_ajuste(kvar=10.0), 'F1', 300.0), 'completar_bancos': True,
            'bancos_kvar_por_tension': {'10': 2.0}}
    [(informe, _rc)] = ajuste.ejecutar_proyecto(app, [plan])
    assert informe['bancos_nuevos'], (SEMILLA, informe.get('avisos'))
    assert all(b['fases'] == fases for b in informe['bancos_nuevos'])
    ctech = {2: 3, 1: 6}[fases]
    for b in informe['bancos_nuevos']:
        assert _objeto(app, 'ElmShnt', b['banco']).ctech == ctech
    assert any('081:RF-68' in a and 'por fase' in a for a in informe['avisos']), informe['avisos']
    assert not any('no se ponen (054:RF-10)' in a for a in informe['avisos'])
