"""Spec 016, T6: la red y la troncal que lee el guion, y partir un tramo en DIgSILENT (doble)."""

from __future__ import annotations

import math
import random

import pytest

import fake_pf
from apoyo import cargar_herramienta
from test_obras_pf_guion import CON, SIN, _activas, _barra, _calibrada, _elm, _linea, _plan

guion = cargar_herramienta('obras_pf.py', 'obras_t6_016', tools_en_path=True)
cargas = cargar_herramienta('cargas_pf.py', 'cargas_t6_016', tools_en_path=True)


def _variacion(app, nombre):
    v = app.carpetas['scheme'].CreateObject('IntScheme', nombre)
    v.NewStage(f'Etapa_{nombre}', 0, 1)
    return v


# --------------------------------------------------------------------------- leer la red
def test_leer_red_con_extremos_largos_trazados_y_estado():
    """016:RF-2, 016:RF-4 — la red del alimentador como la ve el caso activo: cada línea
    con sus dos barras (``bus1`` primero), su longitud en metros y su trazado; un tramo
    fuera de servicio o con un interruptor abierto no está cerrado."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=3, bt=True)
    elm = app.proyecto.GetContents('*.ElmFeeder', 1)[0]
    lineas = {ln.loc_name: ln for ln in elm.GetObjs('ElmLne')}
    lineas['F1_L2'].outserv = 1
    cub = next(c for c in app.proyecto.GetContents('*.StaCubic', 1) if c.obj_id is lineas['F1_L3'])
    sw = cub.CreateObject('StaSwitch', 'SECC')
    sw.on_off = 0
    cabecera = guion.cabecera_de(elm)
    red = cargas.leer_red(elm, cabecera)
    tramos = red.por_nombre()
    assert (tramos['F1_L1'].desde, tramos['F1_L1'].hasta) == ('F1_B0', 'F1_B1')
    assert tramos['F1_L1'].largo_m == pytest.approx(1000.0) and len(tramos['F1_L1'].trazado) == 2
    assert tramos['F1_L1'].cerrado and not tramos['F1_L2'].cerrado and not tramos['F1_L3'].cerrado
    assert red.barras['F1_B1'].gps is not None and red.barras['F1_B1'].kv == 10.0


def test_las_obras_no_ejecutan_combbone_y_leen_en_su_caso():
    """016:RF-2, 016:RF-10 — la troncal de las obras sale de la red leída, sin ``ComBbone``; un
    alimentador con obras solo de «Con proyecto» se lee en «Con proyecto»: un tramo abierto
    solo allí corta lo que queda aguas abajo de la migración."""
    app, alims = _calibrada(random.Random(51), cargas_min=3)
    llamadas = []
    app.ordenes['ComBbone'] = fake_pf.Orden(app, 'BB', clase='ComBbone',
                                            efecto=lambda *_: llamadas.append(1))
    f = alims[0]
    _activas(app, CON)
    v = _variacion(app, 'Operador_CON')
    _linea(app, f'{f}_L2').outserv = 1                       # abierto solo en «Con proyecto»
    app.grabando = None
    _activas(app, SIN)
    v.Deactivate()
    obra = {'clase': 'migracion', 'alimentador': f, 'casos': [CON], 'nodo': f'{f}_B3',
            'kv_destino': 22.9}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]), simular=True)
    assert codigo == 2 and 'camino cerrado' in informe['obras'][0]['error']
    assert llamadas == []
    obra['nodo'] = f'{f}_B1'
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]), simular=True)
    elementos = {e['elemento'] for e in informe['obras'][0]['elementos']}
    assert f'{f}_L2' not in elementos and f'{f}_L1' in elementos      # L1 es la entrada


# --------------------------------------------------------------------------- partir un tramo
def test_partir_un_tramo_en_la_variacion():
    """016:RF-16, 016:RF-17, 016:RF-18, 016:RF-19, 016:RF-22 — la barra nueva lleva el
    nombre y el GPS del punto y la tensión del tramo; cada mitad, su parte del trazado, el
    tipo y las ternas; al desactivar la variación el tramo vuelve a estar entero."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=2)
    ln = next(o for o in app.proyecto.GetContents('*.ElmLne', 1) if o.loc_name == 'F1_L1')
    ln.nlnum = 2
    entero = list(map(tuple, ln.GPScoords))
    v = _variacion(app, 'Enlace')
    barra, copia = cargas.partir_tramo(app, ln, 0.25, 'ENLACE_F1')
    assert barra.loc_name == 'ENLACE_F1' and barra.uknom == 10.0
    (a, b) = entero
    esperado = (a[0] + 0.25 * (b[0] - a[0]), a[1] + 0.25 * (b[1] - a[1]))
    assert (barra.GPSlat, barra.GPSlon) == pytest.approx(esperado)
    assert [tuple(p) for p in ln.GPScoords][0] == a and tuple(ln.GPScoords[-1]) == pytest.approx(esperado)
    assert tuple(copia.GPScoords[0]) == pytest.approx(esperado) and tuple(copia.GPScoords[-1]) == b
    assert (copia.typ_id, copia.nlnum) == (ln.typ_id, 2)
    assert ln.dline + copia.dline == pytest.approx(1.0) and ln.dline == pytest.approx(0.25)
    v.Deactivate()
    assert ln.dline == pytest.approx(1.0)
    assert barra not in app.proyecto.GetContents('*.ElmTerm', 1)


