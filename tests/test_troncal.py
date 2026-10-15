"""Troncal por el camino más largo y aguas abajo de un nodo (spec 016, T3).

Las redes se sortean: tamaño, forma, longitudes, nombres y tramos abiertos. La troncal se
contrasta con una fuerza bruta que recorre el camino de la cabecera a cada barra.
"""
from __future__ import annotations

import math
import random

import pytest

from igea_dgs.troncal import (Barra, Tramo, TroncalError, _metros, aguas_abajo, conexion_en,
                              cortar_trazado, extremos_del_enlace, partir, punto_en_troncal,
                              punto_mas_cercano, red_de, troncal)


def _sorteada(rng: random.Random, *, abiertos: float = 0.0):
    """Árbol de tamaño sorteado; cada barra nueva cuelga de una anterior al azar."""
    n = rng.randint(1, 400)
    nombres = [f'B{i:04d}' for i in range(n + 1)]
    rng.shuffle(nombres)
    tramos = []
    for i in range(1, n + 1):
        j = rng.randrange(i)
        lados = (nombres[j], nombres[i]) if rng.random() < 0.5 else (nombres[i], nombres[j])
        tramos.append(Tramo(f'T{rng.randrange(10**6):06d}_{i}', *lados,
                            largo_m=rng.choice([1.0, 2.0, rng.uniform(5, 900)]),
                            cerrado=rng.random() >= abiertos))
    rng.shuffle(tramos)
    return red_de([Barra(b) for b in nombres], tramos), nombres[0]


def _fuerza_bruta(red, cabecera):
    """(largo, tupla de nombres) del mejor camino, probando todas las barras."""
    mejor = None
    for destino in red.barras:
        # El camino único del árbol, por búsqueda en profundidad desde la cabecera.
        pila = [(cabecera, ())]
        visto = {cabecera}
        while pila:
            u, camino = pila.pop()
            if u == destino:
                largo = sum(red.por_nombre()[t].largo_m for t in camino)
                clave = (-round(largo, 6), camino)
                mejor = clave if mejor is None or clave < mejor else mejor
                break
            for v, t in red.vecinos.get(u, ()):
                if v not in visto:
                    visto.add(v)
                    pila.append((v, camino + (t.nombre,)))
    return -mejor[0], mejor[1]


@pytest.mark.parametrize('semilla', range(40))
def test_troncal_es_el_camino_mas_largo(semilla):
    """016:RF-1, 016:RF-3 — el camino continuo más largo desde la cabecera, aunque el
    alimentador no tenga enlace con ningún otro."""
    rng = random.Random(semilla)
    red, cabecera = _sorteada(rng)
    largo, camino = _fuerza_bruta(red, cabecera)
    t = troncal(red, cabecera)
    assert t.tramos == camino
    assert t.largo_m == pytest.approx(largo)


@pytest.mark.parametrize('semilla', range(20))
def test_los_tramos_abiertos_no_cuentan(semilla):
    """016:RF-4 — un tramo abierto o fuera de servicio corta el camino."""
    rng = random.Random(1000 + semilla)
    red, cabecera = _sorteada(rng, abiertos=0.2)
    cerrados = {t.nombre for t in red.tramos if t.cerrado}
    t = troncal(red, cabecera)
    assert set(t.tramos) <= cerrados
    largo, camino = _fuerza_bruta(red, cabecera)
    assert t.tramos == camino and t.largo_m == pytest.approx(largo)


def test_desempate_no_depende_del_orden_de_lectura():
    """016:RF-5 — dos ramas de la misma longitud: siempre la de nombres menores, se lean
    los tramos en el orden que se lean."""
    tramos = [Tramo('T_b', 'C', 'X', 100.0), Tramo('T_a', 'C', 'Y', 100.0),
              Tramo('T_c', 'X', 'X2', 50.0), Tramo('T_d', 'Y', 'Y2', 50.0)]
    barras = [Barra(n) for n in ('C', 'X', 'Y', 'X2', 'Y2')]
    rng = random.Random(7)
    vistos = set()
    for _ in range(20):
        rng.shuffle(tramos)
        rng.shuffle(barras)
        vistos.add(troncal(red_de(barras, tramos), 'C').tramos)
    assert vistos == {('T_a', 'T_d')}


