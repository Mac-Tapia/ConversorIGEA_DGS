"""Spec 016, T5: casos, sección de toda la troncal, enlace y migración sin DIgSILENT."""

from __future__ import annotations

import random

import pytest

from igea_dgs import obras_pf as op
from igea_dgs.estudios_pf import CON_PROYECTO, SIN_PROYECTO
from igea_dgs.troncal import Barra, Tramo, red_de, troncal

SEMILLAS = (3, 17, 41, 77)
CON, AMBOS = [CON_PROYECTO], [SIN_PROYECTO, CON_PROYECTO]
AAAC_120 = {'nombre': 'AAAC_120', 'clase': 'TypLne'}
CABLE_120 = {'nombre': 'N2XSY_120', 'clase': 'TypLne'}


def _tipos(kv: float) -> list[op.Tipo]:
    out = [op.Tipo(n, 'TypLne', {'uline': kv, 'qurs': q}) for n, q in
           (('AAAC_120', 120.0), ('AAAC_70', 70.0), ('CU_25', 25.0), ('N2XSY_120', 120.0),
            ('N2XSY_50', 50.0))]
    out += [op.Tipo(n, 'TypTr2', {'strn': s, 'utrn_h': kv, 'utrn_l': 0.38})
            for n, s in (('TR100', 0.1), ('TR250', 0.25))]
    return out


def _alimentador(rng, nombre: str, kv: float) -> op.RedAlimentador:
    """Un árbol sorteado con su troncal del camino más largo, cables, SED y barras de baja."""
    n = rng.randint(4, 40)
    barras = [f'{nombre}_N{i}' for i in range(n)]
    tramos, topo = {}, []
    for i in range(1, n):
        j = rng.randrange(i)
        cable = rng.random() < 0.2
        tipo = rng.choice(['N2XSY_120', 'N2XSY_50'] if cable else ['AAAC_120', 'AAAC_70', 'CU_25'])
        largo = rng.uniform(1, 800)
        t = f'{nombre}_L{i}'
        tramos[t] = op.Tramo(t, tipo, 1, cable, largo)
        topo.append(Tramo(t, barras[j], barras[i], largo))
    red = red_de([Barra(b) for b in barras], topo)
    seds = {f'TR_{nombre}_{k}': barras[rng.randrange(1, n)] for k in range(rng.randint(1, 6))}
    kvs = {b: kv for b in barras}
    kvs.update({f'{t}_BT': 0.38 for t in seds})
    return op.RedAlimentador(
        alimentador=nombre, kv=kv, barras=kvs, tramos=tramos,
        troncal=troncal(red, barras[0]).tramos,
        trafos={t: rng.choice(['TR100', 'TR250']) for t in seds},
        topologia=red, cabecera=barras[0], trafo_barra=seds)


def _obra(**datos) -> op.Obra:
    datos.setdefault('casos', AMBOS)
    return op.validar_obra(datos)


# --------------------------------------------------------------------------- casos
def test_lo_de_sin_proyecto_pasa_a_con_proyecto():
    """016:RF-11, 016:RF-13 — una obra en «Sin proyecto» va también en «Con proyecto»;
    pedirla solo en «Sin proyecto» se rechaza antes de escribir nada."""
    assert _obra(clase='terna', alimentador='A1').casos == tuple(AMBOS)
    assert _obra(clase='terna', alimentador='A1', casos=CON).casos == tuple(CON)
    with pytest.raises(op.ObrasError, match='pasa siempre'):
        _obra(clase='terna', alimentador='A1', casos=[SIN_PROYECTO])


@pytest.mark.parametrize('datos', [
    {'clase': 'enlace', 'alimentador': 'TA225', 'cede': 'IN111', 'tipo': AAAC_120},
    {'clase': 'migracion', 'alimentador': 'IN111', 'nodo': 'N7', 'kv_destino': 22.9},
])
def test_enlace_y_migracion_solo_en_con_proyecto(datos):
    """016:RF-14, 016:RF-25, 016:RF-53 — las construcciones nuevas y la migración van solo
    en «Con proyecto»: pedirlas en «Sin proyecto» se rechaza."""
    assert _obra(**datos, casos=CON).casos == tuple(CON)
    with pytest.raises(op.ObrasError, match='solo en «Con proyecto»'):
        _obra(**datos)