def test_partir_un_tramo_con_el_punto_dado():
    """016:RF-19 — si se da el punto, la barra nueva toma sus coordenadas."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=1)
    ln = app.proyecto.GetContents('*.ElmLne', 1)[0]
    _variacion(app, 'Carga')
    barra, _ = cargas.partir_tramo(app, ln, 0.5, 'P', gps=(-14.1, -75.6))
    assert (barra.GPSlat, barra.GPSlon) == (-14.1, -75.6)


@pytest.mark.parametrize('caso', ['sin_variacion', 'fuera_de_servicio', 'extremo'])
def test_no_se_parte_fuera_de_una_variacion_ni_un_tramo_fuera_de_servicio(caso):
    """016:RF-21, 016:RF-22 — sin una variación grabando, con el tramo fuera de servicio o en
    un extremo no se parte nada: se dice por qué."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=1)
    ln = app.proyecto.GetContents('*.ElmLne', 1)[0]
    if caso != 'sin_variacion':
        _variacion(app, 'Obra')
    if caso == 'fuera_de_servicio':
        ln.outserv = 1
    antes = len(app.proyecto.GetContents('*.ElmTerm', 1))
    with pytest.raises(RuntimeError, match={'sin_variacion': 'grabando',
                                            'fuera_de_servicio': 'fuera de servicio',
                                            'extremo': 'extremo'}[caso]):
        cargas.partir_tramo(app, ln, 1.0 if caso == 'extremo' else 0.5, 'X')
    assert len(app.proyecto.GetContents('*.ElmTerm', 1)) == antes
    assert math.isclose(ln.dline, 1.0)


# --------------------------------------------------------------------------- T7: el enlace
def _mover(app, nombre, lat, lon):
    """Mueve una barra y los extremos de los trazados de sus líneas."""
    barra = next(b for b in app.proyecto.GetContents('*.ElmTerm', 1) if b.loc_name == nombre)
    barra.GPSlat, barra.GPSlon = lat, lon
    for cub in barra.GetContents('*.StaCubic'):
        ln = cub.obj_id
        if ln.GetClassName() == 'ElmLne' and ln.GPScoords:
            ln.GPScoords[-1 if cub.obj_bus else 0] = [lat, lon]


def _dos_alimentadores(semilla):
    """F1 recibe y F2 cede; F2 se acerca a F1 solo en ``F2_B2``, frente al centro de ``F1_L2``."""
    app, alims = _calibrada(random.Random(semilla), n_min=2, cargas_min=3)
    _mover(app, 'F2_B2', -14.003, -75.6985)
    return app, alims


