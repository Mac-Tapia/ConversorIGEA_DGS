"""Spec 011, T15b, y spec 013, T6: lo que la transferencia de carga decide sin DIgSILENT
(``transferencia_pf``)."""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

import pytest

from convertersmartgrid import transferencia_pf as tp
from convertersmartgrid.estudios_pf import Limites

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


# --------------------------------------------------------------------------- spec 013: instante común
def _serie(rng, inicio, n, *, sin_q=0.0, huecos=0.0):
    """Registros cada 15 minutos con kW y kVAR sorteados; algunos sin kVAR o sin registro."""
    out = []
    for k in range(n):
        if rng.random() < huecos:
            continue
        t = inicio + timedelta(minutes=15 * k)
        out.append((t, round(rng.uniform(100, 900), 1),
                    None if rng.random() < sin_q else round(rng.uniform(-50, 300), 1)))
    return out


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_instantes_comunes_sin_interpolar(semilla):
    """013:RF-22, 013:RF-27 — solo los registros que los dos tienen a la misma fecha y hora,
    del periodo elegido; un registro sin kW no cuenta y nada se interpola."""
    rng = random.Random(semilla)
    inicio = datetime(2026, 6, 30, 22)
    a = _serie(rng, inicio, 400, huecos=0.2)
    b = _serie(rng, inicio, 400, huecos=0.2)
    # Uno desplazado un segundo no coincide; uno sin kW tampoco.
    b.append((inicio + timedelta(days=1, seconds=1), 500.0, 10.0))
    a.append((inicio + timedelta(days=1, seconds=1, minutes=1), None, None))
    instantes = tp.instantes_comunes({'A': a, 'B': b}, '2026-07')
    esperado = sorted({t for t, kw, _q in a if kw is not None and t.month == 7}
                      & {t for t, kw, _q in b if kw is not None and t.month == 7})
    assert [i.fecha for i in instantes] == esperado
    de_a, de_b = {t: (kw, q) for t, kw, q in a}, {t: (kw, q) for t, kw, q in b}
    for i in instantes:
        assert i.objetivos == {'A': de_a[i.fecha], 'B': de_b[i.fecha]}
    # Con el año entero, también los de junio (025:RF-7).
    assert len(tp.instantes_comunes({'A': a, 'B': b}, '2026')) >= len(instantes)


def test_curva_de_un_alimentador_con_varios_medidores():
    """013:RF-27 — con dos medidores, la suma en los instantes que tienen los dos; sin kVAR en
    uno, el del instante queda sin valor y no en cero."""
    t1, t2, t3 = (datetime(2026, 7, 1, h) for h in (0, 1, 2))
    curva = tp.curva_del_alimentador([[(t1, 100.0, 10.0), (t2, 200.0, None), (t3, 50.0, 5.0)],
                                      [(t1, 1.0, 1.0), (t2, 2.0, 2.0)]])
    assert curva == [(t1, 101.0, 11.0), (t2, 202.0, None)]


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_frontera_no_dominada_igual_que_la_comparacion_completa(semilla):
    """013:RF-27 — un instante se descarta solo si otro tiene P y |Q| de los dos al menos
    iguales y alguna mayor; sin kVAR no se descarta ni descarta; cada descarte dice quién lo
    domina; no hay tope de candidatos."""
    rng = random.Random(semilla)
    a = _serie(rng, datetime(2026, 7, 1), 300, sin_q=0.05)
    b = _serie(rng, datetime(2026, 7, 1), 300, sin_q=0.05)
    instantes = tp.instantes_comunes({'A': a, 'B': b}, '2026-07')
    cand, desc = tp.frontera_no_dominada(instantes, 'A', 'B')

    def comp(i):
        (pa, qa), (pb, qb) = i.objetivos['A'], i.objetivos['B']
        return None if qa is None or qb is None else (pa, abs(qa), pb, abs(qb))

    def domina(x, y):
        return all(p >= q for p, q in zip(x, y)) and any(p > q for p, q in zip(x, y))

    esperado = [i for i in instantes if comp(i) is None
                or not any(comp(j) is not None and domina(comp(j), comp(i)) for j in instantes)]
    assert [i.fecha for i in cand] == [i.fecha for i in esperado]
    assert set(desc) == {i.fecha for i in instantes} - {i.fecha for i in cand}
    por_fecha = {i.fecha: i for i in instantes}
    for t, quien in desc.items():
        assert domina(comp(por_fecha[quien]), comp(por_fecha[t]))


def test_candidatos_de_los_dos_sentidos_y_su_cobertura():
    """013:RF-27, 013:RF-28 — los candidatos son la unión de las fronteras de los dos
    sentidos, con la cobertura examinada."""
    t = [datetime(2026, 7, 1, h) for h in range(3)]
    # t0 domina a t1 en los dos sentidos; t2 tiene más en B y menos en A: no lo domina nadie.
    instantes = [tp.InstanteTransferencia(t[0], {'A': (500.0, 50.0), 'B': (300.0, 30.0)}),
                 tp.InstanteTransferencia(t[1], {'A': (400.0, 40.0), 'B': (200.0, 20.0)}),
                 tp.InstanteTransferencia(t[2], {'A': (100.0, 10.0), 'B': (900.0, 90.0)})]
    cand, cob = tp.candidatos_de_transferencia(instantes, 'A', 'B')
    assert [i.fecha for i in cand] == [t[0], t[2]]
    assert cob['instantes_comunes'] == 3 and cob['candidatos'] == 2
    assert cob['desde'] == '2026-07-01 00:00:00' and cob['hasta'] == '2026-07-01 02:00:00'
    assert cob['por_sentido']['A->B']['descartados'] == {'2026-07-01 01:00:00': '2026-07-01 00:00:00'}


