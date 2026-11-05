"""087:RF-1 a RF-6, RF-10 a RF-13, RF-28 — el oráculo en la escalera por alimentador, por tandas."""
from __future__ import annotations

import pytest
from apoyo import cargar_herramienta
from test_optimizacion_oraculo import _alimentador, _dos_cargas, _espacio, _grafo, _p, NUEVA, TIPOS

from convertersmartgrid import optimizacion_oraculo as oo
from convertersmartgrid.escalera_optima import Variante
from convertersmartgrid.web import services
from convertersmartgrid.web.jobs import JobCancelled


class _Ctx:
    def __init__(self):
        self.textos = []

    def log(self, texto='', *_a, **_k):
        self.textos.append(texto)

    def check_cancel(self):
        pass


def _aplicadas():
    return [{'sed': 'A', 'alimentador': 'F1', 'kw': 100.0, 'variacion': 'Carga_A'}]


def _v(n):
    return Variante(n, ('bancos',), [{'clase': 'condensador', 'barra': 'B', 'q_kvar': 100.0}], {'bancos': 1.0})


@pytest.fixture(autouse=True)
def _medicion_aparte(monkeypatch, tmp_path):
    monkeypatch.setattr(services, '_ruta_de_medicion', lambda nombre: tmp_path / nombre)
    # 087:RF-45: la confirmación conjunta tiene sus pruebas en test_obras_integrales; aquí, que cumple.
    monkeypatch.setattr(services, 'confirmar_conjunto', lambda *a, **k: {'cumple': True})


def _con_seleccion(monkeypatch, seleccion, cumple_en):
    llamadas = []
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: _aplicadas())
    monkeypatch.setattr(services, '_reponer_cargas_nuevas', lambda *a, **k: None)
    monkeypatch.setattr(services, '_seleccion_por_oraculo', lambda *a, **k: seleccion)

    def escalera(ws, ctx, project, feeders, *, aplicar=False, variantes_de=None, solo=None, **k):
        llamadas.append({'aplicar': aplicar, 'variantes': [v.nombre for v in (variantes_de or {}).get(feeders[0], [])], 'solo': solo})
        if aplicar:
            return {'alimentadores': []}
        nombres = llamadas[-1]['variantes']
        tabla = [{'nombre': n, 'maxima': n == cumple_en, 'fraccion': 1.0 if n == cumple_en else None} for n in nombres]
        return {'alimentadores': [{'alimentador': feeders[0], 'elegida': cumple_en if cumple_en in nombres else None, 'tabla': tabla}]}

    monkeypatch.setattr(services, 'obras_escalera', escalera)
    return llamadas


def _seleccion(n, buenas=None):
    orden = [_v(f'v{i}') for i in range(n)]
    buenas = n if buenas is None else buenas
    tabla = [{'nombre': v.nombre, 'cumple': i < buenas, 'costo_anual': 1000.0 + i if i < buenas else None, 'v_min': 0.97}
             for i, v in enumerate(orden)]
    return {'alimentadores': {'F1': {'orden': orden, 'tabla': tabla, 'bayesiana': {'cumplen': 1}, 'pareto': {'frente': []},
                                     'perdidas_energia': {'energia_kwh_anio': 10.0}, 'ya_cumple': False}}, 'tanda': 3}


def test_digsilent_mide_primero_una_tanda_y_para_si_cumple(monkeypatch):
    """087:RF-1, 087:RF-2 — del orden del oráculo, DIgSILENT mide solo la primera tanda si en ella hay obra."""
    llamadas = _con_seleccion(monkeypatch, _seleccion(7), 'v1')
    r = services.escalera_por_alimentador(object(), _Ctx(), 'P', ['F1'])
    medidas = [x for x in llamadas if not x['aplicar']]
    assert [x['variantes'] for x in medidas] == [['v0', 'v1', 'v2']]
    assert r['por_alimentador']['F1']['cumple']


def test_si_la_tanda_no_cumple_mide_la_siguiente_y_aplica_la_medida(monkeypatch):
    """087:RF-3, 087:RF-12 — hasta agotar; se aplica la que midió DIgSILENT, aunque no esté en la lista de la escalera."""
    llamadas = _con_seleccion(monkeypatch, _seleccion(7), 'v4')
    services.escalera_por_alimentador(object(), _Ctx(), 'P', ['F1'])
    medidas = [x['variantes'] for x in llamadas if not x['aplicar']]
    assert medidas == [['v0', 'v1', 'v2'], ['v3', 'v4', 'v5']]
    aplicada = next(x for x in llamadas if x['aplicar'])
    assert aplicada['variantes'] == ['v4'] and aplicada['solo'] == {'F1': 'v4'}



def test_solo_las_cumplidoras_y_una_tanda_de_cercanas():
    """087:RF-39 — de 9 variantes, 2 cumplidoras en el oráculo y una tanda de 3 cercanas: las otras 4 no se miden."""
    assert [v.nombre for v in oo.a_confirmar(_seleccion(9, buenas=2)['alimentadores']['F1'], 3)] == ['v0', 'v1', 'v2', 'v3', 'v4']
    assert [v.nombre for v in oo.a_confirmar(_seleccion(9, buenas=0)['alimentadores']['F1'], 3)] == ['v0', 'v1', 'v2']