def _enlace(**extra):
    return {'clase': 'enlace', 'alimentador': 'F1', 'cede': 'F2', 'casos': [CON],
            'tipo': {'nombre': 'AAAC_F1', 'clase': 'TypLne'}, **extra}


def _con_tension(app, barras, u=0.90):
    """El flujo deja ``u`` en esas barras: fuera del límite de 0,95 p.u."""
    flujo = app.ldf
    original = flujo.Execute

    def ejecutar():
        rc = original()
        for b in app.proyecto.GetContents('*.ElmTerm', 1):
            if b.loc_name in barras:
                object.__setattr__(b, 'm_u', u)
        return rc
    object.__setattr__(flujo, 'Execute', ejecutar)


def _barras(app, f):
    return {b.loc_name for b in _elm(app, f).GetObjs('ElmTerm')}


@pytest.mark.parametrize('semilla', (61, 62, 63))
def test_enlace_parte_un_tramo_llega_a_una_barra_y_queda_abierto(semilla):
    """016:RF-29, 016:RF-34, 016:RF-35, 016:RF-36, 016:RF-37, 016:RF-38, 016:RF-42, 016:RF-43, 016:RF-62
    — el origen parte el tramo de F1 frente a F2 y el destino es la barra de F2 más cercana;
    la línea va en recta con el trazado de sus extremos y el seccionador abierto del lado de
    F2; nada une los dos alimentadores y el enlace no es troncal; todo solo en «Con
    proyecto»."""
    app, alims = _dos_alimentadores(semilla)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_enlace()]))
    assert codigo == 0, informe
    (fila,) = informe['obras']
    assert fila['flujo'][CON]['converge'] and fila['casos_activos'] == [CON]
    enlace = fila['enlace']
    assert enlace['origen']['parte'] and enlace['origen']['tramo'] == 'F1_L2'
    assert enlace['origen']['fraccion'] == pytest.approx(0.5, abs=1e-3)
    assert not enlace['destino']['parte'] and enlace['destino']['barra_final'] == 'F2_B2'
    # Haversine (016:RF-82): 0,003° de latitud son 333,6 m.
    assert enlace['largo_m'] == pytest.approx(333.6, abs=1.0)

    _activas(app, CON)
    linea = _linea(app, 'Enlace_F1_F2')
    assert linea.dline == pytest.approx(0.3336, abs=1e-3)
    assert linea.typ_id.loc_name == 'AAAC_F1_10kV'          # a la tensión del que recibe (RF-38)
    nueva = enlace['origen']['barra_final']
    assert [tuple(p) for p in linea.GPScoords] == [pytest.approx((-14.0, -75.6985)),
                                                   pytest.approx((-14.003, -75.6985))]
    cub = next(c for c in app.proyecto.GetContents('*.StaCubic', 1)
               if c.obj_id is linea and c.cterm.loc_name == 'F2_B2')
    (secc,) = cub.GetContents('*.StaSwitch')
    assert secc.on_off == 0
    assert _linea(app, 'F1_L2').dline == pytest.approx(0.5)
    assert nueva in _barras(app, 'F1') and not (_barras(app, 'F1') & _barras(app, 'F2'))
    red = cargas.leer_red(_elm(app, 'F1'), guion.cabecera_de(_elm(app, 'F1')))
    assert 'Enlace_F1_F2' not in guion.troncal_de(red, 'F1_B0').tramos

    _activas(app, SIN)
    assert not any(o.loc_name == 'Enlace_F1_F2' for o in app.proyecto.GetContents('*.ElmLne', 1))
    assert _linea(app, 'F1_L2').dline == pytest.approx(1.0) and nueva not in _barras(app, 'F1')


def test_el_origen_solo_donde_la_tension_lo_permite():
    """016:RF-26 — con F1_B2 por debajo del límite, los tramos que tocan esa barra no son
    candidatos: el enlace sale del punto válido más cercano, la barra F1_B1."""
    app, alims = _dos_alimentadores(64)
    _con_tension(app, {'F1_B2'})
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_enlace()]))
    assert codigo == 0, informe
    origen = informe['obras'][0]['enlace']['origen']
    assert origen['tramo'] not in ('F1_L2', 'F1_L3') and origen['barra_final'] == 'F1_B1'


