"""Spec 011, T15b: lo que la transferencia de carga decide sin DIgSILENT (``transferencia_pf``)."""

from __future__ import annotations

import math
import random

import pytest

from igea_dgs import transferencia_pf as tp
from igea_dgs.estudios_pf import Limites

#: Semillas de los sorteos: largo del camino, cargas, seccionadores y paso que limita.
SEMILLAS = (5, 17, 38, 71)
LIMITES = Limites(0.95, 1.05, 100.0)


def _camino(rng, *, seccionadores=True):
    """Puntos desde el enlace hacia la cabecera del que cede: barras con su carga y, entre
    algunas, un seccionador."""
    puntos = []
    for i in range(rng.randint(3, 9)):
        if seccionadores and i and rng.random() < 0.5:
            puntos.append(tp.Punto(f'SECC_{i}', 'seccionador'))
        puntos.append(tp.Punto(f'N{i}', 'nodo', round(rng.uniform(20, 400), 1),
                               round(rng.uniform(5, 120), 1)))
    return puntos


def _medida(paso, *, converge=True, u_min=0.99, carga=60.0):
    return {'converge': converge,
            'barras': [('R1', 1.0), (f'R_{paso.punto}', u_min)],
            'elementos': [('L_R1', 'ElmLne', carga)],
            'cabecera_kw': 1000 + paso.carga_kw, 'cabecera_kvar': 300 + paso.carga_kvar}


# --------------------------------------------------------------------------- pasos
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_carga_transferida_en_cada_paso(semilla):
    """011:RF-110 — en cada paso, la carga que queda del lado del enlace: con un seccionador
    abierto, las barras anteriores a él; abriendo en una barra, hasta ella incluida; en kW
    y en kVA."""
    rng = random.Random(semilla)
    puntos = _camino(rng)
    pasos = tp.pasos_del_camino(puntos)
    nodos = [p for p in puntos if p.tipo == 'nodo']
    for paso in pasos:
        i = puntos.index(next(p for p in puntos if p.nombre == paso.punto))
        antes = [p for p in puntos[:i] if p.tipo == 'nodo']
        if paso.tipo == 'nodo':
            antes.append(puntos[i])
        assert paso.carga_kw == pytest.approx(sum(p.carga_kw for p in antes))
        assert paso.carga_kvar == pytest.approx(sum(p.carga_kvar for p in antes))
        assert paso.carga_kva == pytest.approx(math.hypot(paso.carga_kw, paso.carga_kvar))
    assert [p.punto for p in pasos if p.tipo == 'nodo'] == [n.nombre for n in nodos]
    assert [p.indice for p in pasos] == list(range(1, len(pasos) + 1))


def test_un_seccionador_al_principio_no_transfiere_nada_y_no_es_paso():
    """011:RF-110 — un seccionador pegado al enlace dejaría la carga en cero: no es un paso."""
    puntos = [tp.Punto('SECC_0', 'seccionador'), tp.Punto('N1', 'nodo', 100, 30)]
    assert [p.punto for p in tp.pasos_del_camino(puntos)] == ['N1']


# --------------------------------------------------------------------------- juicio
def test_paso_viable_si_converge_sin_violaciones():
    """011:RF-111 — viable si el flujo converge y nada pasa de la cargabilidad ni sale de los
    límites de tensión; si no, el motivo con el elemento y su valor."""
    paso = tp.pasos_del_camino([tp.Punto('N1', 'nodo', 100, 30)])[0]
    assert tp.juzgar(paso, _medida(paso), LIMITES) == (True, None)
    viable, limita = tp.juzgar(paso, _medida(paso, carga=130.0), LIMITES)
    assert not viable and limita == {'motivo': 'sobrecarga', 'elemento': 'L_R1', 'valor': 130.0,
                                     'limite': 100.0}
    viable, limita = tp.juzgar(paso, _medida(paso, u_min=0.91), LIMITES)
    assert not viable and limita['motivo'] == 'tension' and limita['elemento'] == 'R_N1'
    assert limita['valor'] == 0.91
    viable, limita = tp.juzgar(paso, _medida(paso, converge=False), LIMITES)
    assert not viable and limita['motivo'] == 'no converge'


