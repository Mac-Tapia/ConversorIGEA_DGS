"""086:RF-124 (amplía 083:RF-30): un alimentador que no puede cuadrar no gasta los flujos ni tumba a los que cuadran.

En el proyecto, un alimentador tiene fijas que, con sus pérdidas, pasan de su medida de cabecera, y el oráculo ya dejó
su factor de escaladas casi en cero. Antes, «escaladas al mínimo» se medía contra ese factor del oráculo y no se
alcanzaba: el bucle partía el factor a la mitad hasta el último flujo y no decía la causa. Ahora se mide contra el
factor de antes del oráculo: se para con la causa (fijas, pérdidas y la SED fija que más pesa) y los demás quedan
cumplidos. La calibración sigue siendo una, por proyecto. Red sintética sorteada; ningún dato de una empresa.
"""
from __future__ import annotations

import random

from convertersmartgrid.dominio import ajuste_cabecera as ac
from convertersmartgrid.dominio.ajuste_cabecera import MedidaConjunta, Objetivo, Reparto, cuadrar_conjunto

SEMILLA = random.SystemRandom().randrange(1, 2 ** 31)
PERDIDAS = 0.06          # fracción de lo consumido que se pierde en la red sintética


def _reparto(fijas: dict[str, float], base: dict[str, float], a: float) -> Reparto:
    seds = {**{s: 'fija' for s in fijas}, **{s: 'kva' for s in base}}
    return Reparto(fijas={s: (p, 0.3 * p) for s, p in fijas.items()}, base={s: (p, 0.3 * p) for s, p in base.items()},
                   origen=seds, kva={s: 100.0 for s in seds}, a=a, b=a, solo_kw=True)


def _flujo(reps):
    kw, carga = {}, {}
    for k, r in reps.items():
        c = r.totales()[0]
        carga[k], kw[k] = c, c * (1 + PERDIDAS)
    return MedidaConjunta(True, kw=kw, kvar={k: 0.0 for k in reps}, carga_kw=carga)


def _proyecto():
    """Cuatro alimentadores: tres que cuadran y uno (A2) con un cliente fijo que, con las pérdidas, pasa de su medida."""
    rng = random.Random(SEMILLA)
    repartos, objetivos, antes = {}, {}, {}
    for n in range(1, 5):
        k = f'A{n}'
        base = {f'{k}-S{i}': rng.uniform(50, 400) for i in range(1, rng.randint(4, 9))}
        fijas = {f'{k}-F1': rng.uniform(20, 200)}
        a0 = rng.uniform(0.15, 0.6)
        if k == 'A2':
            fijas[f'{k}-SED-X'] = rng.uniform(1500, 2000)
            medida = sum(fijas.values()) * (1 + PERDIDAS) / rng.uniform(1.12, 1.25)    # 12 % a 25 % por debajo
            a_oraculo = a0 * 1e-4                                                         # el oráculo ya la bajó
        else:
            medida = (sum(fijas.values()) + rng.uniform(0.3, 0.8) * sum(base.values())) * (1 + PERDIDAS)
            a_oraculo = a0
        repartos[k] = _reparto(fijas, base, a_oraculo)
        objetivos[k] = Objetivo(medida, 0.3 * medida, k)
        antes[k] = a0
    return repartos, objetivos, antes


