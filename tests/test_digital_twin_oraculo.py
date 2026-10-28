"""Spec 024, T11: oráculo PINN/GNN del estado eléctrico, con redes radiales sintéticas.

Las tensiones objetivo salen del barrido físico de ``ModeloRadial`` (el mismo contrato que
la PINN, RF-38): así la prueba entrena y evalúa de verdad sin DIgSILENT.
"""
from __future__ import annotations

import random

import numpy as np
import pytest

torch = pytest.importorskip('torch')

from test_digital_twin_episode import _payload

from igea_dgs.digital_twin import oraculo as orc
from igea_dgs.digital_twin.buffer import BuferEpisodios
from igea_dgs.digital_twin.episode import episodio_a_dict, leer_episodio
from igea_dgs.digital_twin.escenarios import Escenario

CFG = orc.Entrenamiento(epocas=120, lr=5e-3, ocultas=32, pasos=6)


def red_radial(rnd: random.Random, n: int, carga: float = 1.0) -> dict:
    """Árbol de ``n`` barras de 10 kV con fuente en N0, tramos y cargas sorteados."""
    nodos = {f'N{i}': {'kv': 10.0, 'p_mw': 0.0 if i == 0 else rnd.uniform(0.05, 0.25) * carga,
                       'q_mvar': 0.0 if i == 0 else rnd.uniform(0.01, 0.08) * carga, 'fuente': i == 0,
                       'v_pu': 1.0 if i == 0 else None}
             for i in range(n)}
    ramas = [{'id': f'L{i}', 'desde': f'N{rnd.randrange(max(0, i - 3), i)}', 'hasta': f'N{i}',
              'cerrada': True, 'r_ohm': rnd.uniform(0.2, 0.8), 'x_ohm': rnd.uniform(0.2, 0.6),
              'inom_ka': 0.2} for i in range(1, n)]
    return {'version': orc.VERSION_GRAFO, 'nodos': nodos, 'ramas': ramas}


def _tensiones(grafo):
    p = orc.ModeloRadial().predecir(grafo)
    return dict(zip(p['ids'], map(float, p['v']), strict=True))


def _episodio(grafo, i, clase='counterfactual'):
    p = _payload(clase=clase)
    p['nativo']['feeders'] = [f'A{i % 4}']
    p['accion']['escenario'] = {'factor_carga': 1.0, 'tramos_abiertos': [f'T{i}']}
    p['topologia'] = {'grafo': grafo}
    p['flujo']['tensiones'] = {'unidad': 'p.u.', 'valores': _tensiones(grafo)}
    return leer_episodio(p)


@pytest.fixture(scope='module')
def entrenado(tmp_path_factory):
    rnd = random.Random(11)
    bufer = BuferEpisodios(tmp_path_factory.mktemp('twin'))
    # 027:RF-2, RF-3: cuatro redes de tamaño distinto con 12 escenarios de carga cada una, para
    # que una red entera quede de prueba con al menos 10 episodios.
    import copy

    for r, n in enumerate((8, 11, 14, 17)):
        base = red_radial(rnd, n)
        for k in range(12):
            g = copy.deepcopy(base)
            factor = rnd.uniform(0.7, 1.3)
            for nodo in g['nodos'].values():
                nodo['p_mw'] = (nodo.get('p_mw') or 0.0) * factor
                nodo['q_mvar'] = (nodo.get('q_mvar') or 0.0) * factor
            bufer.guardar(_episodio(g, r * 12 + k))
    r = orc.entrenar(bufer, cfg=CFG, puertas=orc.Puertas(mae_v_max=0.02, residuo_max=0.5))
    return bufer, r


def test_el_barrido_cumple_la_fisica():
    """024:RF-15 / 024:RF-38 — el modelo físico de respaldo da un estado con residuo nulo y
    el mismo contrato que la PINN."""
    g = red_radial(random.Random(1), 12)
    p = orc.ModeloRadial().predecir(g)
    assert p['v'][0] == pytest.approx(1.0) and p['v'].min() < 1.0
    assert float(np.max(p['residuo'])) < 1e-6
    assert set(p) >= {'ids', 'v', 'theta', 'incertidumbre', 'residuo', 'fuera_de_dominio', 'modelo'}


def test_estado_electrico_con_perdidas_y_cargabilidad():
    """024:RF-18 — de la predicción, tensiones, pérdidas y cargabilidad por rama."""
    g = red_radial(random.Random(2), 10)
    e = orc.estado_electrico(orc.ModeloRadial().predecir(g), g)
    assert e['perdidas_mw'] > 0 and e['cargabilidad_pct'] and not e['requiere_pf']
    assert set(e['tensiones']) == set(g['nodos'])


