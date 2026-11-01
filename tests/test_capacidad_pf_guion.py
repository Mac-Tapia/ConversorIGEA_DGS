"""Spec 012, T6: ``tools/capacidad_pf.py`` contra ``fake_pf``, desde ``tools/estudios_pf.py``.

Capacidad de alojamiento nodo a nodo y conjunta, curvas PV con y sin contingencias y
ubicación de condensadores en una variación temporal. Proyectos y bancos sorteados.
"""

from __future__ import annotations

import random

import pytest

import fake_pf
from apoyo import cargar_herramienta
from convertersmartgrid import datos_empresa as de
from test_confiabilidad_pf_guion import _alim, _plan_estudio, casos_pf
from test_estudios_pf_guion import _bbone_que_crea

estudios = cargar_herramienta('estudios_pf.py', 'estudios_cap_012', tools_en_path=True)
cap = cargar_herramienta('capacidad_pf.py', 'capacidad_012', tools_en_path=True)

SEMILLAS = (6, 17, 44, 83)
LIMITES = {'tension_min_pu': 0.93, 'tension_max_pu': 1.06, 'cargabilidad_max_pct': 95.0}


def _red(rng):
    alims = tuple(f'F{i}' for i in range(1, rng.randint(1, 3) + 1))
    app = fake_pf.proyecto(alimentadores=alims, cargas_por_alim=rng.randint(2, 5), bt=True, flujo=True)
    base = {'variaciones': [], 'feeders': list(alims), 'excluidos': [],
            'ajustes': [{'feeder': f, 'cuadrado': True} for f in alims]}
    informe, codigo = casos_pf.preparar(app, {'project': 'P', 'feeders': list(alims), 'base': base,
                                              'caso_base_sin_verificar': {}})
    assert codigo == 0, informe
    app.escrituras.clear()
    return app, list(alims)


def _demandas(app):
    return {c.loc_name: (c.plini, c.qlini) for c in app.proyecto.GetContents('*.ElmLod', 1)}


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_alojamiento_nodo_a_nodo_con_su_motivo(semilla):
    """012:RF-41, 012:RF-42, 012:RF-43, 012:RF-44, 012:RF-47, 012:RF-48, 012:RF-72, 012:RF-3,
    012:RF-5 — generación y carga máximas en cada nodo de media tensión, con el elemento que
    limita y su motivo; el nodo sin carga conectada lo dice; solo límites térmicos y de
    tensión, los del perfil; ninguna demanda cambia."""
    rng = random.Random(semilla)
    app, alims = _red(rng)
    antes = _demandas(app)
    informe, rc = estudios.ejecutar(app, _plan_estudio(alims, 'alojamiento', limites=LIMITES))
    assert rc == 0, informe
    mt = {b.loc_name for f in alims for b in _alim(app, f).GetObjs('ElmTerm') if b.uknom >= 1}
    assert {n['nodo'] for n in informe['nodos']} == mt
    for n in informe['nodos']:
        assert n['gd_motivo'] == 'tensión' and n['gd_kw'] > 0 and n['gd_limita']
        if n['nodo'].endswith('_B0'):                         # la cabecera no tiene SED
            assert n['carga_kw'] is None and n['carga_motivo'] == 'sin carga conectada'
        else:
            assert n['carga_kw'] == pytest.approx(2000.0)
    for f in alims:
        gds = [n['gd_kw'] for n in informe['nodos'] if n['alimentador'] == f]
        assert informe['red'][f]['capacidad_gd_max_kw'] == max(gds)
    hc = next(o for o in app.creados if o.GetClassName() == 'ComHostcap')
    assert (hc.if_volmin, hc.if_volmax, hc.if_load) == (0.93, 1.06, 95.0)
    assert (hc.iLoad, hc.iVolt, hc.ioptProt, hc.ioptPqual, hc.iopt_shc) == (1, 1, 0, 0, 0)
    assert not app.GetActiveStudyCase().GetContents('*.ComHostcap') and informe['fiable']
    assert _demandas(app) == antes


def test_alojamiento_conjunto_solo_con_las_escalables():
    """012:RF-45, 012:RF-46 — el crecimiento conjunto sube a la vez solo las cargas escalables:
    la selección de cargas de DIgSILENT lleva las escalables y no las fijas."""
    rng = random.Random(3)
    app, alims = _red(rng)
    fija = _alim(app, alims[0]).GetObjs('ElmLod')[0]
    fija.i_scale = 0
    informe, rc = estudios.ejecutar(app, _plan_estudio(alims, 'alojamiento', opciones={'conjunto': True}))
    assert rc == 0, informe
    assert all('conjunto_kw' in n for n in informe['nodos'])
    sel = [o for o in app.creados if o.GetClassName() == 'SetSelect' and o.loc_name.startswith(f'Escalables_{alims[0]}')]
    assert sel and fija not in sel[0].All() and sel[0].All()
    assert not app.GetActiveStudyCase().GetContents('*.SetSelect')