def test_086_rf124_el_imposible_para_pronto_con_su_causa_y_los_demas_cumplen():
    """086:RF-124 — con el factor de antes del oráculo, el imposible se reconoce en pocos flujos, se dice su causa
    (fijas, pérdidas y la SED fija que más pesa) y los otros tres quedan en tolerancia en el mismo flujo."""
    repartos, objetivos, antes = _proyecto()
    assert 'factores_iniciales' in cuadrar_conjunto.__code__.co_varnames, 'el cuadre no conoce el factor de antes del oráculo'
    res = cuadrar_conjunto(repartos, objetivos, _flujo, tolerancia=0.01, factores_iniciales=antes)
    assert not res.cuadrado, SEMILLA
    assert hasattr(res, 'imposibles') and set(res.imposibles) == {'A2'}, (SEMILLA, getattr(res, 'imposibles', None))
    assert res.flujos < ac.MAX_FLUJOS // 2, (SEMILLA, res.flujos)
    assert all(res.cumple(k) for k in ('A1', 'A3', 'A4')) and not res.cumple('A2'), SEMILLA
    causa = res.imposibles['A2']
    assert causa['dominante']['sed'] == 'A2-SED-X' and causa['perdidas_kw'] > 0 and causa['exceso_kw'] > 0, SEMILLA
    for parte in ('A2:', 'sus fijas suman', 'sus pérdidas', 'A2-SED-X', 'no puede cuadrar'):
        assert parte in causa['texto'], (parte, causa['texto'])
    assert '(s)' not in causa['texto'] and causa['texto'] in res.motivo


def test_086_rf124_aun_sin_el_factor_inicial_el_imposible_no_gasta_todos_los_flujos():
    """086:RF-124 — la falla de la corrida real: con el exceso por encima del tope de 083:RF-30, el bucle seguía partiendo
    el factor (y el paso conjunto lo volvía a subir) hasta el último flujo, sin causa. Ahora, una vez al mínimo, se queda
    quieto con su causa y se para cuando los demás cumplen."""
    repartos, objetivos, _antes = _proyecto()
    res = cuadrar_conjunto(repartos, objetivos, _flujo, tolerancia=0.01)
    assert res.flujos < ac.MAX_FLUJOS, (SEMILLA, res.flujos)
    assert set(getattr(res, 'imposibles', {})) == {'A2'}, SEMILLA
    assert all(res.cumple(k) for k in ('A1', 'A3', 'A4')), SEMILLA


def test_086_rf124_un_exceso_pequeno_sigue_corrigiendo_las_fijas():
    """086:RF-124, 083:RF-30 — si el exceso cabe en el 10 % de sus fijas, se bajan las fijas y cuadra: no es imposible."""
    rng = random.Random(SEMILLA)
    fijas = {'B-F1': rng.uniform(1500, 2500)}
    base = {f'B-S{i}': rng.uniform(50, 200) for i in range(1, 5)}
    medida = fijas['B-F1'] * (1 + PERDIDAS) * rng.uniform(0.93, 0.97)
    res = cuadrar_conjunto({'B': _reparto(fijas, base, 0.4 * 1e-4)}, {'B': Objetivo(medida, 0.3 * medida, 'B')}, _flujo,
                           tolerancia=0.01, **({'factores_iniciales': {'B': 0.4}}
                                               if 'factores_iniciales' in cuadrar_conjunto.__code__.co_varnames else {}))
    assert res.cuadrado and res.metodos.get('fijas_corregidas'), (SEMILLA, res.motivo, res.metodos)
    assert not getattr(res, 'imposibles', {})


def test_086_rf124_el_guion_pasa_el_factor_de_antes_del_oraculo_y_da_el_estado_por_alimentador():
    """086:RF-124 — el guion de DIgSILENT mide el mínimo contra el factor de antes del oráculo, guarda la causa del
    imposible en su informe y da por cuadrado al que cumple en el flujo común (la calibración sigue siendo una)."""
    from pathlib import Path

    guion = (Path(__file__).resolve().parents[1] / 'tools' / 'ajuste_cabecera_pf.py').read_text(encoding='utf-8')
    assert 'factores_iniciales = {f: r.a for f, r in repartos.items()}' in guion, 'el guion no guarda el factor de antes del oráculo'
    assert guion.index('factores_iniciales = {f: r.a') < guion.index('repartos, del_oraculo = _arranque_del_oraculo(')
    assert 'factores_iniciales=factores_iniciales)' in guion
    assert "inf['imposible'] = res.imposibles[f]" in guion and "inf['motivo'] = causa['texto']" in guion
    assert "feeder not in res.imposibles and res.cumple(feeder)" in guion, 'el que cumple sigue marcado como violación'
    assert 'if cumple and not validacion' in guion