def test_sin_tramos_dentro_de_los_limites_no_se_crea():
    """016:RF-30 — si ninguna barra de la troncal está en tensión, no se crea el enlace y se
    dice la tensión mínima, sin dejar la variación."""
    app, alims = _dos_alimentadores(65)
    _con_tension(app, _barras(app, 'F1'))
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_enlace()]))
    (fila,) = informe['obras']
    assert codigo == 2 and 'ningún tramo de la troncal de F1' in fila['error']
    assert 'tensión mínima 0.9' in fila['error'] and fila['variacion'] == ''
    assert not any(o.loc_name.startswith('Enlace') for o in app.proyecto.GetContents('*.ElmLne', 1))


def test_origen_indicado_fuera_de_limites_se_usa_y_se_avisa():
    """016:RF-31, 016:RF-32 — la barra que indica el operador se usa aunque esté fuera de los
    límites, y el aviso dice su tensión."""
    app, alims = _dos_alimentadores(66)
    _con_tension(app, {'F1_B2'})
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_enlace(origen='F1_B2')]))
    assert codigo == 0, informe
    (fila,) = informe['obras']
    assert fila['enlace']['origen']['barra_final'] == 'F1_B2' and not fila['enlace']['origen']['parte']
    assert any('F1_B2' in a and '0.900 p.u.' in a and 'se usa igual' in a for a in fila['avisos'])


def test_sin_coordenadas_en_el_que_cede_no_se_crea():
    """016:RF-33 — sin coordenadas en la troncal del que cede no hay dónde llegar: se pide
    indicar los dos puntos."""
    app, alims = _dos_alimentadores(67)
    for o in _elm(app, 'F2').GetObjs('ElmTerm'):
        o.GPSlat, o.GPSlon = 0.0, 0.0
    for ln in _elm(app, 'F2').GetObjs('ElmLne'):
        ln.GPScoords = []
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_enlace()]))
    assert codigo == 2 and 'indique los dos puntos' in informe['obras'][0]['error']


def test_enlace_por_la_via_con_el_enrutador_del_perfil(monkeypatch):
    """016:RF-81, 016:RF-82, 016:RF-87 — con enrutador en el perfil, la línea del enlace
    sigue la ruta de la vía (sus vértices en GPScoords) y su largo es el de la ruta con los
    accesos; el informe de la obra dice el largo por la vía, la recta y el servicio."""
    import functools
    import json

    from igea_dgs import vias

    app, alims = _dos_alimentadores(71)
    curva = [(-14.0, -75.6985), (-14.001, -75.6970), (-14.002, -75.6995), (-14.003, -75.6985)]

    def pedir(_url, _t):
        return json.dumps({'code': 'Ok', 'routes': [{'distance': 612.0, 'geometry': {
            'coordinates': [[lon, lat] for lat, lon in curva]}}],
            'waypoints': [{'distance': 1.0}, {'distance': 2.0}]}).encode()

    monkeypatch.setattr(guion, 'datos_perfil', lambda: {'vias': {'servicio': 'osrm', 'url': 'x'}})
    monkeypatch.setattr(guion, 'ruta_por_vias', functools.partial(vias.ruta_por_vias, pedir=pedir))
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_enlace()]))
    assert codigo == 0, informe
    (fila,) = informe['obras']
    assert fila['enlace']['largo_m'] == pytest.approx(615.0)
    assert fila['enlace']['trazado']['por_via'] and fila['enlace']['trazado']['servicio'] == 'osrm'
    assert fila['enlace']['trazado']['recta_m'] == pytest.approx(333.6, abs=1.0)
    _activas(app, CON)
    linea = _linea(app, 'Enlace_F1_F2')
    assert linea.dline == pytest.approx(0.615)
    assert [tuple(p) for p in linea.GPScoords] == [pytest.approx(p) for p in curva]


