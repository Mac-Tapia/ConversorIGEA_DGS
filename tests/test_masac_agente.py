"""Spec 114: el entorno multiagente de obras, MASAC con CTDE, el registro de experiencia y el modo sombra."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import numpy as np
import pytest

from convertersmartgrid.adaptadores.digital_twin.oraculo import ModeloRadial
from convertersmartgrid.adaptadores.madrl_obras import ParametrosObras
from convertersmartgrid.adaptadores.madrl_puerta import huella_grafo
from convertersmartgrid.adaptadores.masac_entorno import (
    NADA,
    EntornoAgente,
    MotorAbierto,
    ParametrosAgente,
    acciones_por_nivel,
    jerarquia,
    jugar,
    red_sintetica,
    tomas_de,
)

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = ParametrosObras(0.95, 1.05, 100.0, 0.3, 10.0, costo_terna_km=20.0, candidatos=3, max_bancos=2, max_pasos=5)


def _p(**cambios) -> ParametrosAgente:
    base = {'obras': OBRAS, 'costo_maniobra': 1.0, 'costo_perdidas_mw': 5.0, 'factor_valle': 0.4, 'paso_consigna_pu': 0.01}
    return ParametrosAgente(**{**base, **cambios})


def _cuentas(grafo):
    """Sistemas, SET y alimentadores que sorteó ``red_sintetica``, leídos de los nombres de sus barras."""
    sistemas = {n for n, d in grafo['nodos'].items() if d.get('fuente')}
    sets = {n[:-1] for n in grafo['nodos'] if re.fullmatch(r'S\d+T\d+A', n)}
    alimentadores = {m.group(1) for n in grafo['nodos'] if (m := re.fullmatch(r'(S\d+T\d+F\d+)N\d+', n))}
    return sistemas, sets, alimentadores


def _radial(grafo) -> bool:
    """Cada componente de la red cerrada es un árbol: ramas cerradas = barras − componentes."""
    nodos = list(grafo['nodos'])
    padre = {n: n for n in nodos}

    def raiz(n):
        while padre[n] != n:
            n = padre[n]
        return n

    cerradas = [r for r in grafo['ramas'] if r.get('cerrada', True)]
    for r in cerradas:
        a, b = raiz(r['desde']), raiz(r['hasta'])
        if a == b:
            return False
        padre[a] = b
    return True


@pytest.mark.parametrize('semilla', range(6))
def test_un_agente_por_alimentador_por_set_y_por_sistema_sin_tamanos_fijos(semilla):
    """114:RF-13, 114:RF-1 — tantos agentes como tenga la red sorteada, en tres niveles enlazados."""
    g = red_sintetica(semilla)
    sistemas, sets, alimentadores = _cuentas(g)
    agentes = jerarquia(g)
    por_nivel = {n: [a for a in agentes.values() if a.nivel == n] for n in ('alimentador', 'set', 'sistema')}
    assert len(por_nivel['alimentador']) == len(alimentadores)
    assert len(por_nivel['set']) == len(sets)
    assert len(por_nivel['sistema']) == len(sistemas)
    vistos: set[str] = set()
    for a in por_nivel['alimentador']:
        assert not (a.nodos & vistos), 'dos alimentadores comparten barras'
        vistos |= a.nodos
        superior = agentes[a.superior]
        assert superior.nivel == 'set' and a.codigo in superior.alimentadores and a.nodos <= superior.nodos
        assert agentes[superior.superior].nivel == 'sistema' and superior.nodos <= agentes[superior.superior].nodos
    assert vistos == {n for n in g['nodos'] if re.fullmatch(r'S\d+T\d+F\d+N\d+', n)}


def test_la_estructura_de_la_fuente_manda_y_sin_ella_se_deduce():
    """114:RF-13, 114:RF-16 — con la estructura de la fuente (055) sus nombres; sin ella, la SET por sus barras."""
    g = red_sintetica(11, sistemas=1, sets=2, alimentadores=2)
    deducida = jerarquia(g)
    assert {a.codigo for a in deducida.values() if a.nivel == 'set'} == {'S0T0A', 'S0T1A'}
    # Sin la estructura, la SET de un alimentador es la de su cabecera: las barras de 60 y 10 kV de su transformador.
    assert deducida['set:S0T0A'].nodos >= {'S0T0A', 'S0T0B'}
    assert deducida['alimentador:S0T1F0'].superior == 'set:S0T1A'
    estructura = {'S0T0F0': {'set': 'SET Norte', 'sistema': 'SE01'}, 'S0T0F1': {'set': 'SET Norte', 'sistema': 'SE01'},
                  'S0T1F0': {'set': 'SET Sur', 'sistema': 'SE01'}, 'S0T1F1': {'set': 'SET Sur', 'sistema': 'SE01'}}
    con = jerarquia(g, estructura)
    assert {a for a in con if not a.startswith('alimentador:')} == {'set:SET Norte', 'set:SET Sur', 'sistema:SE01'}
    assert con['set:SET Norte'].alimentadores == ('S0T0F0', 'S0T0F1')
    # Un alimentador que cuelga de la fuente, sin cabecera ni SET: un agente de cada nivel, no ninguno.
    sola = {'nodos': {'F': {'kv': 10.0, 'fuente': True, 'v_pu': 1.0}, 'B': {'kv': 10.0, 'p_mw': 0.1}},
            'ramas': [{'id': 'L', 'clase': 'ElmLne', 'desde': 'F', 'hasta': 'B', 'r_ohm': 0.1, 'x_ohm': 0.1, 'inom_ka': 0.2}]}
    assert sorted(a.nivel for a in jerarquia(sola).values()) == ['alimentador', 'set', 'sistema']


def test_observacion_parcial_y_espacios_del_mismo_tamano_en_cualquier_red():
    """114:RF-1, 114:RF-13, 114:RF-15 — cada agente ve su parte; el tamaño de su nivel no depende de la red."""
    tam = None
    for semilla in range(4):
        e = EntornoAgente(red_sintetica(semilla, carga_mw=0.5), _p())
        obs, info = e.reset(seed=semilla)
        assert set(obs) == set(e.agents) == set(e.possible_agents) == set(info)
        for a, o in obs.items():
            assert e.observation_space(a) is e.observation_space(a)
            assert e.observation_space(a).contains(o)
            assert len(o['action_mask']) == acciones_por_nivel(e.p)[e.estructura[a].nivel]
        dims = e.dimensiones()
        assert tam in (None, dims) and len(e.state()) == e.tam_estado
        tam = dims
    # Parcial: cargar otro sistema no cambia lo que ve un alimentador de este.
    g = red_sintetica(5, sistemas=2, sets=1, alimentadores=1, carga_mw=0.3)
    mas = copy.deepcopy(g)
    for n, d in mas['nodos'].items():
        if n.startswith('S1T0F0N') and d.get('p_mw'):
            d['p_mw'] *= 1.5
    a = EntornoAgente(g, _p()).reset()[0]
    b = EntornoAgente(mas, _p()).reset()[0]
    np.testing.assert_allclose(a['alimentador:S0T0F0']['observation'], b['alimentador:S0T0F0']['observation'])
    assert not np.allclose(a['alimentador:S1T0F0']['observation'], b['alimentador:S1T0F0']['observation'])


def test_la_api_paralela_funciona_sin_pettingzoo():
    """114:RF-15 — episodio entero con ``reset``/``step`` de ``ParallelEnv`` y la máscara en la observación."""
    e = EntornoAgente(red_sintetica(2, carga_mw=0.6), _p())
    obs, _ = e.reset(seed=4)
    for _ in range(50):
        if not e.agents:
            break
        acciones = {a: e.action_space(a).sample(mask=obs[a]['action_mask']) for a in e.agents}
        vivos = list(e.agents)
        obs, rec, term, trunc, info = e.step(acciones)
        assert set(rec) == set(term) == set(trunc) == set(info) == set(vivos)
        assert len(set(rec.values())) == 1, 'la recompensa es común'
    assert e.agents == []
    assert any(term.values()) or any(trunc.values())


def test_una_accion_fuera_de_su_mascara_no_hace_nada_y_se_dice():
    """114:RF-20 — se toma como «no hacer nada» y la información del paso lo dice."""
    e = EntornoAgente(red_sintetica(2, carga_mw=0.6), _p())
    obs, _ = e.reset()
    agente = next(a for a in e.agents if not obs[a]['action_mask'].all())
    prohibida = int(np.flatnonzero(obs[agente]['action_mask'] == 0)[0])
    antes = huella_grafo(e.grafo)
    _obs, _r, _t, _tr, info = e.step({agente: prohibida})
    assert info[agente].get('accion_invalida') == prohibida
    assert huella_grafo(e.grafo) == antes


def test_recompensa_con_norma_en_maxima_y_valle_costo_perdidas_y_lo_deshecho():
    """114:RF-10 — obras, maniobras, tiempo, norma en máxima y valle, pérdidas, DIgSILENT y castigo por lo deshecho."""
    g = red_sintetica(7, sistemas=1, sets=1, alimentadores=1, barras=7, carga_mw=0.5)
    e = EntornoAgente(g, _p(costo_paso=0.1))
    obs, _ = e.reset()
    assert not e.estado.en_norma
    al = 'alimentador:S0T0F0'
    banco = next(i for i, x in enumerate(e.huecos[al]) if x is not None and x.tipo == 'banco' and obs[al]['action_mask'][i])
    _o, rec, term, trunc, info = e.step({al: banco})
    c = info[al]['recompensa']
    assert c['obras'] == pytest.approx(-OBRAS.costo_banco / e.escala)
    assert c['tiempo'] == -0.1 and c['digsilent'] == 0.0 and c['deshechas'] == 0.0
    assert rec[al] == pytest.approx(sum(c.values()))
    # Terminar fuera de norma cobra la penalidad, al menos todo el presupuesto, y las pérdidas que bajaron suman.
    _o, rec, term, trunc, info = e.step({})
    c = info[al]['recompensa']
    assert term[al] and c['norma'] <= -e.presupuesto
    assert c['perdidas'] == pytest.approx((e.inicial.perdidas_mw - e.estado.perdidas_mw) * 5.0 / e.escala)
    # En valle cuentan los bancos del agente: muchos bancos dejan la red en sobretensión con poca demanda.
    valle = EntornoAgente(g, _p(factor_valle=0.05, obras=ParametrosObras(0.95, 1.05, 100.0, 3.0, 10.0, candidatos=3,
                                                                          max_bancos=3, max_pasos=5)))
    o, _ = valle.reset()
    for _ in range(3):
        if not valle.agents:
            break
        o, *_ = valle.step({al: 1})                                     # la escalera: un banco más por paso
    assert valle.estado.valle is not None and valle.estado.valle.sobretension > 0
    # Repetir lo que el operador deshizo cuesta un presupuesto.
    accion = e.huecos[al][banco]
    castigado = EntornoAgente(g, _p(), deshechas=[(al, accion.tipo, accion.elemento)])
    castigado.reset()
    _o, _r, _t, _tr, info = castigado.step({al: banco})
    assert info[al]['recompensa']['deshechas'] == pytest.approx(-castigado.presupuesto)


def test_los_pasos_los_resuelve_el_motor_abierto_o_el_oraculo_nunca_digsilent():
    """114:RF-4 — el motor abierto y el barrido del oráculo coinciden en una red radial; una PINN entra igual."""
    g = red_sintetica(4, carga_mw=0.4)
    abierto = EntornoAgente(g, _p(), evaluador=MotorAbierto())
    radial = EntornoAgente(g, _p(), evaluador=ModeloRadial())
    abierto.reset()
    radial.reset()
    assert abierto.estado.motor in ('zbus', 'newton')
    assert abs(abierto.estado.maxima.vm_min - radial.estado.maxima.vm_min) < 2e-3
    assert abierto.estado.perdidas_mw == pytest.approx(radial.estado.perdidas_mw, rel=0.05)

    class PINN:
        """Lo que da ``OraculoPINN.predecir``: tensiones y ángulos; las pérdidas, el entorno las estima."""

        llamadas = 0

        def predecir(self, grafo):
            PINN.llamadas += 1
            r = ModeloRadial().predecir(grafo)
            return {'v': r['v'], 'theta': r['theta'], 'modelo': 'pinn_gnn'}

    pinn = EntornoAgente(g, _p(), evaluador=PINN())
    pinn.reset()
    assert PINN.llamadas >= 2 and pinn.estado.motor == 'pinn_gnn'
    assert pinn.estado.perdidas_mw == pytest.approx(radial.estado.perdidas_mw)
    fuente = (RAIZ / 'src/convertersmartgrid/adaptadores/masac_entorno.py').read_text(encoding='utf-8')
    assert not re.search(r'^\s*(import|from)\s+\S*(powerfactory|pf_arnes)', fuente, re.M)


def test_transferencia_solo_en_maniobras_y_la_red_sigue_radial():
    """114:RF-17 — cerrar la maniobra abierta y abrir otra del que cede; sin esa otra, no se ofrece."""
    g = red_sintetica(9, sistemas=1, sets=1, alimentadores=2, barras=6, carga_mw=0.6)
    e = EntornoAgente(g, _p())
    obs, _ = e.reset()
    s = 'set:S0T0A'
    tr = [i for i, x in enumerate(e.huecos[s]) if x is not None and x.tipo == 'transferencia']
    assert tr and all(obs[s]['action_mask'][i] for i in tr)
    for i in tr:
        cerrar, abrir = e.huecos[s][i].elemento.split('|')
        assert e._rama[cerrar]['clase'] == 'ElmCoup' and not e._rama[cerrar]['cerrada']
        assert e._rama[abrir]['clase'] == 'ElmCoup' and e._rama[abrir]['cerrada'] and abrir.endswith('SEC')
    e.step({s: tr[0]})
    assert _radial(e.grafo)
    assert all(v > 0 for n, v in e.estado.tension.items() if n.startswith('S0T0F'))
    # Sin seccionador en el alimentador que cede, cerrar haría un lazo: no se ofrece.
    sin = copy.deepcopy(g)
    for r in sin['ramas']:
        if r['id'].endswith('SEC'):
            r['clase'] = 'ElmLne'
    e2 = EntornoAgente(sin, _p())
    e2.reset()
    assert not any(x is not None and x.tipo == 'transferencia' for x in e2.huecos[s])


def test_toma_y_consigna_solo_con_su_paso_declarado():
    """114:RF-18 — sin paso o sin límites no se ofrecen; con ellos, mueven la tensión."""
    g = red_sintetica(7, sistemas=1, sets=1, alimentadores=1, barras=7, carga_mw=0.5)
    sin_limites = copy.deepcopy(g)
    for r in sin_limites['ramas']:
        if 'toma' in r:
            del r['toma']['minimo']
    assert tomas_de(sin_limites, set(sin_limites['nodos']), set()) == []
    assert tomas_de(g, set(g['nodos']), set()) == ['S0T0TR']
    sin_paso = EntornoAgente(g, _p(paso_consigna_pu=None))
    sin_paso.reset()
    assert all(x is None for x in sin_paso.huecos['sistema:S0'][1:])
    e = EntornoAgente(g, _p())
    obs, _ = e.reset()
    sube = next(i for i, x in enumerate(e.huecos['sistema:S0']) if x is not None and x.tipo == 'consigna+')
    antes = e.estado.maxima.vm_min
    e.step({'sistema:S0': sube})
    assert e.grafo['nodos']['S0']['v_pu'] == pytest.approx(1.01) and e.estado.maxima.vm_min > antes
    e.reset()
    toma = next(i for i, x in enumerate(e.huecos['set:S0T0A']) if x is not None and x.tipo.startswith('toma'))
    e.step({'set:S0T0A': toma})
    assert e._rama['S0T0TR']['toma']['posicion'] != 0 and g['ramas'][1]['toma']['posicion'] == 0


def test_lo_que_cambio_el_operador_no_se_ofrece():
    """114:RF-9 (aclaración) — una barra o una maniobra suya, o en la lista de protegidos, no es acción del agente."""
    g = red_sintetica(9, sistemas=1, sets=1, alimentadores=2, barras=6, carga_mw=0.6)
    e = EntornoAgente(g, _p())
    e.reset()
    banco = next(x.elemento for x in e.huecos['alimentador:S0T0F0'] if x is not None and x.tipo == 'banco')
    suyo = copy.deepcopy(g)
    suyo['nodos'][banco]['operador'] = True
    e2 = EntornoAgente(suyo, _p(), protegidos=['S0T0TR', 'S0T0F1ENL'])
    e2.reset()
    elementos = {x.elemento for h in e2.huecos.values() for x in h if x is not None}
    assert banco not in elementos and 'S0T0TR' not in elementos
    assert not any(x.startswith('S0T0F1ENL|') for x in elementos)


def test_el_mismo_episodio_da_lo_mismo():
    """114:RF-1 — determinismo con semilla: mismas acciones, mismo resultado y misma recompensa."""
    g = red_sintetica(3, carga_mw=0.6)

    def episodio():
        e = EntornoAgente(g, _p())
        rng = np.random.default_rng(5)
        ep = jugar(e, lambda _a, _o, m: int(rng.choice(np.flatnonzero(m))), semilla=5)
        return ep.resultado, [p['recompensa'] for p in ep.pasos]

    assert episodio() == episodio()


# ------------------------------------------------------------------ MASAC (T3)
torch = pytest.importorskip('torch')

from convertersmartgrid.adaptadores.masac_politica import (  # noqa: E402
    IMPLEMENTACION,
    MASAC,
    ConfigMASAC,
    cargar_masac,
    entrenar_masac,
    evaluar_azar,
    evaluar_masac,
    guardar_masac,
)


def _juguete():
    g = red_sintetica(7, sistemas=1, sets=1, alimentadores=1, barras=7, carga_mw=0.4)
    obras = ParametrosObras(0.95, 1.05, 100.0, 0.3, 10.0, candidatos=3, max_bancos=3, max_pasos=4)
    return g, _p(obras=obras)


def test_masac_aprende_el_juguete_mejor_que_el_azar_y_se_guarda_en_cpu(tmp_path, monkeypatch):
    """114:RF-2, 114:RF-3, 114:RF-14 — MASAC con CTDE supera al azar con semilla fija y se carga sin GPU."""
    g, p = _juguete()
    e = EntornoAgente(g, p)
    agente, curva = entrenar_masac(e, ConfigMASAC(episodios=40, semilla=1))
    assert len(curva) == 40
    aprendido, azar = evaluar_masac(e, agente), evaluar_azar(e, 30, 1)
    assert aprendido['retorno'] > azar['retorno'] and aprendido['en_norma']
    # CTDE: el actor solo ve la observación del agente; el crítico, además, el estado global.
    obs_alim, acciones_alim = e.dimensiones()['alimentador']
    nivel = agente.niveles['alimentador']
    assert nivel.actor[0].in_features == obs_alim and nivel.actor[-1].out_features == acciones_alim
    assert nivel.q1[0].in_features == e.tam_estado + obs_alim
    obs, _ = e.reset()
    o, m = obs['alimentador:S0T0F0']['observation'], obs['alimentador:S0T0F0']['action_mask']
    uno, otro = agente.explicar('alimentador', o, m, e.state()), agente.explicar('alimentador', o, m, e.state() + 1.0)
    assert [f['probabilidad'] for f in uno] == [f['probabilidad'] for f in otro]
    assert [f['valor'] for f in uno] != [f['valor'] for f in otro]
    manifiesto = guardar_masac(tmp_path / 'modelo', agente)
    assert manifiesto['implementacion'] == IMPLEMENTACION and 'BenchMARL' in IMPLEMENTACION
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: False)
    cargado = cargar_masac(tmp_path / 'modelo')
    assert all(w.device.type == 'cpu' for r in cargado.niveles.values() for w in r.parameters())
    assert evaluar_masac(e, cargado)['obras'] == aprendido['obras']


def test_la_entropia_no_cuenta_lo_que_la_mascara_prohibe():
    """114:RF-3 — SAC discreto: una sola acción permitida da probabilidad 1 y la actualización queda finita."""
    g, p = _juguete()
    e = EntornoAgente(g, p)
    agente = MASAC.para(e, ConfigMASAC(semilla=2))
    obs, _ = e.reset()
    a = 'alimentador:S0T0F0'
    sola = np.zeros_like(obs[a]['action_mask'])
    sola[NADA] = 1
    filas = agente.explicar('alimentador', obs[a]['observation'], sola, e.state())
    assert [f['accion'] for f in filas] == [NADA] and filas[0]['probabilidad'] == pytest.approx(1.0)
    t = {'obs': obs[a]['observation'], 'mascara': sola.astype(bool), 'accion': NADA, 'recompensa': -1.0,
         'obs2': obs[a]['observation'], 'mascara2': sola.astype(bool), 'estado': e.state(), 'estado2': e.state(), 'fin': True}
    perdidas = agente.actualizar('alimentador', [t, t])
    assert all(np.isfinite(v) for v in perdidas.values())
    # La temperatura se ajusta sola: con varias acciones permitidas se mueve desde su valor inicial.
    todas = {**t, 'mascara': np.ones_like(sola, dtype=bool), 'mascara2': np.ones_like(sola, dtype=bool), 'fin': False}
    antes = float(agente.niveles['alimentador'].log_alfa.detach())
    agente.actualizar('alimentador', [todas, todas])
    assert float(agente.niveles['alimentador'].log_alfa.detach()) != antes


# ------------------------------------------------------------------ registro y modo sombra (T4)
from convertersmartgrid.adaptadores.masac_sombra import (  # noqa: E402
    RegistroExperiencia,
    SombraError,
    exigir_destino,
    modo_del_modulo,
    proponer_en_sombra,
    quien_acierta,
)


def test_el_registro_guarda_cada_decision_y_quien_la_confirmo(tmp_path):
    """114:RF-11 — observación, acción, recompensa y quién confirmó; solo se añade, nunca se reescribe."""
    reg = RegistroExperiencia(tmp_path)
    a = reg.registrar(modulo='obras', agente='alimentador:X', observacion={'observation': np.ones(2, np.float32)},
                      accion={'tipo': 'banco', 'elemento': 'B1'}, recompensa=-1.0, explicacion='Propone un banco.')
    b = reg.registrar(modulo='obras', agente='set:Y', observacion=[0.5], accion={'tipo': 'toma+', 'elemento': 'T'},
                      recompensa=-0.1, explicacion='Propone subir la toma.')
    primeras = reg.ruta.read_text(encoding='utf-8')
    reg.confirmar(a, 'digsilent')
    reg.deshacer(b)
    assert reg.ruta.read_text(encoding='utf-8').startswith(primeras)
    por_id = {d['id']: d for d in reg.decisiones()}
    assert por_id[a]['estado'] == 'confirmada' and por_id[a]['confirmo'] == 'digsilent'
    assert por_id[a]['observacion'] == {'observation': [1.0, 1.0]} and por_id[a]['recompensa'] == -1.0
    assert por_id[b]['estado'] == 'deshecha' and por_id[b]['confirmo'] == 'operador'
    assert reg.deshechas() == {('set:Y', 'toma+', 'T')}
    with pytest.raises(SombraError):
        reg.confirmar(a, 'agente')
    with pytest.raises(SombraError):
        reg.confirmar('no-existe', 'operador')


def test_en_sombra_propone_junto_a_la_regla_sin_aplicar_y_explica(tmp_path):
    """114:RF-7, 114:RF-9, 114:RF-11 — propone sin tocar la red del operador, explica y mide quién acierta."""
    g, p = _juguete()
    huella = huella_grafo(g)
    politica = MASAC.para(EntornoAgente(g, p), ConfigMASAC(semilla=3))
    reg = RegistroExperiencia(tmp_path)
    r = proponer_en_sombra(g, p, politica, registro=reg)
    assert r['modo'] == 'sombra' and r['aplicada'] is False and huella_grafo(g) == huella
    assert r['regla']['control'] == 'escalera' and r['acierta'] in ('agente', 'regla', 'empate')
    assert r['decisiones'], 'la política sin entrenar propone algo en una red fuera de norma'
    for d in r['decisiones']:
        assert d['explicacion'].startswith('Propone ') and 'valor del crítico' in d['explicacion']
        assert not re.search(r'RF-\d', d['explicacion'])
        assert d['alternativas'] and d['confirmo'] is None
    registradas = reg.decisiones()
    assert {d['id'] for d in registradas} == {d['id'] for d in r['decisiones']}
    assert all(d['modo'] == 'sombra' and d['aplicada'] is False and d['observacion']['action_mask'] for d in registradas)
    assert sum(reg.aciertos().values()) == 1
    # Con las puertas pasadas el módulo podría actuar (T5), pero esta propuesta tampoco aplica nada.
    assert modo_del_modulo('obras', {'obras': True}) == 'actua' and modo_del_modulo('obras', {}) == 'sombra'
    assert proponer_en_sombra(g, p, politica, puertas={'obras': True})['aplicada'] is False
    # Una política de otros huecos de acción no se usa en silencio.
    otra = MASAC.para(EntornoAgente(g, _p(obras=OBRAS)), ConfigMASAC(semilla=3))
    with pytest.raises(SombraError, match='huecos de acción'):
        proponer_en_sombra(g, _p(obras=ParametrosObras(0.95, 1.05, 100.0, 0.3, 10.0, candidatos=4)), otra)


def test_el_agente_solo_escribe_en_variaciones_pruebas_o_con_confirmacion():
    """114:RF-9 — un proyecto real del operador, sin su confirmación, se rechaza."""
    with pytest.raises(SombraError, match='variación'):
        exigir_destino('LL202_2026')
    assert exigir_destino('PRUEBA114_LL202') == 'PRUEBA114_LL202'
    assert exigir_destino('LL202_2026', variacion=True) == 'LL202_2026'
    assert exigir_destino('LL202_2026', confirmado_por_operador=True) == 'LL202_2026'


def test_acierta_la_que_cumple_luego_la_mas_barata_y_luego_la_de_menos_perdidas():
    """114:RF-19 — el orden del acierto en modo sombra."""
    cumple = {'en_norma': True, 'costo': 30.0, 'costo_maniobras': 0.0, 'perdidas_mw': 0.2}
    assert quien_acierta(cumple, {**cumple, 'en_norma': False, 'costo': 0.0}) == 'agente'
    assert quien_acierta(cumple, {**cumple, 'costo': 20.0, 'costo_maniobras': 2.0}) == 'regla'
    assert quien_acierta(cumple, {**cumple, 'perdidas_mw': 0.1}) == 'regla'
    assert quien_acierta(cumple, dict(cumple)) == 'empate'


def test_lo_deshecho_en_el_registro_vuelve_como_castigo(tmp_path):
    """114:RF-10, 114:RF-11 — una propuesta que el operador deshizo cuesta caro la próxima vez."""
    g, p = _juguete()
    politica = MASAC.para(EntornoAgente(g, p), ConfigMASAC(semilla=3))
    reg = RegistroExperiencia(tmp_path)
    primera = proponer_en_sombra(g, p, politica, registro=reg)
    d = primera['decisiones'][0]
    reg.deshacer(d['id'])
    segunda = proponer_en_sombra(g, p, politica, registro=reg)
    misma = next(x for x in segunda['decisiones'] if x['agente'] == d['agente'] and x['accion'] == d['accion'])
    assert misma['recompensa'] < d['recompensa']
    json.dumps(segunda, default=float)