def test_086_rf124_un_solo_alimentador_tambien_para_con_su_causa_o_corrige_sus_fijas():
    """086:RF-124 — con un solo alimentador (``cuadrar``) igual: un exceso grande para con su causa en pocos flujos y uno
    pequeño se corrige en las fijas (083:RF-30), que antes ni existía en este camino."""
    from convertersmartgrid.dominio.ajuste_cabecera import cuadrar

    def flujo_uno(r):
        c = r.totales()[0]
        return ac.Medida(True, kw=c * (1 + PERDIDAS), kvar=0.0, carga_kw=c, carga_kvar=0.0)

    assert 'factor_inicial' in cuadrar.__code__.co_varnames, 'el cuadre de un alimentador no conoce el factor inicial'
    rng = random.Random(SEMILLA)
    fijas = {'U-F1': rng.uniform(40, 120), 'U-SED-X': rng.uniform(1500, 2000)}
    base = {f'U-S{i}': rng.uniform(50, 300) for i in range(1, 6)}
    medida = sum(fijas.values()) * (1 + PERDIDAS) / rng.uniform(1.12, 1.25)
    res = cuadrar(_reparto(fijas, base, 0.3 * 1e-4), Objetivo(medida, 0.3 * medida, 'U', 'U'), flujo_uno,
                  tolerancia=0.01, factor_inicial=0.3)
    assert not res.cuadrado and res.imposible and res.flujos < ac.MAX_FLUJOS // 2, (SEMILLA, res.flujos, res.motivo)
    assert res.imposible['dominante']['sed'] == 'U-SED-X' and res.motivo == res.imposible['texto']
    pequeno = sum(fijas.values()) * (1 + PERDIDAS) * rng.uniform(0.93, 0.97)
    ok = cuadrar(_reparto(fijas, base, 0.3 * 1e-4), Objetivo(pequeno, 0.3 * pequeno, 'U', 'U'), flujo_uno,
                 tolerancia=0.01, factor_inicial=0.3)
    assert ok.cuadrado and ok.metodos.get('fijas_corregidas') and not ok.imposible, (SEMILLA, ok.motivo)


def test_086_rf124_por_set_y_por_sistema_electrico_van_por_el_mismo_cuadre_del_proyecto():
    """086:RF-124 — la calibración por SET (máxima de barra) y por sistema eléctrico calibra el proyecto entero con
    ``_ejecutar_proyecto``, el que pasa el factor de antes del oráculo y da el estado por alimentador; la de un solo
    alimentador, con ``cuadrar`` y su factor inicial."""
    from pathlib import Path

    guion = (Path(__file__).resolve().parents[1] / 'tools' / 'ajuste_cabecera_pf.py').read_text(encoding='utf-8')
    assert 'if len(planes) == 1 and not bancos and not barra:' in guion, 'la de SET o sistema ya no va por el proyecto'
    assert guion.count('_ejecutar_proyecto(app, planes, cancelado=cancelado, estado=estado') >= 2
    assert 'factor_inicial = reparto.a' in guion and 'factor_inicial=factor_inicial)' in guion
    assert "informe['imposible'] = res.imposible" in guion


def _flujo_que_encadena(originales: dict[str, float]):
    """Pérdidas sintéticas que crecen al bajar las fijas: cada corrección de 083:RF-30 deja otro exceso pequeño."""
    def perdidas(k, r):
        fijas = sum(p for p, _q in r.fijas.values())
        return 80.0 + 0.5 * (originales[k] - fijas)

    def uno(r):
        c = r.totales()[0]
        return ac.Medida(True, kw=c + perdidas('U', r), kvar=0.0, carga_kw=c, carga_kvar=0.0)

    def conjunto(reps):
        carga = {k: r.totales()[0] for k, r in reps.items()}
        return MedidaConjunta(True, kw={k: carga[k] + perdidas(k, r) for k, r in reps.items()},
                              kvar={k: 0.0 for k in reps}, carga_kw=carga)
    return uno, conjunto


