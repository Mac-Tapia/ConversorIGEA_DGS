"""Spec 006: ``tools/ajuste_cabecera_pf.py`` contra un DIgSILENT simulado (``fake_pf``).

DIgSILENT no se ejecuta en la suite (P11): el doble calcula lo que entra por la cabecera
con pérdidas cuadráticas y deja de converger por encima de un límite. La prueba real, con
el signo y el lado de la cabecera, la hace el usuario (T8).
"""
from __future__ import annotations

import os
import random

import pytest

import fake_pf
from apoyo import cargar_herramienta

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED', random.randrange(1 << 30)))


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_cabecera_pf_guion',
                              tools_en_path=True)


def _app(n=6, **kw):
    kw.setdefault('kva', lambda f, i: 50.0 * i)
    return fake_pf.proyecto(alimentadores=('F1', 'F2'), cargas_por_alim=n, bt=True, flujo=True,
                            **kw)


def _plan(kw=300.0, kvar=90.0, clientes=(), kva_entrada=None, tolerancia=0.01, max_flujos=None):
    return {'project': 'P', 'feeder': 'F1', 'stamp': '20261009_120000',
            'variacion': 'Ajuste_F1_20261009_120000',
            'objetivo': {'kw': kw, 'kvar': kvar, 'medidor': 'M1', 'alimentador': 'F1',
                         'fecha': '2026-03-03 10:00:00'},
            'clientes': list(clientes), 'kva_entrada': kva_entrada or {},
            'tolerancia': tolerancia, 'max_flujos': max_flujos,
            'project_binding': {'native_reread': {
                'status': 'VERIFICADO_PERSISTENCIA',
                'capacitor_reread': {'status': 'VERIFICADO_PERSISTENCIA', 'expected': 3},
            }}}


def _carga(app, nombre):
    return next(o for o in app.proyecto.GetContents('*.ElmLod', 1) if o.loc_name == nombre)


def _sed(informe, sed):
    return next(x for x in informe['sed'] if x['sed'] == sed)