def test_si_no_cumplen_va_a_la_obra_integral_sin_medir_las_demas(monkeypatch):
    """087:RF-40 — ninguna de las de RF-39 cumple: no se insiste con las otras, el alimentador va a la obra integral."""
    llamadas = _con_seleccion(monkeypatch, _seleccion(9, buenas=2), 'v8')
    ctx = _Ctx()
    r = services.escalera_por_alimentador(object(), ctx, 'P', ['F1'])
    medidas = [x['variantes'] for x in llamadas if not x['aplicar']]
    # Después, sin lista del oráculo, el paso a 22,9 kV (087:RF-41) y transferir o trasladar (087:RF-31).
    assert medidas == [['v0', 'v1', 'v2'], ['v3', 'v4'], [], []]
    assert not r['por_alimentador']['F1']['cumple'] and not any(x['aplicar'] for x in llamadas)
    assert any('087:RF-40' in t and 'las otras 4 no se prueban' in t for t in ctx.textos)


def test_lo_predicho_y_lo_medido_quedan_y_manda_digsilent(monkeypatch):
    """087:RF-6 — el oráculo daba por buenas todas; DIgSILENT rechaza y no se elige ninguna."""
    _con_seleccion(monkeypatch, _seleccion(4), 'ninguna')
    r = services.escalera_por_alimentador(object(), _Ctx(), 'P', ['F1'])
    f1 = r['por_alimentador']['F1']
    assert not f1['cumple'] and len(f1['oraculo']['comparacion']) == 4
    fila = f1['oraculo']['comparacion'][0]
    assert fila['oraculo_cumple'] is True and fila['digsilent_maxima'] is False
    assert f1['oraculo']['perdidas_energia'] and f1['oraculo']['pareto'] is not None and f1['oraculo']['bayesiana']


def test_sin_oraculo_mide_digsilent_como_siempre(monkeypatch):
    """087:RF-4 — si el oráculo falla no se queda sin obras: se dice el motivo y mide DIgSILENT."""
    monkeypatch.setattr(services, 'obras_escalera', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('sin grafo')))
    ctx = _Ctx()
    assert services._seleccion_por_oraculo(object(), ctx, 'P', ['F1'], _aplicadas(), {}, {}) == {}
    assert any('087:RF-4' in t and 'sin grafo' in t for t in ctx.textos)
    llamadas = _con_seleccion(monkeypatch, {}, 'x')
    services.escalera_por_alimentador(object(), _Ctx(), 'P', ['F1'])
    assert llamadas[0]['variantes'] == []


def test_la_cancelacion_no_se_toma_por_un_fallo_del_oraculo(monkeypatch):
    """087:RF-4 — cancelar el trabajo no cae a medir en DIgSILENT."""
    monkeypatch.setattr(services, 'obras_escalera', lambda *a, **k: (_ for _ in ()).throw(JobCancelled()))
    with pytest.raises(JobCancelled):
        services._seleccion_por_oraculo(object(), _Ctx(), 'P', ['F1'], _aplicadas(), {}, {})


def test_el_oraculo_recibe_los_tramos_sobrecargados():
    """087:RF-5 — el constructor del oráculo pasa a las variantes el mismo dato que la escalera."""
    import inspect

    fuente = inspect.getsource(services._preparar_oraculo)
    assert "sobrecargados=d.get('sobrecargados')" in fuente and "'cargabilidad_max_pct'" in fuente


def test_el_que_ya_cumple_no_gasta_busqueda():
    """087:RF-10, 087:RF-11 — sin bayesiana ni frente para quien ya cumple; con ellas, para quien no."""
    ora = oo.Oraculo(_grafo(r=0.1, x=0.1), [{**NUEVA, 'alimentador': 'F1', 'barra': 'B'}], tipos=TIPOS)
    e = oo.seleccion_por_alimentador(ora, [_alimentador(_espacio())], _p(), evaluaciones_bayes=5)['F1']
    assert e['ya_cumple'] and e['bayesiana'] is None and e['pareto'] is None
    malo = _dos_cargas()
    e = oo.seleccion_por_alimentador(malo, [_alimentador(_espacio())], _p(), evaluaciones_bayes=5)['F1']
    assert not e['ya_cumple'] and e['bayesiana']['evaluaciones'] > 0 and e['pareto'] is not None
    assert [v.nombre for v in e['orden']] and e['elegida'] == e['orden'][0].nombre