def test_un_segundo_enlace_entre_los_mismos_no_se_crea():
    """016:RF-40 — con un enlace ya creado entre F1 y F2, otro se rechaza con su variación."""
    app, alims = _dos_alimentadores(68)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_enlace()]))
    assert codigo == 0, informe
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_enlace()]))
    assert codigo == 2 and 'Obra_enlace_F1_F2' in informe['obras'][0]['error']


# --------------------------------------------------------------------------- T8: la migración
def _migracion(f, nodo, destino=22.9):
    return {'clase': 'migracion', 'alimentador': f, 'casos': [CON], 'nodo': nodo,
            'kv_destino': destino}


def _uknom(app, nombre):
    return next(b.uknom for b in app.proyecto.GetContents('*.ElmTerm', 1) if b.loc_name == nombre)


def _trafo(app, nombre):
    return next(t for t in app.proyecto.GetContents('*.ElmTr2', 1) if t.loc_name == nombre)


@pytest.mark.parametrize('semilla', (71, 72, 73))
def test_migracion_de_lo_que_queda_aguas_abajo_del_nodo(semilla):
    """016:RF-52, 016:RF-54, 016:RF-55, 016:RF-56, 016:RF-57, 016:RF-58, 016:RF-60 — desde
    ``F1_B2`` pasan a 22,9 kV sus barras, las líneas y las SED de aguas abajo, con copias de
    tipo; el tramo que entra al nodo se abre; lo de aguas arriba, el otro alimentador y
    «Sin proyecto» no cambian."""
    app, alims = _calibrada(random.Random(semilla), n_min=2, cargas_min=3)
    n = len(_elm(app, 'F1').GetObjs('ElmLne'))
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_migracion('F1', 'F1_B2')]))
    assert codigo == 0, informe
    (fila,) = informe['obras']
    assert fila['flujo'][CON]['converge'] and fila['casos_activos'] == [CON]
    _activas(app, CON)
    for i in range(n + 1):
        assert _uknom(app, f'F1_B{i}') == (22.9 if i >= 2 else 10.0), i
    for i in range(1, n + 1):
        ln = _linea(app, f'F1_L{i}')
        assert ln.typ_id.loc_name == ('AAAC_F1_22_9kV' if i >= 3 else 'AAAC_F1'), i
        assert ln.outserv == (1 if i == 2 else 0), i
        tr = _trafo(app, f'TR_F1_S{i}')
        assert tr.typ_id.loc_name == ('TR100_F1_22_9kV' if i >= 2 else 'TR100_F1'), i
    assert _trafo(app, 'TR_F1_S2').typ_id.utrn_h == 22.9
    assert {b.uknom for b in _elm(app, 'F2').GetObjs('ElmTerm')} == {10.0}
    _activas(app, SIN)
    assert {b.uknom for b in _elm(app, 'F1').GetObjs('ElmTerm')} == {10.0}
    assert {ln.outserv for ln in _elm(app, 'F1').GetObjs('ElmLne')} == {0}


def test_enlace_y_migracion_en_la_misma_tanda():
    """016:RF-54, 016:RF-55, 016:RF-56 — el enlace parte un tramo de la parte que pasa; la
    migración, que se calcula al construirla, migra también la mitad nueva y la barra del
    enlace, y lo dice."""
    app, alims = _calibrada(random.Random(74), n_min=2, cargas_min=3)
    _mover(app, 'F1_B2', -14.007, -75.6985)              # F1 se acerca al centro de F2_L2
    obras = [_enlace(), _migracion('F2', 'F2_B1')]
    informe, codigo = guion.aplicar(app, _plan(alims, obras=obras))
    assert codigo == 0, informe
    enlace, migracion = informe['obras']
    assert enlace['enlace']['destino']['tramo'] == 'F2_L2' and enlace['enlace']['destino']['parte']
    barra_enlace = enlace['enlace']['destino']['barra_final']
    assert any('F2_L2(1)' in a and 'no estaban en la simulación' in a for a in migracion['avisos'])
    _activas(app, CON)
    assert _uknom(app, barra_enlace) == 22.9
    assert _linea(app, 'F2_L2(1)').typ_id.loc_name == 'AAAC_F2_22_9kV'
    assert _linea(app, 'F2_L2').typ_id.loc_name == 'AAAC_F2_22_9kV'
    assert _linea(app, 'F2_L1').outserv == 1