def test_entre_varias_violaciones_limita_la_peor():
    """011:RF-114 — con sobrecarga y tensión a la vez, limita la que más se pasa de su límite."""
    paso = tp.pasos_del_camino([tp.Punto('N1', 'nodo', 100, 30)])[0]
    medida = _medida(paso, carga=101.0, u_min=0.80)
    assert tp.juzgar(paso, medida, LIMITES)[1]['motivo'] == 'tension'
    medida = _medida(paso, carga=180.0, u_min=0.949)
    assert tp.juzgar(paso, medida, LIMITES)[1]['motivo'] == 'sobrecarga'


# --------------------------------------------------------------------------- sentido
def _sentido(rng, puntos, corte):
    """Medidas de un sentido en que los pasos dejan de ser viables a partir de ``corte``."""
    pasos = tp.pasos_del_camino(puntos)
    medidas = [_medida(p, carga=60.0 if p.indice < corte else 120.0 + p.indice) for p in pasos]
    return pasos, medidas


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_maximo_por_seccionador_y_por_nodo(semilla):
    """011:RF-112, 011:RF-113, 011:RF-114, 011:RF-115 — el seccionador viable más lejano
    con su carga, el nodo viable más lejano con la suya, el elemento que limita en el
    primer paso no viable y, por paso, carga, tensión mínima, cargabilidad y cabecera."""
    rng = random.Random(semilla)
    puntos = _camino(rng)
    pasos, _ = _sentido(rng, puntos, 1)
    corte = rng.randint(2, len(pasos) + 1)
    pasos, medidas = _sentido(rng, puntos, corte)
    r = tp.resumir_sentido(pasos, medidas, LIMITES)
    viables = [p for p in pasos if p.indice < corte]
    secc = [p for p in viables if p.tipo == 'seccionador']
    assert r['admite'] is True
    if secc:
        assert r['maximo_seccionador'] == {'punto': secc[-1].punto, 'carga_kw': secc[-1].carga_kw,
                                           'carga_kva': secc[-1].carga_kva}
    else:
        assert r['maximo_seccionador'] is None
    nodo = [p for p in viables if p.tipo == 'nodo'][-1]
    assert r['maximo_nodo']['punto'] == nodo.punto
    if corte <= len(pasos):
        assert r['limita'] == {'paso': corte, 'punto': pasos[corte - 1].punto, 'motivo': 'sobrecarga',
                               'elemento': 'L_R1', 'valor': 120.0 + corte, 'limite': 100.0}
    else:
        assert r['limita'] is None
    for fila, paso in zip(r['pasos'], pasos):
        assert fila['punto'] == paso.punto and fila['carga_kw'] == paso.carga_kw
        assert fila['vm_min'] is not None and fila['cargabilidad_max'] is not None
        assert fila['cabecera_recibe_kw'] == 1000 + paso.carga_kw


def test_ningun_paso_viable():
    """011:RF-116 — si ni el primer paso es viable, el sentido no admite transferencia y se
    dice qué lo impide."""
    puntos = [tp.Punto('N1', 'nodo', 100, 30), tp.Punto('SECC', 'seccionador'),
              tp.Punto('N2', 'nodo', 50, 10)]
    pasos = tp.pasos_del_camino(puntos)
    medidas = [_medida(p, u_min=0.90) for p in pasos]
    r = tp.resumir_sentido(pasos, medidas, LIMITES)
    assert r['admite'] is False and r['maximo_seccionador'] is None and r['maximo_nodo'] is None
    assert r['limita']['paso'] == 1 and r['limita']['motivo'] == 'tension'
    assert any('no admite' in a and 'R_N1' in a for a in r['avisos'])


def test_sin_seccionadores_solo_por_nodos():
    """011:RF-117 — un camino sin seccionadores da solo el resultado por nodos, y lo dice."""
    rng = random.Random(3)
    puntos = _camino(rng, seccionadores=False)
    pasos = tp.pasos_del_camino(puntos)
    r = tp.resumir_sentido(pasos, [_medida(p) for p in pasos], LIMITES)
    assert r['maximo_seccionador'] is None and r['maximo_nodo'] is not None
    assert any('ningún seccionador' in a for a in r['avisos'])