def test_las_obras_nuevas_vuelven_igual_del_espacio():
    """016:RF-23, 016:RF-51, 016:RF-6 — las obras nuevas se guardan y se reconstruyen igual."""
    obras = [
        _obra(clase='seccion', alimentador='A1', toda_troncal=True, tipo=AAAC_120,
              tipo_cable=CABLE_120),
        _obra(clase='enlace', alimentador='TA225', cede='IN111', tipo=AAAC_120, minima_m=0,
              origen='-14.03, -75.77', destino='NODE_1', casos=CON),
        _obra(clase='migracion', alimentador='IN111', nodo='N7', kv_destino=22.9, casos=CON),
    ]
    for obra in obras:
        assert op.validar_obra(obra.a_dict()) == obra


@pytest.mark.parametrize('datos, falta', [
    ({'clase': 'enlace', 'alimentador': 'TA225', 'tipo': AAAC_120}, 'cede'),
    ({'clase': 'enlace', 'alimentador': 'TA225', 'cede': 'TA225', 'tipo': AAAC_120}, 'distintos'),
    ({'clase': 'enlace', 'alimentador': 'TA225', 'cede': 'IN111'}, 'tipo'),
    ({'clase': 'enlace', 'alimentador': 'TA225', 'cede': 'IN111', 'tipo': AAAC_120,
      'minima_m': -1}, 'negativa'),
    ({'clase': 'enlace', 'alimentador': 'TA225', 'cede': 'IN111', 'tipo': AAAC_120,
      'origen': '95, 10'}, 'latitud'),
    ({'clase': 'migracion', 'alimentador': 'IN111', 'kv_destino': 22.9}, 'nodo'),
    ({'clase': 'migracion', 'alimentador': 'IN111', 'nodo': 'N7'}, 'tensión'),
    ({'clase': 'seccion', 'alimentador': 'A1', 'toda_troncal': True, 'tramos': ['L1'],
      'tipo': AAAC_120}, 'no las dos'),
])
def test_obra_nueva_incompleta_se_rechaza(datos, falta):
    """016:RF-23, 016:RF-31, 016:RF-51 — lo que falta o no vale se dice al definir la obra."""
    with pytest.raises(op.ObrasError, match=falta):
        _obra(**datos, casos=CON)


# --------------------------------------------------------------------------- sección
@pytest.mark.parametrize('semilla', SEMILLAS)
@pytest.mark.parametrize('con_cable', [False, True])
def test_seccion_de_toda_la_troncal(semilla, con_cable):
    """016:RF-6, 016:RF-7, 016:RF-8, 016:RF-9, 016:RF-59 — cada tramo aéreo de la troncal
    pasa al tipo pedido, sea del material que sea; los de cable, al tipo de cable o se
    listan; las derivaciones no se tocan; ningún tipo del proyecto cambia."""
    rng = random.Random(semilla)
    kv = rng.choice([10.0, 22.9])
    red = _alimentador(rng, 'A1', kv)
    tipos = _tipos(kv)
    antes = {t.nombre: dict(t.datos) for t in tipos}
    datos = {'clase': 'seccion', 'alimentador': 'A1', 'toda_troncal': True, 'tipo': AAAC_120}
    if con_cable:
        datos['tipo_cable'] = CABLE_120
    (fila,) = op.plan_simulacion([_obra(**datos)], {'A1': red}, tipos)
    assert not fila['error'], fila
    cambiados = {e['elemento']: e['tipo'] for e in fila['elementos']}
    esperado = {}
    for n in red.troncal:
        t = red.tramos[n]
        nuevo = ('N2XSY_120' if con_cable else None) if t.cable else 'AAAC_120'
        if nuevo and t.tipo != nuevo:
            esperado[n] = nuevo
    assert cambiados == esperado
    assert set(cambiados) <= set(red.troncal)
    resumen = fila['troncal']
    assert resumen['tramos'] == len(red.troncal)
    assert resumen['largo_m'] == pytest.approx(sum(red.tramos[n].largo_m for n in red.troncal), abs=0.1)
    por_tipo = {}
    for n in esperado:
        por_tipo[red.tramos[n].tipo] = por_tipo.get(red.tramos[n].tipo, 0) + red.tramos[n].largo_m
    assert resumen['cambian_m'] == pytest.approx({k: round(v, 1) for k, v in por_tipo.items()})
    cables = [n for n in red.troncal if red.tramos[n].cable]
    assert resumen['cables_sin_cambiar'] == ([] if con_cable else cables)
    assert bool(cables and not con_cable) == any('tramos de cable' in a for a in fila['avisos'])
    assert {t.nombre: dict(t.datos) for t in tipos} == antes


def test_seccion_de_toda_la_troncal_sin_troncal():
    """016:RF-6 — sin troncal leída no se cambia nada y se dice."""
    red = op.RedAlimentador('A1', 10.0, {'N0': 10.0}, {'L1': op.Tramo('L1', 'AAAC_70')})
    (fila,) = op.plan_simulacion([_obra(clase='seccion', alimentador='A1', toda_troncal=True,
                                        tipo=AAAC_120)], {'A1': red}, _tipos(10.0))
    assert 'troncal' in fila['error']