def test_cuadra_la_cabecera_en_una_variacion_nueva(guion):
    """006:RF-4 / 006:RF-11 / 006:RF-19 / 006:RF-21 — solo el alimentador elegido, en su variación, y
    el informe con objetivo, cabecera, pérdidas, error y flujos."""
    app = _app(escenario=True)
    otra = _carga(app, 'F2_S1').plini
    informe, rc = guion.ejecutar(app, _plan())
    assert rc == 0, informe
    assert informe['cuadrado'] and abs(informe['desvio']['kw']) <= 0.01
    assert informe['status'] == 'AVISO_KVAR'
    assert informe['kvar_no_bloqueante']['bloquea'] is False
    assert informe['kvar_no_bloqueante']['supera_tolerancia']
    reread = informe['relectura_cargas_nativas']
    assert reread['status'] == 'VERIFICADO_PERSISTENCIA'
    assert reread['cantidad'] == len(informe['sed'])
    assert all({'p_kw', 'q_kvar', 'fp', 'outserv', 'i_scale', 'full_name'} <= set(x)
               for x in reread['despues'])
    assert informe['relectura_bancos']['expected'] == 3
    # «error» es solo para fallos: la web lo toma por uno y paraba un ajuste que cuadró.
    assert 'error' not in informe
    assert informe['perdidas']['kw'] > 0 and 1 <= informe['flujos'] < 20
    assert [v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme')] == [informe['variacion']]
    escritas = [e for e in app.escrituras if getattr(e[0], '_clase', '') == 'ElmLod']
    assert escritas and all(e[3] is not None and e[4] is None for e in escritas), \
        'todo en la etapa que graba y con el escenario apagado'
    assert app.escenario is not None, 'el escenario del operador vuelve a estar activo'
    assert _carga(app, 'F2_S1').plini == otra
    fila = _sed(informe, 'F1_S3')
    assert fila['antes']['kw'] == pytest.approx(50.0) and fila['kva_de'] == 'pf'


def test_kva_de_los_transformadores_y_reparto_proporcional(guion):
    """006:RF-8 — kW por kVA igual en todas las repartidas; kVA del transformador en PF."""
    rnd = random.Random(SEMILLA)
    tamanos = {i: rnd.choice([25.0, 50.0, 100.0, 160.0, 250.0]) for i in range(1, 30)}
    app = _app(n=rnd.randint(5, 25), kva=lambda f, i: tamanos[i])
    informe, rc = guion.ejecutar(app, _plan(kw=900.0, kvar=250.0))
    assert rc == 0, (SEMILLA, informe)
    ratios = {round(x['despues']['kw'] / x['kva'], 9) for x in informe['sed']}
    assert len(ratios) == 1, SEMILLA
    assert {x['kva'] for x in informe['sed']} <= set(tamanos.values())


def test_sed_con_clientes_lleva_su_demanda(guion):
    """006:RF-5 / 006:RF-9 — la SED del cliente con su Pot, fija; la que no está, omitida."""
    app = _app()
    clientes = [{'codigo': '11', 'sed': 'f1_s2', 'pot': 40.0, 'ea': 1.0, 'eri': 0.25},
                {'codigo': '12', 'sed': 'ZZ9', 'pot': 10.0, 'ea': 1.0, 'eri': 0.1}]
    informe, rc = guion.ejecutar(app, _plan(clientes=clientes))
    assert rc == 0, informe
    fila = _sed(informe, 'F1_S2')
    assert fila['origen'] == 'cliente' and fila['clientes'] == ['11']
    assert fila['despues']['kw'] == pytest.approx(40.0)
    assert fila['despues']['kvar'] == pytest.approx(10.0)
    assert fila['despues']['fp'] == pytest.approx(1 / (1 + 0.25**2) ** 0.5)
    assert fila['derivaciones'] == [{
        'cliente': '11', 'p_kw': 40.0, 'q_kvar': 10.0,
        'fp': pytest.approx(1 / (1 + 0.25**2) ** 0.5),
        'metodo': 'ERI/EA', 'ea': 1.0, 'eri': 0.25,
    }]
    assert _carga(app, 'F1_S2').plini == pytest.approx(0.040)
    assert [o['sed'] for o in informe['omitidas']] == ['ZZ9']


def test_kva_de_la_entrada_original(guion):
    """006:RF-10 — sin transformador en DIgSILENT, el kVA de la entrada original, y se dice."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=3, bt=True, flujo=True,
                           con_trafos=False)
    informe, rc = guion.ejecutar(app, _plan(kva_entrada={'F1_S1': 100.0, 'F1_S2': 100.0,
                                                         'f1 s3': 200.0}))
    assert rc == 0, informe
    assert {x['kva_de'] for x in informe['sed']} == {'entrada'}
    assert _sed(informe, 'F1_S3')['kva'] == 200.0
    assert any('entrada original' in a for a in informe['avisos'])


def test_sin_kva_en_ningun_sitio_no_se_escribe(guion):
    """006:RF-24 — una SED sin kVA ni en DIgSILENT ni en la entrada: error y nada escrito."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=3, bt=True, flujo=True,
                           con_trafos=False)
    informe, rc = guion.ejecutar(app, _plan(kva_entrada={'F1_S1': 100.0}))
    assert rc == 2 and 'F1_S2' in informe['error']
    assert not app.carpetas['scheme'].GetContents('*.IntScheme')


def test_simular_no_escribe(guion):
    """006:RF-20 — el reparto sin pérdidas por SED, sin variación ni escrituras."""
    app = _app()
    informe, rc = guion.ejecutar(app, _plan(), simular=True)
    assert rc == 0 and informe['modo'] == 'simular'
    assert informe['totales_sin_perdidas']['kw'] == pytest.approx(300.0)
    assert not app.escrituras and app.ldf.ejecuciones == 0