def _anillo(app, f, desde, hasta, nombre):
    """Un tramo que cierra un anillo entre dos barras del alimentador ``f``."""
    red = _barra(app, desde).GetParent()
    ln = red.CreateObject('ElmLne', nombre)
    ln.typ_id, ln.nlnum, ln.outserv, ln.dline = _linea(app, f'{f}_L1').typ_id, 1, 0, 0.3
    for lado, b in ((0, _barra(app, desde)), (1, _barra(app, hasta))):
        cub = b.CreateObject('StaCubic', f'c{lado}_{nombre}')
        cub.obj_id, cub.obj_bus = ln, lado
    _elm(app, f)._objs.append(ln)
    return ln


def test_enlace_entre_tensiones_distintas_y_migracion_que_lo_cierra():
    """016:RF-76, 016:RF-80 — el enlace entre 22,9 kV (F1) y 10 kV (F2) se crea fuera de
    servicio y se dice; la migración de F2 a 22,9 kV cambia también el tramo que cierra un
    anillo en la parte que pasa, pone el enlace en servicio y cierra su seccionador."""
    app, alims = _calibrada(random.Random(75), n_min=2, cargas_min=4)
    _mover(app, 'F1_B2', -14.007, -75.6985)
    for b in _elm(app, 'F1').GetObjs('ElmTerm'):
        b.uknom = 22.9
    _anillo(app, 'F2', 'F2_B2', 'F2_B4', 'F2_ANILLO')
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_enlace(tipo={
        'nombre': 'AAAC_F1', 'clase': 'TypLne'})]))
    (enlace,) = informe['obras']
    assert any('fuera de servicio' in a for a in enlace['avisos']), enlace
    _activas(app, CON)
    linea = _linea(app, 'Enlace_F1_F2')
    assert linea.outserv == 1

    nodo = enlace['enlace']['destino']['barra_final']
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_migracion('F2', nodo)]))
    (migra,) = informe['obras']
    assert migra['variacion'], (migra.get('error'), migra.get('avisos'))
    _activas(app, CON)
    assert _linea(app, 'Enlace_F1_F2').outserv == 0
    cubiculos = [c for c in app.proyecto.GetContents('*.StaCubic', 1) if c.obj_id is linea]
    assert [s.on_off for c in cubiculos for s in c.GetContents('*.StaSwitch')] == [1]
    assert any('cerrado' in a for a in migra['avisos'])
    assert _uknom(app, 'F2_B2') == 22.9 and _uknom(app, 'F2_B4') == 22.9
    assert _linea(app, 'F2_ANILLO').typ_id.loc_name.endswith('22_9kV')


def test_obra_de_con_proyecto_con_las_cargas_nuevas_apartadas():
    """016:RF-75 — la obra de «Con proyecto» se graba con las variaciones de cargas nuevas
    apartadas y estas vuelven a quedar activas; la obra queda en su variación."""
    app, alims = _calibrada(random.Random(76))
    _activas(app, CON)
    carpeta = app.carpetas['scheme']
    cargas_nuevas = []
    for k in range(3):
        v = carpeta.CreateObject('IntScheme', f'Carga_N{k}_F1_20261016_000000')
        v.NewStage(f'Etapa_N{k}', 1000 + k, 1)
        cargas_nuevas.append(v.loc_name)
    obra = {'clase': 'terna', 'alimentador': 'F1', 'casos': [CON], 'tramos': ['F1_L1']}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 0, informe
    (fila,) = informe['obras']
    activas = _activas(app, CON)
    assert set(cargas_nuevas) <= activas and fila['variacion'] in activas
    assert _linea(app, 'F1_L1').nlnum == 2


# --------------------------------------------------------------------------- T9: orden de los casos
casos_t9 = cargar_herramienta('casos_pf.py', 'casos_t9_016', tools_en_path=True)