# --------------------------------------------------------------------------- enlace
def _dos(rng, kv_recibe=22.9, kv_cede=10.0):
    return {'TA225': _alimentador(rng, 'TA225', kv_recibe), 'IN111': _alimentador(rng, 'IN111', kv_cede)}


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_enlace_entre_tensiones_distintas(semilla):
    """016:RF-24, 016:RF-36, 016:RF-38, 016:RF-39, 016:RF-41, 016:RF-61 — el enlace va en
    su variación con los dos alimentadores; la línea, al tipo copiado a la tensión del que
    recibe, y el seccionador abierto del lado del que cede; con dos tensiones, se crea igual
    y se avisa de que no se puede cerrar hasta migrar."""
    rng = random.Random(semilla)
    redes = _dos(rng)
    tipos = _tipos(10.0)                               # la biblioteca está a 10 kV
    obra = _obra(clase='enlace', alimentador='TA225', cede='IN111', tipo=AAAC_120, minima_m=5,
                 casos=CON)
    (fila,) = op.plan_simulacion([obra], redes, tipos)
    assert not fila['error'], fila
    assert fila['variacion'] == 'Obra_enlace_TA225_IN111' and fila['casos'] == CON
    assert fila['tipo'] == 'AAAC_120_22_9kV'
    assert fila['tipos'][0]['datos']['uline'] == 22.9
    linea, seccionador = fila['elementos']
    assert linea['clase'] == 'ElmLne' and linea['tipo'] == 'AAAC_120_22_9kV' and '5 m' in linea['cambio']
    assert seccionador['clase'] == 'StaSwitch' and 'abierto' in seccionador['cambio']
    assert 'IN111' in seccionador['cambio']
    assert any('22.9 kV' in a and '10 kV' in a and 'migrar' in a for a in fila['avisos'])
    assert fila['enlace']['kv_recibe'] == 22.9 and fila['enlace']['kv_cede'] == 10.0


def test_enlace_a_la_misma_tension_no_avisa():
    """016:RF-61 — sin dos tensiones no hay aviso de migración."""
    redes = _dos(random.Random(5), 10.0, 10.0)
    (fila,) = op.plan_simulacion([_obra(clase='enlace', alimentador='TA225', cede='IN111',
                                        tipo=AAAC_120, casos=CON)], redes, _tipos(10.0))
    assert not fila['error'] and not any('migrar' in a for a in fila['avisos'])


def test_enlace_repetido_o_con_extremos_que_no_son_suyos():
    """016:RF-40, 016:RF-31, 016:RF-23 — otro enlace entre los mismos dos alimentadores, una
    barra que no es del alimentador o un alimentador que no está se rechazan."""
    redes = _dos(random.Random(6))
    tipos = _tipos(10.0)
    base = dict(clase='enlace', alimentador='TA225', cede='IN111', tipo=AAAC_120, casos=CON)
    (fila,) = op.plan_simulacion([_obra(**base)], redes, tipos, variaciones=['Obra_enlace_IN111_TA225'])
    assert 'Ya hay una obra de enlace' in fila['error']
    primera, segunda = op.plan_simulacion([_obra(**base), _obra(**base)], redes, tipos)
    assert not primera['error'] and 'Ya hay' in segunda['error']
    (fila,) = op.plan_simulacion([_obra(**base, origen='IN111_N1')], redes, tipos)
    assert 'IN111_N1' in fila['error'] and 'TA225' in fila['error']
    (fila,) = op.plan_simulacion([_obra(**base, origen='TA225_N1', destino='-14.0, -75.7')],
                                 redes, tipos)
    assert not fila['error'] and 'TA225_N1' in fila['elementos'][0]['cambio']
    (fila,) = op.plan_simulacion([_obra(**{**base, 'cede': 'XX9'})], redes, tipos)
    assert 'XX9' in fila['error']