def test_no_converge_remedios_y_ajustes_restituidos(guion):
    """006:RF-15 / 006:RF-16 / 006:RF-17 — remedios por orden, el informe dice qué cambió, y el
    ComLdf del operador queda como estaba."""
    app = _app()
    # MW de carga de F1: con 900 kW hacen falta dos remedios (F2 tiene 0,3 MW y converge).
    app.ldf.limite, app.ldf.por_ajuste = 0.6, 0.2
    informe, rc = guion.ejecutar(app, _plan(kw=900.0, kvar=250.0))
    assert rc == 0 and informe['cuadrado'], informe
    nombres = [r['remedio'] for r in informe['remedios']]
    assert nombres[:3] == ['acercarse en pasos', 'más iteraciones', 'paso automático']
    assert any('itrlx: 25 → 75' in c for r in informe['remedios'] for c in r['cambios'])
    assert app.ldf.itrlx == 25 and app.ldf.iStepAdapt == 0
    assert informe['ajustes_restituidos'] == {'itrlx': 25, 'iStepAdapt': 0}
    assert 'sed_por_encima_de_su_transformador' in informe['diagnostico']


def test_sin_cuadrar_queda_el_ultimo_que_convergio(guion):
    """006:RF-18 — agotados los remedios: variación con el último reparto bueno, marcada."""
    app = _app(kva=lambda f, i: 100.0)
    app.ldf.limite = 0.5
    informe, rc = guion.ejecutar(app, _plan(kw=900.0, kvar=250.0))
    assert rc == 2 and not informe['cuadrado']
    assert any('NO cumple' in a for a in informe['avisos'])
    total = sum(_carga(app, f'F1_S{i}').plini for i in range(1, 7))
    assert total <= 0.5 + 1e-9
    # 900 kW entre 6 SED de 100 kVA: cada una pedía más que su transformador.
    assert len(informe['diagnostico']['sed_por_encima_de_su_transformador']) == 6
    assert informe['cabecera'] is not None
    assert informe['diagnostico']['tension_minima']['barra'].startswith('F1_')


def test_cancelar(guion):
    """006:RF-22 — cancelar termina el flujo en curso y deja el último reparto que convergió."""
    app = _app()
    llamadas = []

    def cancelado():
        llamadas.append(1)
        return len(llamadas) > 1

    informe, rc = guion.ejecutar(app, _plan(tolerancia=0.001), cancelado=cancelado)
    assert informe['cancelado'] and informe['flujos'] == 1
    assert any('Cancelado' in a for a in informe['avisos'])


def test_sin_cabecera_no_se_ajusta(guion):
    """006:RF-4 — un alimentador sin ElmFeeder con cabecera no se puede medir."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=2, flujo=True)
    informe, rc = guion.ejecutar(app, _plan())
    assert rc == 2 and 'cabecera' in informe['error']


def test_error_inesperado_deja_informe(guion, tmp_path, monkeypatch):
    """008:RF-17 — si ``ejecutar`` revienta, ``main`` escribe el informe con el error y su tipo."""
    import json
    import sys
    import types

    app = _app()
    monkeypatch.setitem(sys.modules, 'powerfactory', types.SimpleNamespace(GetApplicationExt=lambda: app))

    def revienta(*_a, **_k):
        raise AttributeError("'NoneType' object has no attribute 'obj_id'")

    monkeypatch.setattr(guion, 'ejecutar', revienta)
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps(_plan()), encoding='utf-8')
    salida = tmp_path / 'informe.json'
    rc = guion.main(['--plan', str(plan), '--output-json', str(salida)])
    informe = json.loads(salida.read_text(encoding='utf-8'))
    assert rc == 1
    assert 'AttributeError' in informe['error'] and 'obj_id' in informe['error']
    assert informe['feeder'] == 'F1' and informe['modo'] == 'aplicar'