def test_083_rf34_el_tope_del_10_por_ciento_es_contra_las_fijas_originales():
    """083:RF-34 (enmienda 083:RF-30) — con pérdidas que crecen al bajar las fijas, cada corrección dejaba otro exceso
    menor que el 10 % de las fijas del momento y se encadenaban hasta bajarlas un 16 %. El tope se mide contra las fijas
    originales: no bajan más del 10 % en total y el alimentador sale imposible con su causa."""
    from convertersmartgrid.dominio.ajuste_cabecera import cuadrar

    rng = random.Random(SEMILLA)
    f0 = rng.uniform(900.0, 1100.0)
    base = {f'U-S{i}': rng.uniform(5.0, 20.0) for i in range(1, 5)}
    uno, conjunto = _flujo_que_encadena({'U': f0})
    obj = Objetivo(f0, 0.3 * f0, 'U', 'U')
    res = cuadrar(_reparto({'U-F1': f0}, base, 1e-6), obj, uno, tolerancia=0.01, factor_inicial=0.3)
    final = sum(p for p, _q in res.reparto.fijas.values())
    assert final >= 0.9 * f0 - 1e-6 and not res.cuadrado and res.imposible, (SEMILLA, final / f0, res.motivo)
    rc = cuadrar_conjunto({'U': _reparto({'U-F1': f0}, base, 1e-6)}, {'U': obj}, conjunto, tolerancia=0.01,
                          factores_iniciales={'U': 0.3})
    final = sum(p for p, _q in (rc.repartos or {})['U'].fijas.values())
    assert final >= 0.9 * f0 - 1e-6 and not rc.cuadrado and set(rc.imposibles) == {'U'}, (SEMILLA, final / f0)


def test_006_rf46_086_rf124_en_el_proyecto_las_fijas_que_llenan_su_cabecera_quedan_a_escala_1():
    """006:RF-46, 086:RF-124 — en el proyecto, un alimentador cuyas fijas ya llenan su cabecera antes del primer flujo
    queda imposible con su causa y sus fijas con su P; los demás cuadran en el mismo flujo y se para pronto."""
    from convertersmartgrid.dominio.ajuste_cabecera import fijas_de, objetivo_de, reparto_inicial

    rng = random.Random(SEMILLA)
    repartos, objetivos = {}, {}
    for k in ('A1', 'A2', 'A3'):
        cab = rng.uniform(1000.0, 4000.0)
        o = objetivo_de({'medidor': k, 'alimentador': k, 'kw': cab, 'kvar': 0.3 * cab})
        kva = {f'{k}-S{i}': rng.uniform(50.0, 630.0) for i in range(1, 8)}
        pot = cab * (rng.uniform(1.0, 1.2) if k == 'A2' else rng.uniform(0.1, 0.4))
        fijas = fijas_de([{'codigo': '1', 'sed': f'{k}-F1', 'pot': pot, 'ea': 1.0, 'eri': 0.3}], o)
        repartos[k] = reparto_inicial(o, fijas, {f'{k}-F1': (1.0, 0.1), **{s: (0.0, 0.0) for s in kva}}, kva)
        objetivos[k] = o
    assert 'A2-F1' in repartos['A2'].fijas, ('las fijas de A2 pasan a escalar', repartos['A2'].avisos)
    pot_a2 = repartos['A2'].fijas['A2-F1'][0]
    res = cuadrar_conjunto(repartos, objetivos, _flujo, tolerancia=0.01,
                           factores_iniciales={k: r.a for k, r in repartos.items()})
    assert set(res.imposibles) == {'A2'} and not res.cuadrado, (SEMILLA, res.motivo)
    assert res.repartos['A2'].fijas['A2-F1'][0] == pot_a2 and res.imposibles['A2']['fijas_kw'] == pot_a2
    assert all(res.cumple(k) for k in ('A1', 'A3')) and res.flujos < ac.MAX_FLUJOS // 2, (SEMILLA, res.flujos)