def test_un_solo_tramo_y_tramos_de_un_metro():
    """016:RF-1 — un alimentador de un tramo; los tramos de 1 m entre equipos cuentan
    para la continuidad."""
    assert troncal(red_de([Barra('C'), Barra('A')], [Tramo('T1', 'C', 'A', 30.0)]), 'C').tramos == ('T1',)
    red = red_de([Barra(n) for n in 'CABD'],
                 [Tramo('T1', 'C', 'A', 500.0), Tramo('SW', 'A', 'B', 1.0), Tramo('T2', 'B', 'D', 400.0)])
    assert troncal(red, 'C').tramos == ('T1', 'SW', 'T2')


def test_un_anillo_cerrado_se_avisa_y_no_bloquea():
    """016:RF-1 — la red es radial; si un anillo está cerrado, el tramo que lo cierra se
    deja fuera y se dice, sin error."""
    red = red_de([Barra(n) for n in 'CABD'],
                 [Tramo('T1', 'C', 'A', 100.0), Tramo('T2', 'A', 'B', 100.0),
                  Tramo('T3', 'C', 'D', 100.0), Tramo('T4', 'D', 'B', 100.0)])
    t = troncal(red, 'C')
    assert len(t.mallas) == 1 and t.mallas[0] not in t.tramos
    assert t.largo_m == pytest.approx(200.0)


def test_cabecera_que_no_esta():
    """016:RF-2 — la troncal es de la red leída: una cabecera ajena se dice por su nombre."""
    with pytest.raises(TroncalError, match='XX'):
        troncal(red_de([Barra('C')], []), 'XX')


@pytest.mark.parametrize('semilla', range(20))
def test_aguas_abajo_de_un_nodo(semilla):
    """016:RF-64 — el nodo y todo lo que cuelga de él visto desde la cabecera, más el
    tramo que entra al nodo (el que se abre por RF-58)."""
    rng = random.Random(2000 + semilla)
    red, cabecera = _sorteada(rng)
    nodo = rng.choice(sorted(red.barras))
    sub = aguas_abajo(red, cabecera, nodo)
    # Fuerza bruta: una barra está aguas abajo si su camino desde la cabecera pasa por el nodo.
    from igea_dgs.troncal import arbol
    a = arbol(red, cabecera)
    dentro = set()
    for b in red.barras:
        u = b
        while u is not None:
            if u == nodo:
                dentro.add(b)
                break
            u = a.padre[u][0] if a.padre[u] is not None else None
    assert set(sub.barras) == dentro
    tramos = {t.nombre for t in red.tramos if t.desde in dentro and t.hasta in dentro}
    assert set(sub.tramos) == tramos
    if nodo == cabecera:
        assert sub.entrada is None
    else:
        assert sub.entrada == a.padre[nodo][1].nombre and sub.entrada not in sub.tramos


def test_nodo_de_otro_alimentador():
    """016:RF-65 — un nodo que no está en el alimentador se dice con su nombre."""
    red = red_de([Barra('C'), Barra('A')], [Tramo('T1', 'C', 'A', 10.0)])
    with pytest.raises(TroncalError, match='Z9'):
        aguas_abajo(red, 'C', 'Z9')


def test_troncal_de_in111_con_los_txt_reales(txt_dataset):
    """016:RF-1 — IN111 del TXT de referencia: 71 tramos y 13,58 km. Tiene tres anillos
    cerrados; cada barra cuelga del lado por el que llega antes en metros."""
    from igea_dgs.model import build_feeder_model

    m = build_feeder_model(txt_dataset, txt_dataset.resolve_feeder('IN111'), strict=False,
                           include_geography=False)
    nodos = {n for ln in m.lines for n in (ln.from_node, ln.to_node)}
    red = red_de([Barra(n) for n in nodos],
                 [Tramo(ln.section_id, ln.from_node, ln.to_node, ln.length_m, cable=not ln.overhead)
                  for ln in m.lines])
    t = troncal(red, m.source_node)
    assert len(t.tramos) == 71 and len(t.mallas) == 3
    assert t.largo_m / 1000 == pytest.approx(13.58, abs=0.005)