def test_entrena_registra_y_promueve(entrenado):
    """024:RF-12 / 024:RF-13 / 024:RF-16 / 024:RF-42 — entrena con una consulta fija, separa
    por familias, registra episodios y métricas y promueve si pasa las puertas."""
    bufer, r = entrenado
    assert r['entrenado'] and r['promovido'], r
    assert sum(r['particiones'].values()) == 48 and r['mae_v'] < 0.02
    assert r['particiones']['prueba'] >= orc.MIN_EPISODIOS_PRUEBA
    meta = (bufer.raiz / 'modelos' / r['version'] / 'modelo.json').read_text(encoding='utf-8')
    assert '"episodios"' in meta and '"consulta"' in meta
    assert orc.cargar(bufer).version == r['version']


def test_prediccion_con_incertidumbre_y_residuo(entrenado):
    """024:RF-15 / 024:RF-44 — cada predicción con su incertidumbre y su residuo físico, en
    redes de tamaño distinto con los mismos pesos."""
    bufer, _ = entrenado
    o = orc.cargar(bufer)
    rnd = random.Random(99)
    for n in (9, 17):
        g = red_radial(rnd, n)
        p = o.predecir(g)
        real = np.array(list(_tensiones(g).values()))
        assert len(p['v']) == n and np.mean(np.abs(p['v'] - real)) < 0.03
        assert float(np.mean(p['incertidumbre'])) > 0 and len(p['residuo']) == n


def test_fuera_de_dominio_pide_digsilent(entrenado):
    """024:RF-19 — una red con demanda muy fuera de lo aprendido no se extrapola: se pide el
    cálculo nativo."""
    bufer, _ = entrenado
    g = red_radial(random.Random(3), 12, carga=40.0)
    p = orc.cargar(bufer).predecir(g)
    assert p['fuera_de_dominio'] and p['motivos']
    assert orc.estado_electrico(p, g)['requiere_pf']


def test_puertas_que_no_se_pasan_no_promueven(entrenado):
    """024:RF-16 / 024:RF-17 — un candidato que no pasa el umbral se registra pero no
    reemplaza al promovido; parte de sus pesos (ajuste fino con repetición del histórico)."""
    bufer, r = entrenado
    llamadas = []
    original = orc.entrenar_miembro

    def espia(muestras, cfg, inicial=None, log=None, **_kw):
        llamadas.append(inicial is not None)
        return original(muestras, orc.Entrenamiento(epocas=1, ocultas=32, pasos=6), inicial)

    orc.entrenar_miembro = espia
    try:
        r2 = orc.entrenar(bufer, cfg=CFG, puertas=orc.Puertas(mae_v_max=1e-9))
    finally:
        orc.entrenar_miembro = original
    assert all(llamadas) and not r2['promovido'] and r2['fallos']
    assert orc.cargar(bufer).version == r['version']


def test_volver_al_modelo_anterior(tmp_path, entrenado):
    """024:RF-42 — cada promoción guarda el anterior y se puede volver a él."""
    bufer, r = entrenado
    orc.promover(bufer, r['version'], 'prueba')
    assert orc.volver_al_anterior(bufer) == r['version']
    assert (bufer.raiz / 'modelos' / 'historial.jsonl').read_text(encoding='utf-8').count('\n') >= 2


def test_reentrena_solo_si_toca(entrenado, monkeypatch):
    """024:RF-39 / 024:RF-43 — sin episodios nuevos no entrena; con pocos espera, salvo que
    muestren deriva, y entonces se adapta partiendo del modelo en uso."""
    bufer, _ = entrenado
    assert orc.entrenar_si_toca(bufer)['motivo'] == 'sin episodios nuevos'
    bufer.guardar(_episodio(red_radial(random.Random(5), 10), 900))
    monkeypatch.setattr(orc, 'deriva', lambda *a, **k: False)
    assert 'se espera' in orc.entrenar_si_toca(bufer, minimo=50)['motivo']
    monkeypatch.setattr(orc, 'deriva', lambda *a, **k: True)
    monkeypatch.setattr(orc, 'entrenar', lambda b, **k: {'entrenado': True, 'por': 'deriva'})
    assert orc.entrenar_si_toca(bufer, minimo=50) == {'entrenado': True, 'por': 'deriva'}


def test_deriva_cuando_el_modelo_ya_no_reproduce(entrenado):
    """024:RF-43 — si el modelo en uso falla en lo nuevo más del doble del umbral, hay deriva."""
    bufer, _ = entrenado
    d = episodio_a_dict(_episodio(red_radial(random.Random(7), 10), 950))
    d.pop('episode_id')
    d['flujo']['tensiones']['valores'] = {k: 0.5 for k in d['flujo']['tensiones']['valores']}
    e = leer_episodio(d)
    bufer.guardar(e)
    assert orc.deriva(bufer, [e.episode_id], orc.Puertas(mae_v_max=0.01))