def test_las_perdidas_de_energia_con_la_cadena_de_markov():
    """087:RF-13 — la media por probabilidad estacionaria de las pérdidas de cada nivel, por 8 760 h."""
    ora = _dos_cargas()
    markov = {'estacionaria': [0.25, 0.75], 'sorteos': [{'nivel': 0, 'factores': {'F1': 0.5}}, {'nivel': 1, 'factores': {'F1': 1.0}}]}
    r = oo.perdidas_de_energia_markov(ora, [], 2, markov, 'F1')
    esperado = 0.25 * ora.medir([], 2, 0.5, 'F1').perdidas_kw + 0.75 * ora.medir([], 2, 1.0, 'F1').perdidas_kw
    assert r['perdidas_medias_kw'] == pytest.approx(esperado, abs=1e-3) and r['energia_kwh_anio'] == pytest.approx(esperado * 8760.0, rel=1e-3)
    assert oo.perdidas_de_energia_markov(ora, [], 2, {'estacionaria': [], 'sorteos': []}) is None


def test_las_tandas_no_pierden_ninguna_variante():
    """087:RF-3 — todas las variantes, en su orden, de n en n."""
    orden = [_v(str(i)) for i in range(7)]
    assert [len(t) for t in oo.tandas(orden, 3)] == [3, 3, 1]
    assert [v for t in oo.tandas(orden, 3) for v in t] == orden


def test_la_base_de_sin_proyecto_se_mide_una_vez(tmp_path):
    """087:RF-28 — guardada y leída; si no son los mismos sorteos o no hay fichero, se vuelve a medir."""
    guion = cargar_herramienta('obras_pf.py', 'obras_rf28', tools_en_path=True)
    ruta = str(tmp_path / 'base.json')
    assert guion.base_guardada(ruta, 2, 0) is None and guion.base_guardada(None, 2, 0) is None
    medida = {'converge': True, 'u': {'B': 0.97}, 'carga': {'L': 40.0}, 'perdidas_kw': 1.5}
    guion.guardar_base(ruta, [medida, medida], [])
    assert guion.base_guardada(ruta, 2, 0) == ([medida, medida], [])
    assert guion.base_guardada(ruta, 1, 0) is None and guion.base_guardada(ruta, 2, 1) is None
    assert guion.base_guardada(ruta, 3, 0) == ([medida, medida], [])        # 042:RF-87: la primera etapa vale
    guion.guardar_base(None, [], [])


def test_cada_combinacion_con_su_fichero_base():
    """087:RF-28 — otras cargas apartadas son otra base; sin carpeta del trabajo no se guarda nada."""
    from pathlib import Path

    uno = services._fichero_base({'dir_base': 'x'}, {'feeders': ['F1'], 'apartar_variaciones': ['a']})
    dos = services._fichero_base({'dir_base': 'x'}, {'feeders': ['F1'], 'apartar_variaciones': ['b']})
    assert uno != dos and Path(uno['base_sin_fichero']).parent == Path('x')
    assert services._fichero_base(None, {}) == {}


def test_el_margen_de_demanda_por_biseccion():
    """087:RF-29 — sin holgura, 0; con ella, justo antes de incumplir; con la obra, más que sin ella."""
    malo = _dos_cargas()
    assert oo.margen_de_demanda(malo, [], 2, _p(), 'F1') == 0.0
    ora = oo.Oraculo(_grafo(r=1.2, x=0.9), [{**NUEVA, 'alimentador': 'F1', 'barra': 'B'}], tipos=TIPOS)
    p = _p()
    m = oo.margen_de_demanda(ora, [], 1, p, 'F1')
    assert m > 0
    medida = ora.medir([], 1, 1.0 + m, 'F1')
    assert all(p.tension_min_pu <= u for u in medida.u.values())
    terna = [{'clase': 'terna', 'tramos': ['T1', 'T2']}]
    assert oo.margen_de_demanda(ora, terna, 1, p, 'F1') > m


def test_el_perfil_puede_apagar_el_oraculo_para_comparar(monkeypatch):
    """087:RF-30 — con ``escalera.usar_oraculo`` falso se mide todo en DIgSILENT, y se dice el método."""
    llamadas = _con_seleccion(monkeypatch, _seleccion(4), 'x')
    monkeypatch.setattr('convertersmartgrid.perfil_empresa.datos_perfil', lambda *a, **k: {'escalera': {'usar_oraculo': False}})
    r = services.escalera_por_alimentador(object(), _Ctx(), 'P', ['F1'])
    assert llamadas[0]['variantes'] == [] and r['metodo'] == 'escalera'


def test_lo_medido_se_guarda_sin_nombres(monkeypatch, tmp_path):
    """087:RF-17 — el conjunto del modelo lleva números y el resultado de DIgSILENT; ningún nombre de variante."""
    from convertersmartgrid import modelo_obras as mo

    _con_seleccion(monkeypatch, _seleccion(4), 'v1')
    services.escalera_por_alimentador(object(), _Ctx(), 'P', ['F1'])
    filas = mo.leer(tmp_path / 'variantes_medidas.jsonl')
    assert len(filas) == 3 and sum(f['cumple'] for f in filas) == 1
    assert all(set(f) == {'sistema', 'grupo', 'rasgos', 'cumple'} and set(f['rasgos']) == set(mo.RASGOS) for f in filas)
    assert 'v1' not in (tmp_path / 'variantes_medidas.jsonl').read_text(encoding='utf-8')