@pytest.mark.parametrize('semilla', range(20))
def test_con_anillos_cada_barra_por_su_camino_mas_corto(semilla):
    """016:RF-1, 016:RF-5 — con anillos cerrados sorteados, cada barra cuelga del camino
    más corto en metros (Bellman-Ford como referencia) y el resultado no depende del orden
    de lectura."""
    from igea_dgs.troncal import arbol

    rng = random.Random(3000 + semilla)
    red, cabecera = _sorteada(rng)
    nombres = sorted(red.barras)
    extra = [Tramo(f'M{k}', rng.choice(nombres), rng.choice(nombres), rng.uniform(1, 900))
             for k in range(rng.randint(1, 10))]
    tramos = list(red.tramos) + extra
    red = red_de(red.barras.values(), tramos)
    dist = {b: float('inf') for b in red.barras}
    dist[cabecera] = 0.0
    for _ in range(len(dist)):
        for t in tramos:
            if t.desde == t.hasta:
                continue
            for a, b in ((t.desde, t.hasta), (t.hasta, t.desde)):
                if dist[a] + t.largo_m < dist[b]:
                    dist[b] = dist[a] + t.largo_m
    a = arbol(red, cabecera)
    for b, d in a.distancia_m.items():
        assert d == pytest.approx(dist[b])
    rng.shuffle(tramos)
    assert troncal(red_de(red.barras.values(), tramos), cabecera) == troncal(red, cabecera)


# --------------------------------------------------------------------------- T4: conexión
ORIGEN = (-14.0, -75.7)


def _polilinea(rng, n=None, centro=ORIGEN, radio_grados=0.01):
    n = n or rng.randint(2, 30)
    lat = centro[0] + rng.uniform(-radio_grados, radio_grados)
    lon = centro[1] + rng.uniform(-radio_grados, radio_grados)
    out = [(lat, lon)]
    for _ in range(n - 1):
        lat += rng.uniform(-0.002, 0.002)
        lon += rng.uniform(-0.002, 0.002)
        out.append((lat, lon))
    return tuple(out)


def _muestras(trazado, por_segmento=400):
    """Puntos densos del trazado con su fracción en metros: la referencia de fuerza bruta."""
    xy = [_metros(p, trazado[0]) for p in trazado]
    largos = [math.dist(a, b) for a, b in zip(xy, xy[1:])]
    total, acumulado, out = sum(largos), 0.0, []
    for i, (p, q) in enumerate(zip(trazado, trazado[1:])):
        for k in range(por_segmento + 1):
            s = k / por_segmento
            out.append(((acumulado + s * largos[i]) / total,
                        (p[0] + s * (q[0] - p[0]), p[1] + s * (q[1] - p[1]))))
        acumulado += largos[i]
    return out


def _largo(trazado):
    return sum(math.dist(_metros(a, trazado[0]), _metros(b, trazado[0]))
               for a, b in zip(trazado, trazado[1:]))


@pytest.mark.parametrize('semilla', range(25))
def test_punto_mas_cercano_sobre_el_trazado(semilla):
    """016:RF-15 — el punto del trazado GPS más cercano y su fracción medida en metros a lo
    largo del trazado (referencia: el trazado muestreado cada pocos metros)."""
    rng = random.Random(4000 + semilla)
    trazado = _polilinea(rng)
    punto = (ORIGEN[0] + rng.uniform(-0.02, 0.02), ORIGEN[1] + rng.uniform(-0.02, 0.02))
    fraccion, distancia, gps = punto_mas_cercano(trazado, punto)
    ref = min(math.hypot(*_metros(q, punto)) for _, q in _muestras(trazado))
    assert distancia <= ref + 1e-6 and distancia == pytest.approx(ref, abs=2.0)
    assert math.hypot(*_metros(gps, punto)) == pytest.approx(distancia, abs=1e-6)
    uno, _ = cortar_trazado(trazado, fraccion)
    assert math.hypot(*_metros(uno[-1], gps)) < 0.05       # la proyección local cambia de origen


def test_sin_trazado_la_recta_entre_las_barras():
    """016:RF-15 — sin trazado, la recta entre las dos barras."""
    red = red_de([Barra('A', gps=(-14.0, -75.70)), Barra('B', gps=(-14.0, -75.69))],
                 [Tramo('T', 'A', 'B', 1000.0)])
    c = conexion_en(red, red.tramos[0], (-13.999, -75.6975), None)
    assert c.parte and c.fraccion == pytest.approx(0.25, abs=1e-3)