# --------------------------------------------------------------------------- migración
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_migracion_de_lo_que_queda_aguas_abajo(semilla):
    """016:RF-52, 016:RF-54, 016:RF-55, 016:RF-56, 016:RF-57, 016:RF-58, 016:RF-59 — pasan a
    la tensión de destino las barras, los tramos y las SED de aguas abajo del nodo, con
    copias de tipo; nada más cambia, y se abre el tramo que entra al nodo."""
    rng = random.Random(semilla)
    red = _alimentador(rng, 'IN111', 10.0)
    nodo = rng.choice(sorted(b for b in red.topologia.barras if b != red.cabecera))
    tipos = _tipos(10.0)
    obra = _obra(clase='migracion', alimentador='IN111', nodo=nodo, kv_destino=22.9, casos=CON)
    (fila,) = op.plan_simulacion([obra], {'IN111': red}, tipos)
    assert not fila['error'], fila
    from igea_dgs.troncal import aguas_abajo
    parte = aguas_abajo(red.topologia, red.cabecera, nodo)
    por_clase = {}
    for e in fila['elementos']:
        por_clase.setdefault(e['clase'], set()).add(e['elemento'])
    assert por_clase['ElmTerm'] == set(parte.barras)
    assert por_clase['ElmLne'] == set(parte.tramos) | {parte.entrada}
    entrada = next(e for e in fila['elementos'] if e['elemento'] == parte.entrada)
    assert 'se abre' in entrada['cambio']
    seds = {t for t, b in red.trafo_barra.items() if b in set(parte.barras)}
    assert por_clase.get('ElmTr2', set()) == seds
    for e in fila['elementos']:
        if e.get('tipo'):
            assert e['tipo'].endswith('_22_9kV')
    assert all(t['datos'].get('uline', t['datos'].get('utrn_h')) == 22.9 for t in fila['tipos'])
    assert fila['parte']['entrada'] == parte.entrada and fila['kv_destino'] == 22.9


def test_migracion_nodo_ajeno_cabecera_o_misma_tension():
    """016:RF-65 — un nodo de otro alimentador se dice con el nodo y el alimentador; la
    cabecera y la tensión que ya tiene, también se rechazan."""
    red = _alimentador(random.Random(8), 'IN111', 10.0)
    tipos = _tipos(10.0)

    def error(**datos):
        datos = {'clase': 'migracion', 'alimentador': 'IN111', 'kv_destino': 22.9, 'casos': CON,
                 **datos}
        return op.plan_simulacion([op.validar_obra(datos)], {'IN111': red}, tipos)[0]['error']

    assert 'TA225_N3' in error(nodo='TA225_N3') and 'IN111' in error(nodo='TA225_N3')
    assert 'cabecera' in error(nodo=red.cabecera)
    assert 'ya está' in error(nodo='IN111_N1', kv_destino=10.0)


def test_migracion_avisa_si_el_enlace_no_queda_en_la_parte_que_pasa():
    """016:RF-66 — con el punto de enlace fuera de la parte que pasa se migra igual y se
    avisa; dentro, no."""
    barras = ['C', 'A', 'B', 'D']
    topo = red_de([Barra(b) for b in barras], [Tramo('L1', 'C', 'A', 10), Tramo('L2', 'A', 'B', 10),
                                              Tramo('L3', 'C', 'D', 10)])
    red = op.RedAlimentador('IN111', 10.0, {b: 10.0 for b in barras},
                            {n: op.Tramo(n, 'AAAC_70') for n in ('L1', 'L2', 'L3')},
                            topologia=topo, cabecera='C')
    obra = _obra(clase='migracion', alimentador='IN111', nodo='A', kv_destino=22.9, casos=CON)
    (fila,) = op.plan_simulacion([obra], {'IN111': red}, _tipos(10.0), destinos_enlace={'IN111': 'D'})
    assert not fila['error'] and any('sin alimentación' in a for a in fila['avisos'])
    (fila,) = op.plan_simulacion([obra], {'IN111': red}, _tipos(10.0), destinos_enlace={'IN111': 'B'})
    assert not any('sin alimentación' in a for a in fila['avisos'])


def test_migracion_avisa_de_un_anillo_que_une_las_dos_partes():
    """016:RF-58 — un anillo cerrado que une la parte que pasa con la que no se avisa."""
    barras = ['C', 'A', 'B', 'D']
    topo = red_de([Barra(b) for b in barras], [Tramo('L1', 'C', 'A', 10), Tramo('L2', 'A', 'B', 10),
                                              Tramo('L3', 'C', 'D', 10), Tramo('L4', 'D', 'B', 100)])
    red = op.RedAlimentador('IN111', 10.0, {b: 10.0 for b in barras},
                            {n: op.Tramo(n, 'AAAC_70') for n in ('L1', 'L2', 'L3', 'L4')},
                            topologia=topo, cabecera='C')
    obra = _obra(clase='migracion', alimentador='IN111', nodo='A', kv_destino=22.9, casos=CON)
    (fila,) = op.plan_simulacion([obra], {'IN111': red}, _tipos(10.0))
    assert any('L4' in a and 'anillo' in a for a in fila['avisos'])