def _verif(instante, kw, *, verificado=True, cede='A', recibe='B'):
    return {'caso': 'Sin proyecto', 'cede': cede, 'recibe': recibe, 'enlace': 'NA',
            'instante': instante, 'verificado': verificado,
            'motivo': '' if verificado else 'no cuadra', 'admite': kw > 0,
            'maximo_seccionador': {'punto': 'S', 'carga_kw': kw, 'carga_kva': kw}, 'maximo_nodo': None}


def test_critico_es_la_menor_transferencia_viable():
    """013:RF-27, 013:RF-28 — el crítico de cada sentido es el instante que deja la menor
    transferencia viable; a igual carga, el primero; con todo verificado es aceptable."""
    cand = ['2026-07-01 10:00:00', '2026-07-02 19:00:00', '2026-07-03 19:00:00']
    vs = [_verif(cand[0], 400.0), _verif(cand[1], 150.0), _verif(cand[2], 150.0),
          _verif(cand[0], 90.0, cede='B', recibe='A'), _verif(cand[1], 0.0, cede='B', recibe='A'),
          _verif(cand[2], 300.0, cede='B', recibe='A')]
    criticos, estado = tp.seleccionar_critico(vs, cand)
    assert [(c['cede'], c['instante'], c['transferida_kw']) for c in criticos] == [
        ('A', cand[1], 150.0), ('B', cand[1], 0.0)]
    assert estado['aceptable'] and not estado['faltantes'] and estado['criterio']


@pytest.mark.parametrize('falta', ['no_verificado', 'no_calculado', 'cancelado', 'sin_candidatos'])
def test_sin_evidencia_completa_no_es_aceptable(falta):
    """013:RF-29 — si un candidato no se verificó o no se calculó, si se canceló o si no hay
    instantes comunes, el resultado no es aceptable y se dice qué evidencia falta."""
    cand = ['2026-07-01 10:00:00', '2026-07-02 19:00:00']
    vs = [_verif(cand[0], 400.0), _verif(cand[1], 150.0, verificado=falta != 'no_verificado')]
    if falta == 'no_calculado':
        vs = vs[:1]
    if falta == 'sin_candidatos':
        vs, cand = [], []
    criticos, estado = tp.seleccionar_critico(vs, cand, cancelado=falta == 'cancelado')
    assert not estado['aceptable'] and estado['faltantes']
    if falta == 'no_verificado':
        # Lo observado se da, pero solo con los verificados: no es la capacidad comprobada.
        assert [c['instante'] for c in criticos] == [cand[0]]
        assert any(cand[1] in f and 'no cuadra' in f for f in estado['faltantes'])


def test_libro_con_pasos_sed_y_cobertura(tmp_path):
    """013:RF-23, 013:RF-24, 013:RF-26, 013:RF-28 — el descargable es un libro con los pasos,
    las SED transferidas en una hoja aparte y la cobertura temporal, que se relee igual."""
    from openpyxl import load_workbook

    resultados = [{'caso': 'Sin proyecto', 'cede': 'A', 'recibe': 'B', 'enlace': 'NA',
                   'instante': '2026-07-02 19:00:00', 'punto_transferido': 'S2',
                   'pasos': [{'paso': 1, 'punto': 'N3', 'tipo': 'nodo', 'carga_kw': 50.0,
                              'carga_kva': 52.0, 'converge': True, 'viable': True}],
                   'sed_transferidas': [{'sed': 'SE2', 'kw': 30.0, 'kvar': 40.0, 'kva': 50.0},
                                        {'sed': 'SE1', 'kw': 20.0, 'kvar': 0.0, 'kva': 20.0}]}]
    temporal = {'candidatos': [{'instante': '2026-07-02 19:00:00',
                                'objetivos': {'A': [300.0, 90.0], 'B': [500.0, None]},
                                'medido': {'A': [301.0, 88.0], 'B': [499.0, 120.0]},
                                'verificado': True, 'motivo': ''}]}
    libro = load_workbook(tp.escribir_fichero(resultados, tmp_path / 't.xlsx', temporal))
    assert libro.sheetnames == ['Pasos', 'SED transferidas', 'Cobertura temporal']

    def filas(hoja):
        return [list(f) for f in libro[hoja].iter_rows(values_only=True)]

    sed = filas('SED transferidas')
    assert sed[0] == list(tp.COLUMNAS_SED)
    assert [f[6] for f in sed[1:]] == ['SE1', 'SE2'] and sed[2][7:] == [30.0, 40.0, 50.0]
    assert filas('Pasos')[1][:2] == ['2026-07-02 19:00:00', 'Sin proyecto']
    cob = filas('Cobertura temporal')
    assert cob[1] == ['2026-07-02 19:00:00', 'A', 300.0, 90.0, 301.0, 88.0, True, None]
    assert cob[2][:4] == ['2026-07-02 19:00:00', 'B', 500.0, None]
    # Con otra extensión, el CSV de siempre (011:RF-121).
    csv = tp.escribir_fichero(resultados, tmp_path / 't.csv').read_text(encoding='utf-8-sig')
    assert csv.startswith('caso;cede')