@pytest.mark.parametrize('semilla', range(25))
def test_partir_suma_la_longitud_y_corta_el_trazado(semilla):
    """016:RF-18 — las dos partes suman la longitud del tramo en la proporción del punto,
    y cada una se queda con su parte del trazado."""
    rng = random.Random(5000 + semilla)
    largo, fraccion = rng.uniform(1, 5000), rng.uniform(0.01, 0.99)
    l1, l2 = partir(largo, fraccion)
    assert l1 + l2 == pytest.approx(largo) and l1 == pytest.approx(largo * fraccion)
    trazado = _polilinea(rng)
    uno, dos = cortar_trazado(trazado, fraccion)
    assert uno[0] == trazado[0] and dos[-1] == trazado[-1] and uno[-1] == dos[0]
    assert _largo(uno) == pytest.approx(_largo(trazado) * fraccion, rel=1e-6, abs=1e-6)


def _recta():
    a, b = (-14.0, -75.70), (-14.0, -75.69)
    return red_de([Barra('A', gps=a), Barra('B', gps=b)],
                  [Tramo('T', 'A', 'B', 1000.0, trazado=(a, b))])


def test_distancia_minima_a_una_barra():
    """016:RF-20 — más cerca de una barra que la distancia mínima: se conecta en ella sin
    partir; más lejos, se parte."""
    red = _recta()
    cerca = (-13.999, -75.70 + 0.00003)              # a unos 3 m de A a lo largo del tramo
    c = conexion_en(red, red.tramos[0], cerca, 5.0)
    assert not c.parte and c.barra == 'A' and c.fraccion == 0.0
    c = conexion_en(red, red.tramos[0], cerca, 2.0)
    assert c.parte and 0 < c.fraccion < 0.01


def test_sin_distancia_minima_solo_si_coincide():
    """016:RF-67 — sin distancia mínima se parte siempre, salvo en la barra misma."""
    red = _recta()
    assert conexion_en(red, red.tramos[0], (-13.999, -75.70 + 0.00003), None).parte
    c = conexion_en(red, red.tramos[0], (-13.999, -75.68), None)        # más allá de B
    assert not c.parte and c.barra == 'B'


def test_solo_en_la_troncal():
    """016:RF-45, 016:RF-28 — el punto se busca solo en los tramos de la troncal, aunque una
    derivación quede más cerca; sin coordenadas en ninguno, nada."""
    a, b, c = (-14.0, -75.70), (-14.0, -75.69), (-13.995, -75.695)
    red = red_de([Barra('A', gps=a), Barra('B', gps=b), Barra('C', gps=c)],
                 [Tramo('TRONCAL', 'A', 'B', 1000.0, trazado=(a, b)),
                  Tramo('RAMAL', 'B', 'C', 700.0, trazado=(b, c))])
    punto = (-13.996, -75.695)
    assert punto_en_troncal(red, ['TRONCAL', 'RAMAL'], punto).tramo == 'RAMAL'
    assert punto_en_troncal(red, ['TRONCAL'], punto).tramo == 'TRONCAL'
    sin = red_de([Barra('A'), Barra('B')], [Tramo('T', 'A', 'B', 10.0)])
    assert punto_en_troncal(sin, ['T'], punto) is None


def _red_sorteada(rng, pref, centro):
    tramos, barras = [], []
    for k in range(rng.randint(1, 6)):
        tr = _polilinea(rng, centro=centro)
        barras += [Barra(f'{pref}{k}a', gps=tr[0]), Barra(f'{pref}{k}b', gps=tr[-1])]
        tramos.append(Tramo(f'{pref}T{k}', f'{pref}{k}a', f'{pref}{k}b', 100.0, trazado=tr))
    return red_de(barras, tramos)