def test_sin_distinguir_seccionadores_solo_por_nodos_y_pide_reconvertir():
    """011:RF-129 — si el proyecto no distingue los seccionadores, solo por nodos, y se pide
    volver a convertir o cargar la entrada."""
    puntos = [tp.Punto('N1', 'nodo', 100, 30), tp.Punto('SECC', 'seccionador'),
              tp.Punto('N2', 'nodo', 50, 10)]
    pasos = tp.pasos_del_camino(puntos)
    r = tp.resumir_sentido(pasos, [_medida(p) for p in pasos], LIMITES,
                           seccionadores_reconocidos=False)
    assert r['maximo_seccionador'] is None and r['maximo_nodo']['punto'] == 'N2'
    assert any('volver a convertir' in a for a in r['avisos'])


def test_un_viable_despues_de_uno_que_no_lo_es_se_avisa():
    """011:RF-112 — el máximo es el seccionador viable más lejano; si antes hay un paso que no
    lo es, se avisa, porque el resultado no crece con la carga como se espera."""
    puntos = [tp.Punto('N1', 'nodo', 100, 30), tp.Punto('S1', 'seccionador'),
              tp.Punto('N2', 'nodo', 50, 10), tp.Punto('S2', 'seccionador'),
              tp.Punto('N3', 'nodo', 50, 10)]
    pasos = tp.pasos_del_camino(puntos)
    medidas = [_medida(p, carga=130.0 if p.punto == 'N2' else 50.0) for p in pasos]
    r = tp.resumir_sentido(pasos, medidas, LIMITES)
    assert r['maximo_seccionador']['punto'] == 'S2'
    assert any('N2' in a and 'antes' in a for a in r['avisos'])


# --------------------------------------------------------------------------- fichero
def test_fichero_una_fila_por_caso_sentido_enlace_y_paso(tmp_path):
    """011:RF-121 — una fila por caso, sentido, enlace y paso, ordenadas, y el mismo fichero
    byte a byte con los mismos resultados aunque lleguen en otro orden."""
    rng = random.Random(9)
    resultados = []
    for caso in ('Sin proyecto', 'Con proyecto'):
        for cede, recibe in (('A1', 'A2'), ('A2', 'A1')):
            for enlace in ('NA_1', 'NA_2'):
                puntos = _camino(rng)
                pasos = tp.pasos_del_camino(puntos)
                r = tp.resumir_sentido(pasos, [_medida(p) for p in pasos], LIMITES)
                resultados.append({'caso': caso, 'cede': cede, 'recibe': recibe, 'enlace': enlace,
                                   **r})
    filas = tp.filas_fichero(resultados)
    assert len(filas) == sum(len(r['pasos']) for r in resultados)
    claves = [(f['caso'], f['cede'], f['enlace'], f['paso']) for f in filas]
    assert claves == sorted(claves)
    a = tp.escribir_fichero(resultados, tmp_path / 'a.csv')
    rng.shuffle(resultados)
    b = tp.escribir_fichero(resultados, tmp_path / 'b.csv')
    assert a.read_bytes() == b.read_bytes()
    assert a.read_text(encoding='utf-8-sig').splitlines()[0].split(';') == list(tp.COLUMNAS)


# --------------------------------------------------------------------------- capacidad
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_biseccion_da_el_mayor_factor_viable(semilla):
    """011:RF-125 — por flujos sucesivos: el mayor factor viable, con la precisión pedida."""
    rng = random.Random(semilla)
    limite = rng.uniform(1.0, 300.0)
    llamadas = []

    def es_viable(k):
        llamadas.append(k)
        return k <= limite

    k, tope = tp.maximo_factor(es_viable)
    assert not tope and k <= limite and limite - k <= tp.TOLERANCIA_FACTOR * limite + 1e-12
    assert len(llamadas) < 60


def test_biseccion_sin_limite_lo_dice():
    """011:RF-125 — si nada limita hasta el tope, se devuelve el tope y se dice."""
    assert tp.maximo_factor(lambda k: True) == (tp.TOPE_FACTOR, True)


def test_margen_del_enlace():
    """011:RF-123 — capacidad menos lo que ya transfiere."""
    assert tp.margen(900.0, 250.0) == 650.0
    assert tp.margen(None, 250.0) is None