def test_sin_proyecto_pasa_a_con_proyecto_que_ya_existe():
    """016:RF-11 — una obra de «Sin proyecto» queda activa también en «Con proyecto»."""
    app, alims = _calibrada(random.Random(81))
    obra = {'clase': 'terna', 'alimentador': 'F1', 'casos': [SIN, CON], 'tramos': ['F1_L1']}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 0, informe
    (fila,) = informe['obras']
    assert fila['casos_activos'] == [SIN, CON]
    assert fila['variacion'] in _activas(app, SIN) and fila['variacion'] in _activas(app, CON)


def test_con_proyecto_se_crea_despues_de_las_obras_de_sin_proyecto():
    """016:RF-11, 016:RF-12, 016:RF-14 — sin «Con proyecto», primero se aplican las obras de
    «Sin proyecto», luego se crea «Con proyecto» como su copia (con esas obras activas y su
    flujo) y después van las de solo «Con proyecto», aunque llegaran antes en la lista."""
    app, alims = _calibrada(random.Random(82), n_min=2, cargas_min=3)
    casos_t9.casos_del_proyecto(app)['con'].Delete()
    assert 'con' not in casos_t9.casos_del_proyecto(app)
    obras = [_migracion('F2', 'F2_B2'),
             {'clase': 'terna', 'alimentador': 'F1', 'casos': [SIN, CON], 'tramos': ['F1_L1']}]
    informe, codigo = guion.aplicar(app, _plan(alims, obras=obras))
    assert codigo == 0, informe
    migracion, terna = informe['obras']
    assert migracion['clase'] == 'migracion' and terna['clase'] == 'terna'
    assert any('se creó como copia' in a for a in informe['avisos'])
    assert 'con' in casos_t9.casos_del_proyecto(app)
    assert terna['casos_activos'] == [SIN, CON] and terna['flujo'][CON]['converge']
    assert migracion['casos_activos'] == [CON]
    en_sin, en_con = _activas(app, SIN), _activas(app, CON)
    assert terna['variacion'] in en_sin and terna['variacion'] in en_con
    assert migracion['variacion'] in en_con and migracion['variacion'] not in en_sin
    _activas(app, CON)
    assert _linea(app, 'F1_L1').nlnum == 2 and _uknom(app, 'F2_B3') == 22.9
    _activas(app, SIN)
    assert _linea(app, 'F1_L1').nlnum == 2 and _uknom(app, 'F2_B3') == 10.0


class _Nuevo:
    """Como la API de PF 2024: cada acceso a un objeto devuelve un envoltorio de Python nuevo,
    así que ``id()`` e ``is`` no reconocen el mismo objeto (copia de IN111_TA225, 2026-10-15)."""

    def __init__(self, o):
        object.__setattr__(self, '_o', o)

    @staticmethod
    def _envolver(v):
        if isinstance(v, fake_pf.Obj):
            return _Nuevo(v)
        if isinstance(v, list):
            return [_Nuevo._envolver(x) for x in v]
        return v

    def __getattr__(self, nombre):
        v = getattr(self._o, nombre)
        if callable(v):
            return lambda *a, **k: _Nuevo._envolver(v(*a, **k))
        return _Nuevo._envolver(v)


def test_leer_red_con_objetos_nuevos_en_cada_acceso():
    """016:RF-2 — la red se lee igual aunque cada acceso dé un objeto de Python nuevo: los
    extremos se reconocen por el nombre completo, no por ``id()``."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=3, bt=True)
    elm = app.proyecto.GetContents('*.ElmFeeder', 1)[0]
    directa = cargas.leer_red(elm, cargas.cabecera_de(elm))
    envuelta = cargas.leer_red(_Nuevo(elm), cargas.cabecera_de(_Nuevo(elm)))
    assert len(envuelta.tramos) == len(directa.tramos) == 3
    assert {(t.nombre, t.desde, t.hasta) for t in envuelta.tramos} == {
        (t.nombre, t.desde, t.hasta) for t in directa.tramos}