@pytest.mark.parametrize('semilla', range(15))
def test_extremos_del_enlace(semilla):
    """016:RF-27, 016:RF-28 — el origen es el punto de los candidatos del que recibe más
    cercano a la troncal del que cede, y el destino el de esa troncal más cercano al origen
    (referencia: los dos trazados muestreados)."""
    rng = random.Random(6000 + semilla)
    recibe = _red_sorteada(rng, 'R', ORIGEN)
    cede = _red_sorteada(rng, 'C', (ORIGEN[0] + 0.03, ORIGEN[1] + 0.02))
    ts_r = [t.nombre for t in recibe.tramos]
    ts_c = [t.nombre for t in cede.tramos]
    salida, llegada = extremos_del_enlace(recibe, ts_r, cede, ts_c)
    ref = min(math.hypot(*_metros(p, q))
              for t in recibe.tramos for _, p in _muestras(t.trazado, 30)
              for u in cede.tramos for _, q in _muestras(u.trazado, 30))
    d = math.hypot(*_metros(salida.gps, llegada.gps))
    assert d <= ref + 1e-6 and d == pytest.approx(ref, abs=50.0)
    assert salida.tramo in ts_r and llegada.tramo in ts_c
    assert llegada == punto_en_troncal(cede, ts_c, salida.gps)


def test_el_origen_solo_en_los_candidatos():
    """016:RF-27 — un tramo del que recibe que no es candidato (fuera de límites, RF-26) no
    da el origen, aunque esté más cerca; sin coordenadas, se dice de qué lado."""
    a, b = (-14.0, -75.70), (-14.0, -75.69)
    c, d = (-14.02, -75.70), (-14.02, -75.69)
    recibe = red_de([Barra('A', gps=a), Barra('B', gps=b), Barra('C', gps=c), Barra('D', gps=d)],
                    [Tramo('CERCA', 'A', 'B', 1.0, trazado=(a, b)),
                     Tramo('LEJOS', 'C', 'D', 1.0, trazado=(c, d))])
    e, f = (-13.99, -75.70), (-13.99, -75.69)
    cede = red_de([Barra('E', gps=e), Barra('F', gps=f)], [Tramo('X', 'E', 'F', 1.0, trazado=(e, f))])
    assert extremos_del_enlace(recibe, ['CERCA', 'LEJOS'], cede, ['X'])[0].tramo == 'CERCA'
    assert extremos_del_enlace(recibe, ['LEJOS'], cede, ['X'])[0].tramo == 'LEJOS'
    sin = red_de([Barra('A'), Barra('B')], [Tramo('T', 'A', 'B', 1.0)])
    with pytest.raises(TroncalError, match='el que recibe'):
        extremos_del_enlace(sin, ['T'], cede, ['X'])


def test_enlace_ta225_in111_con_los_txt_reales(txt_dataset, perfil_real):
    """016:RF-27, 016:RF-28 — de la troncal de TA225 a la de IN111 con los trazados GPS
    del TXT: los dos extremos en sus troncales, más cerca que sus barras más próximas."""
    from igea_dgs.geography import build_geography
    from igea_dgs.model import build_feeder_model

    redes, troncales = {}, {}
    for f in ('TA225', 'IN111'):
        m = build_feeder_model(txt_dataset, txt_dataset.resolve_feeder(f), strict=False,
                               include_geography=True)
        g = build_geography(txt_dataset, m, source_crs=perfil_real.crs_origen)
        nodos = {n for ln in m.lines for n in (ln.from_node, ln.to_node)}
        barras = [Barra(n, gps=(g.nodes[n].lat, g.nodes[n].lon) if n in g.nodes else None)
                  for n in nodos]
        tramos = [Tramo(ln.section_id, ln.from_node, ln.to_node, ln.length_m,
                        trazado=tuple((p.lat, p.lon) for p in g.lines[ln.section_id].path)
                        if ln.section_id in g.lines else ())
                  for ln in m.lines]
        redes[f] = red_de(barras, tramos)
        troncales[f] = troncal(redes[f], m.source_node).tramos
    salida, llegada = extremos_del_enlace(redes['TA225'], troncales['TA225'],
                                          redes['IN111'], troncales['IN111'], 5.0)
    assert salida.tramo in troncales['TA225'] and llegada.tramo in troncales['IN111']
    d = math.hypot(*_metros(salida.gps, llegada.gps))

    def gps_troncal(f):
        por = redes[f].por_nombre()
        return [redes[f].barras[x].gps for n in troncales[f] for x in (por[n].desde, por[n].hasta)
                if redes[f].barras[x].gps]
    barras = min(math.hypot(*_metros(a, b)) for a in gps_troncal('TA225') for b in gps_troncal('IN111'))
    assert 0 < d <= barras + 1e-6