@pytest.mark.parametrize('contingencias', [False, True])
def test_curva_pv_por_alimentador(contingencias):
    """012:RF-50, 012:RF-51, 012:RF-52, 012:RF-53 — una curva por alimentador con sus cargas
    escalables; demanda inicial y crítica, margen y barra crítica; con contingencias, las de
    su troncal y la más crítica; sin licencia para ellas, sin contingencias y dicho."""
    rng = random.Random(11)
    app, alims = _red(rng)
    app.ordenes['ComBbone'] = fake_pf.Orden(app, 'BB', clase='ComBbone', efecto=_bbone_que_crea(alims))
    app.licencia_pv_contingencias = False
    fija = _alim(app, alims[0]).GetObjs('ElmLod')[0]
    fija.i_scale = 0
    informe, rc = estudios.ejecutar(app, _plan_estudio(alims, 'curvas_pv',
                                                       opciones={'contingencias': contingencias}))
    assert rc == 0, informe
    assert set(informe['red']) == set(alims)
    for f in alims:
        r = informe['red'][f]
        escal = [c for c in _alim(app, f).GetObjs('ElmLod') if getattr(c, 'i_scale', 1)]
        assert r['demanda_inicial_kw'] == pytest.approx(sum(c.plini for c in escal) * 1000, abs=10)
        assert r['margen_kw'] == pytest.approx(r['demanda_critica_kw'] - r['demanda_inicial_kw'])
        assert r['barra_critica'] and r['margen_pct'] > 0
    pv = [o for o in app.creados if o.GetClassName() == 'ComPvcurves']
    assert len(pv) == len(alims) and all(o.frLoads == 1 for o in pv)
    assert fija not in pv[0].pSel_Load.All()
    if contingencias:
        assert any('contingencias' in a for a in informe['avisos'])
        assert all(o.calcCont == 0 for o in pv)
    assert not app.GetActiveStudyCase().GetContents('*.ComSimoutage')


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_condensadores_sin_instalar_nada(semilla):
    """012:RF-54, 012:RF-55, 012:RF-56, 012:RF-66, 012:RF-15, 012:RF-64 — ``ComCapo`` por
    alimentador con los bancos y el coste de la energía del libro; informa cada banco con su
    nodo, kvar, pasos, inversión, vida, tasa y coste anual, y el ahorro; no queda ninguno."""
    rng = random.Random(semilla)
    app, alims = _red(rng)
    tasa = rng.uniform(0.01, 0.15)
    bancos = [de.Banco(q, rng.randint(1, 4), True, rng.uniform(100, 5000), rng.randint(5, 25), 0.0)
              for q in rng.sample([50.0, 100.0, 150.0, 300.0], 2)]
    bancos = [de.Banco(b.potencia_kvar, b.pasos, b.trifasico, b.inversion, b.vida_anios,
                       de.anualidad(b.inversion, tasa, b.vida_anios)) for b in bancos]
    libro = de.Libro(bancos=bancos, coste_energia_kwh=rng.uniform(0.01, 0.5), moneda='M', tasa_descuento=tasa)
    f = alims[0]
    barra = f'{f}_B2'
    app.capo_propuestas = [(barra, 1, 2)]
    app.capo_coste = (500.0, 420.0)
    previas = {v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1)}
    informe, rc = estudios.ejecutar(app, _plan_estudio([f], 'condensadores', libro=libro.a_dict(),
                                                       limites=LIMITES))
    assert rc == 0, informe
    fila = informe['red'][f]
    (b,) = fila['bancos']
    assert (b['nodo'], b['kvar_paso'], b['pasos']) == (barra, bancos[1].potencia_kvar, 2)
    assert b['coste_anual'] == pytest.approx(bancos[1].coste_anual) and b['tasa_descuento'] == tasa
    assert fila['ahorro_anual'] == pytest.approx(80.0)
    capo = next(o for o in app.creados if o.GetClassName() == 'ComCapo')
    assert capo.ecost == libro.coste_energia_kwh and capo.iopt_con == 1
    assert capo.shntcost == pytest.approx([x.coste_anual for x in bancos])
    assert (capo.vmin, capo.vmax) == (0.93, 1.06)
    assert {v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1)} == previas
    assert not _alim(app, f).GetObjs('ElmShnt') and informe['fiable']


def test_condensadores_sin_propuesta_se_dice():
    """012:RF-57 — si no propone ningún banco, se dice por alimentador."""
    app, alims = _red(random.Random(2))
    libro = de.Libro(bancos=[de.Banco(150.0, 2, True, 100.0, 10, 13.0)], coste_energia_kwh=0.1, tasa_descuento=0.0)
    informe, rc = estudios.ejecutar(app, _plan_estudio(alims, 'condensadores', libro=libro.a_dict()))
    assert rc == 0, informe
    assert all(informe['red'][f]['bancos'] == [] for f in alims)
    assert sum('ningún banco' in a for a in informe['avisos']) == len(alims)


def test_ayuda_sin_digsilent():
    """012:RF-50 — la herramienta responde a ``--help`` sin abrir DIgSILENT (spec 009)."""
    with pytest.raises(SystemExit) as e:
        cap.main(['--help'])
    assert e.value.code == 0