def test_evaluar_si_aprendio(entrenado):
    """024:RF-74 — la evaluación dice, por episodio y por partición, cuánto se apartan de
    DIgSILENT el modelo promovido y la física sola."""
    bufer, r = entrenado
    e = orc.evaluar(bufer)
    assert e['modelo'] == orc.cargar(bufer).version and len(e['episodios']) >= 24
    assert set(e['por_particion']) <= {'entrenamiento', 'validacion', 'prueba'}
    assert all(d['episodios'] > 0 and 'mae_modelo' in d for d in e['por_particion'].values())
    # Otras pruebas del módulo guardan a propósito episodios con tensiones falsas (deriva):
    # la evaluación tiene que dejarlos a la vista, no esconderlos en la media.
    reales = [f for f in e['episodios'] if f['mae_fisica'] < 1e-6]
    assert len(reales) >= 24 and all(f['mae_modelo'] < 0.03 for f in reales)
    falsos = [f for f in e['episodios'] if f['mae_fisica'] >= 1e-6]
    assert all(f['mae_fisica'] > 0.1 for f in falsos)


def test_violaciones_no_son_objetivo(tmp_path):
    """024:RF-14 — las violaciones y rechazos no entran como objetivo de tensión."""
    bufer = BuferEpisodios(tmp_path / 't')
    rnd = random.Random(8)
    bufer.guardar(_episodio(red_radial(rnd, 8), 1, clase='converged_with_violations'))
    assert orc.entrenar(bufer, cfg=CFG)['motivo'] == 'no hay episodios con grafo y tensiones'


def test_incertidumbre_para_el_aprendizaje_activo(entrenado):
    """024:RF-40 — con modelo, el aprendizaje activo tiene su función de incertidumbre."""
    bufer, _ = entrenado
    g = red_radial(random.Random(4), 12)
    f = orc.incertidumbre_de_escenarios(g, bufer)
    assert f(Escenario(1.0)) >= 0 and f(Escenario(30.0)) > f(Escenario(1.0))


def test_ordenar_obras_candidatas_con_el_oraculo():
    """024:RF-23 / 024:RF-35 / 024:RF-36 — el oráculo ordena las obras candidatas antes de
    confirmarlas en DIgSILENT: el banco en el nodo más bajo gana al banco junto a la fuente."""
    g = red_radial(random.Random(6), 14, carga=2.0)
    v = _tensiones(g)
    peor = min(v, key=v.get)
    orden = orc.ordenar_candidatos(orc.ModeloRadial(), g, [
        {'codigo': 'cerca', 'nodo': 'N1', 'q_mvar': 0.3},
        {'codigo': 'lejos', 'nodo': peor, 'q_mvar': 0.3}], tension_min_pu=0.99)
    assert orden[0]['codigo'] == 'lejos' and all(c['confirmar_en_pf'] for c in orden)


def test_solo_en_la_gpu(monkeypatch):
    """024:RF-44 — el gemelo entrena y predice en la GPU; sin CUDA lo dice, nunca usa la CPU."""
    assert orc.dispositivo().type == 'cuda'
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: False)
    with pytest.raises(orc.SinGPU, match='GPU CUDA'):
        orc.dispositivo()



def test_parada_temprana_con_la_mejor_epoca():
    """027:RF-5 / 027:RF-6 — con validación, el miembro para tras la paciencia y devuelve los
    pesos de su mejor época; coseno y recorte vienen de la configuración."""
    rnd = random.Random(5)
    datos = []
    for _ in range(6):
        g = red_radial(rnd, 9)
        datos.append(orc.muestra(g, _tensiones(g)))
    cfg = orc.Entrenamiento(epocas=3000, lr=5e-3, ocultas=16, pasos=4, paciencia=10, cada=1, recorte=0.5)
    historial: list = []
    estado = orc.entrenar_miembro(datos[:4], cfg, validacion=datos[4:], historial=historial)
    assert historial and historial[-1][0] < cfg.epocas - 1
    _mejor_epoca, mejor = min(historial, key=lambda x: x[1])
    disp = orc.dispositivo()
    red = orc._red(cfg.ocultas, cfg.pasos).to(disp)
    red.load_state_dict(estado)
    red.eval()
    with torch.no_grad():
        err = np.mean([float((red(*orc._tensores(m, disp, cfg.exponente_carga, cfg.fisica))[0]
                              - torch.tensor(m.v, dtype=torch.float32, device=disp))[torch.tensor(m.mascara, device=disp)]
                             .abs().mean()) for m in datos[4:]])
    assert err == pytest.approx(mejor, rel=1e-4)


def test_el_registro_guarda_la_curva_de_validacion(entrenado):
    """027:RF-5 — el candidato guarda la mejor época y la curva de cada miembro."""
    import json
    from pathlib import Path

    _bufer, r = entrenado
    meta = json.loads((Path(r['carpeta']) / 'modelo.json').read_text(encoding='utf-8'))
    assert len(meta['validacion']) == orc.MIEMBROS
    assert all(v['mejor_epoca'] is not None and v['curva'] for v in meta['validacion'])
