"""Spec 042, T4: la obra «SET nueva» en DIgSILENT (doble ``fake_pf``).

El caso real es la SET Copara para NA203 + NA205 (2026-10-31): transformador del módulo PIT,
red externa con los datos de la de cabecera, y las ramas que pasan a ella, cada una con su
alimentador nuevo y su tramo de entrada abierto, solo en «Con proyecto».
"""
from __future__ import annotations

import random

import pytest

from apoyo import cargar_herramienta
from convertersmartgrid.obras_pf import ObrasError, validar_obra
from test_obras_pf_guion import CON, SIN, _activas, _barra, _calibrada, _linea, _plan

guion = cargar_herramienta('obras_pf.py', 'obras_042', tools_en_path=True)
SEMILLAS = [11, 23, 57]
#: Lo que el libro CAPEX no trae del transformador: la uk de IEC 60076-5 y las tomas (042:RF-7).
PERFIL = {'planificacion': {'transformador_set': {
    'uk_pct_hasta_mva': [[6.3, 7.0], [25, 8.0], [40, 10.0]], 'toma_paso_pct': 1.25, 'tomas': 8}}}


@pytest.fixture()
def perfil(monkeypatch):
    monkeypatch.setattr(guion, 'datos_perfil', lambda: PERFIL)


def _obra(**extra):
    return {'clase': 'set_nueva', 'alimentador': 'F1', 'casos': [CON], 'destino': '-14.0005, -75.6995',
            'ramas': ['F1/F1_B2', 'F2/F2_B2'], 'mva': 25, 'kv_alta': 60, **extra}


def _con_red_externa(app):
    cabecera = _barra(app, 'F1_B0')
    red = cabecera.GetParent().CreateObject('ElmXnet', 'Red_F1')
    red.usetp, red.snss, red.rntxn = 1.02, 250.0, 0.1
    cub = cabecera.CreateObject('StaCubic', 'c_Red_F1')
    cub.obj_id = red
    app.escrituras.clear()
    app.creados.clear()
    return red


def test_la_obra_set_nueva_se_valida():
    """042:RF-5, 042:RF-6, 042:RF-11 — punto «lat, lon», ramas ALIMENTADOR/NODO, potencia y tensión
    de alta; solo en «Con proyecto»."""
    o = validar_obra(_obra())
    assert o.ramas == ('F1/F1_B2', 'F2/F2_B2') and o.mva == 25 and o.kv_alta == 60
    with pytest.raises(ObrasError, match='latitud'):
        validar_obra(_obra(destino='cerca'))
    with pytest.raises(ObrasError, match='ALIMENTADOR/NODO'):
        validar_obra(_obra(ramas=['F1']))
    with pytest.raises(ObrasError):
        validar_obra(_obra(casos=[SIN]))


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_la_set_nueva_se_crea_solo_en_con_proyecto(semilla, perfil):
    """042:RF-5, 042:RF-6, 042:RF-7, 042:RF-10, 042:RF-11 — barras de 60 kV y de media, red externa
    con los datos de la de cabecera, transformador de 25 MVA con la uk de la norma (8 %), una
    línea y un alimentador nuevo por rama y su tramo de entrada abierto; nada en «Sin proyecto»."""
    app, alims = _calibrada(random.Random(semilla), n_min=2, cargas_min=3)
    origen = _con_red_externa(app)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_obra()]))
    assert codigo == 0, informe
    (fila,) = informe['obras']
    assert fila['casos_activos'] == [CON], fila
    s = fila['set_nueva']
    assert s['uk_pct'] == pytest.approx(8.0) and s['copiado_de'] == origen.loc_name
    assert {'usetp', 'snss', 'rntxn'} <= set(s['atributos_copiados'])
    nuevos = {(x['alimentador'], x['nodo'], x['entrada']) for x in s['alimentadores_nuevos']}
    assert nuevos == {('F1', 'F1_B2', 'F1_L2'), ('F2', 'F2_B2', 'F2_L2')}
    assert s['intentos'] and all(x['largo_m'] > 0 for x in s['alimentadores_nuevos'])

    _activas(app, CON)
    assert _barra(app, 'SET_NUEVA_AT').uknom == 60.0
    tr = next(o for o in app.proyecto.GetContents('*.ElmTr2', 1) if o.loc_name == 'TR_SET_NUEVA')
    assert tr.typ_id.strn == 25.0 and tr.typ_id.utrn_h == 60.0
    red = next(o for o in app.proyecto.GetContents('*.ElmXnet', 1) if o.loc_name == 'Red_SET_NUEVA')
    assert (red.usetp, red.snss, red.bustp) == (1.02, 250.0, 'SL')
    assert _linea(app, 'F1_L2').outserv == 1 and _linea(app, 'F2_L2').outserv == 1
    assert {f['feeder'] for f in s['alimentadores_nuevos']} <= {
        o.loc_name for o in app.proyecto.GetContents('*.ElmFeeder', 1)}

    _activas(app, SIN)
    assert not any(b.loc_name == 'SET_NUEVA_AT' for b in app.proyecto.GetContents('*.ElmTerm', 1))
    assert int(getattr(_linea(app, 'F1_L2'), 'outserv', 0) or 0) == 0


def test_set_nueva_regula_la_media_y_queda_en_el_mejor_punto(perfil):
    """042:RF-16, 042:RF-10 — el transformador regula con el cambiador a la consigna de la red
    externa de cabecera (1,02) y el informe da la toma, la consigna y un punto que se probó."""
    app, alims = _calibrada(random.Random(31), n_min=2, cargas_min=3)
    _con_red_externa(app)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_obra()]))
    assert codigo == 0, informe
    s = informe['obras'][0]['set_nueva']
    assert s['consigna_pu'] == pytest.approx(1.02) and s['regula'].get('ntrcn') == 1
    assert (s['lat'], s['lon']) in {(x['lat'], x['lon']) for x in s['intentos']}
    assert all('toma' in x for x in s['intentos'])
    _activas(app, CON)
    tr = next(o for o in app.proyecto.GetContents('*.ElmTr2', 1) if o.loc_name == 'TR_SET_NUEVA')
    assert tr.ntrcn == 1 and tr.usetp == pytest.approx(1.02) and tr.nntap == s['toma']


def test_set_nueva_con_transformadores_en_paralelo(perfil):
    """042:RF-14 — la obra con dos unidades crea un ElmTr2 con ntnum = 2, cada uno con la uk de su
    potencia; sin el dato, uno; cero no es un número de unidades."""
    assert validar_obra(_obra()).unidades is None
    assert validar_obra(_obra(unidades=2)).unidades == 2
    with pytest.raises(ObrasError, match='entero positivo'):
        validar_obra(_obra(unidades=0))
    app, alims = _calibrada(random.Random(21), n_min=2, cargas_min=3)
    _con_red_externa(app)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_obra(unidades=2)]))
    assert codigo == 0, informe
    _activas(app, CON)
    tr = next(o for o in app.proyecto.GetContents('*.ElmTr2', 1) if o.loc_name == 'TR_SET_NUEVA')
    assert tr.ntnum == 2 and tr.typ_id.strn == 25.0 and tr.typ_id.uktr == pytest.approx(8.0)


def test_sin_red_externa_en_la_cabecera_se_dice(perfil):
    """042:RF-5 — sin red externa en la cabecera no se sabe con qué alimentar la SET nueva."""
    app, alims = _calibrada(random.Random(5), n_min=2, cargas_min=3)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_obra()]))
    assert codigo == 2 and 'red externa' in informe['obras'][0]['error']


def test_sin_la_uk_en_el_perfil_no_se_supone():
    """042:RF-8 — sin la tabla de uk del perfil, la SET nueva no se crea y se dice qué falta."""
    app, alims = _calibrada(random.Random(7), n_min=2, cargas_min=3)
    _con_red_externa(app)
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_obra()]))
    assert codigo == 2 and 'uk_pct_hasta_mva' in informe['obras'][0]['error']


def test_apartar_variaciones_por_nombre():
    """042:RF-2 — la escalera carga a carga aparta, además de las de unos alimentadores, las
    variaciones de carga nueva que se le nombran, y solo esas."""
    app, alims = _calibrada(random.Random(3), n_min=2, cargas_min=3)
    _activas(app, CON)
    v1 = app.carpetas['scheme'].CreateObject('IntScheme', 'Carga_A_F1_1')
    v1.NewStage('E1', 0, 1)
    v2 = app.carpetas['scheme'].CreateObject('IntScheme', 'Carga_B_F1_1')
    v2.NewStage('E2', 0, 1)
    app.grabando = None
    apartadas = guion._apartar_cargas_de(app, [], ['Carga_A_F1_1'])
    assert [v.loc_name for v in apartadas] == ['Carga_A_F1_1']
    activas = {v.loc_name for v in app.GetActiveNetworkVariations()}
    assert 'Carga_B_F1_1' in activas and 'Carga_A_F1_1' not in activas


def test_datos_de_la_red_para_la_set_nueva():
    """042:RF-6, 042:RF-7, 042:RF-9 — en «Con proyecto», por alimentador: cabecera, barras con su
    GPS, tramos, y cada carga en la barra de media de su SED (la de alta de su transformador)."""
    app, alims = _calibrada(random.Random(9), n_min=2, cargas_min=3)
    informe, codigo = guion.datos_set_nueva(app, _plan(alims))
    assert codigo == 0, informe
    for f in alims:
        d = informe['alimentadores'][f]
        assert d['cabecera'] == f'{f}_B0' and d['kv'] == 10.0
        assert all(b['gps'] for b in d['barras'] if b['nombre'].startswith(f'{f}_B'))
        assert {t['nombre'] for t in d['tramos']} >= {f'{f}_L1', f'{f}_L2'}
        por_carga = {c['nombre']: c['barra'] for c in d['cargas']}
        assert por_carga[f'{f}_S1'] == f'{f}_B1' and all(c['kw'] > 0 for c in d['cargas'])


def test_set_nueva_halla_la_barra_de_media_de_una_carga_apartada():
    """042:RF-6 — las cargas que pasan a la SET nueva son las que la escalera apartó y no están
    activas en «Con proyecto»: su barra de media sale de la barra que dio la escalera. Por su
    nombre, en NA203 + NA205 (2026-10-31) 29 de 32 quedaban fuera de la SET nueva."""
    app, alims = _calibrada(random.Random(17), n_min=2, cargas_min=3)
    informe, codigo = guion.datos_set_nueva(app, _plan(alims, barras={'F1': ['F1_S2_BT']}))
    assert codigo == 0, informe
    assert informe['alimentadores']['F1']['media'] == {'F1_S2_BT': 'F1_B2'}


def test_la_escalera_mide_la_barra_de_media_de_una_ampliacion():
    """042:RF-2 — una ampliación (040:RF-4) cuelga de la barra de baja de su SED; la escalera la
    mide en la de media (025:RF-50). Con la de baja, en NA203 + NA205 (2026-10-31) todas las
    variantes salían «la carga nueva en SE50150_BT queda a ? p.u.»."""
    app, alims = _calibrada(random.Random(13), n_min=2, cargas_min=3)
    plan = _plan(alims, barras={'F1': ['F1_S2_BT']}, tension_min_pu=0.94)
    informe, codigo = guion.datos_escalera(app, plan)
    assert codigo == 0, informe
    d = informe['alimentadores']['F1']
    assert d['media'] == {'F1_S2_BT': 'F1_B2'}
    assert 'F1_B2' in d['existen'] and 'F1_B2' in d['indices']


def test_la_set_nueva_lleva_una_barra_y_un_transformador_por_tension(perfil):
    """042:RF-20 — Pisco: una rama de 10 kV en la barra de 22,9 kV; cada tensión con su barra y su transformador."""
    app, alims = _calibrada(random.Random(SEMILLAS[0]), n_min=2, cargas_min=3)
    _con_red_externa(app)
    otra_kv = 33.0 if round(_barra(app, 'F1_B0').uknom, 1) != 33.0 else 13.2
    _barra(app, 'F2_B2').uknom = otra_kv
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[_obra()]))
    assert codigo == 0, informe
    s = informe['obras'][0]['set_nueva']
    assert otra_kv in {round(n['kv'], 1) for n in s['niveles']} and len(s['niveles']) == 2
    otra = next(n for n in s['niveles'] if round(n['kv'], 1) == otra_kv)
    _activas(app, CON)
    tr = next(o for o in app.proyecto.GetContents('*.ElmTr2', 1) if o.loc_name == otra['transformador'])
    assert tr.typ_id.utrn_l == otra_kv and tr.typ_id.utrn_h == 60.0 and tr.typ_id.strn == 25.0


def test_el_alimentador_expreso_sale_de_la_set_y_abre_la_entrada(perfil):
    """042:RF-22 — la zona que no justifica SET: una línea desde la cabecera hasta el nodo, su entrada abierta."""
    app, alims = _calibrada(random.Random(SEMILLAS[0]), n_min=2, cargas_min=3)
    obra = {'clase': 'expreso', 'alimentador': 'F1', 'casos': [CON], 'ramas': ['F1/F1_B2']}
    informe, codigo = guion.aplicar(app, _plan(alims, obras=[obra]))
    assert codigo == 0, informe
    (x,) = informe['obras'][0]['expreso']['alimentadores_nuevos']
    assert (x['alimentador'], x['nodo'], x['entrada'], x['desde']) == ('F1', 'F1_B2', 'F1_L2', 'F1_B0')
    _activas(app, CON)
    assert _linea(app, 'F1_L2').outserv == 1
    assert any(o.loc_name == x['linea'] for o in app.proyecto.GetContents('*.ElmLne', 1))
    _activas(app, SIN)
    assert int(getattr(_linea(app, 'F1_L2'), 'outserv', 0) or 0) == 0


def test_el_plan_completo_se_mide_con_todas_las_obras_juntas(perfil):
    """042:RF-23 — dos expresos creados y un solo flujo del plan: si converge, quedan los dos activos en «Con proyecto»."""
    app, alims = _calibrada(random.Random(SEMILLAS[0]), n_min=2, cargas_min=3)
    obras = [{'clase': 'expreso', 'alimentador': 'F1', 'casos': [CON], 'ramas': ['F1/F1_B2']},
             {'clase': 'expreso', 'alimentador': 'F2', 'casos': [CON], 'ramas': ['F2/F2_B2']}]
    informe, codigo = guion.aplicar(app, {**_plan(alims, obras=obras), 'en_conjunto': True})
    assert codigo == 0, informe
    assert informe['plan_completo']['obras'] == 2 and informe['plan_completo']['converge'] is True
    assert all(f['casos_activos'] == [CON] and f['flujo'][CON]['en_conjunto'] for f in informe['obras'])


def test_reponer_cargas_activa_solo_las_pedidas():
    """042:RF-32 — las variaciones pedidas y apagadas se activan en «Con proyecto»; las demás no se tocan."""
    from types import SimpleNamespace as N

    guion = cargar_herramienta('obras_pf.py', 'obras_rf32', tools_en_path=True)
    activas = []

    def variacion(nombre):
        return N(loc_name=nombre, Activate=lambda: activas.append(v[nombre]))

    v = {n: variacion(n) for n in ('Carga_A', 'Carga_B', 'Otra')}
    activas.append(v['Carga_B'])
    caso = N(Activate=lambda: None)
    app = N(GetActiveStudyCase=lambda: caso, GetActiveNetworkVariations=lambda: list(activas),
            GetProjectFolder=lambda _c: N(GetContents=lambda *_a: list(v.values())))
    guion.activar_proyecto = lambda *_a: object()
    guion.casos_del_proyecto = lambda *_a: {'con': caso}
    informe, codigo = guion.reponer_cargas(app, {'project': 'P', 'variaciones': ['Carga_A', 'Carga_B']})
    assert codigo == 0 and informe['repuestas'] == ['Carga_A'] and not informe['avisos']
    assert v['Otra'] not in activas


def test_el_tipo_de_regulador_se_crea_activando_la_biblioteca(monkeypatch):
    """042:RF-34 — sin activar, CreateObject da None; se activa la biblioteca y se crea, y no se repite el que hay."""
    from types import SimpleNamespace as N

    from convertersmartgrid.catalogo_reguladores import unidades_para

    guion = cargar_herramienta('obras_pf.py', 'obras_rf34', tools_en_path=True)
    creados = []

    class Equip:
        def __init__(self, deja):
            self.deja = deja

        def CreateObject(self, _clase, nombre):
            if not self.deja:
                return None
            o = N(loc_name=nombre, Delete=lambda: None)
            creados.append(o)
            return o

        def GetContents(self, *_a):
            return list(creados)

    bloqueada, abierta = Equip(False), Equip(True)
    activada = []
    proyecto = N(Activate=lambda: activada.append(True))
    monkeypatch.setattr(guion, '_proyecto_biblioteca', lambda *_a: (proyecto, bloqueada))
    monkeypatch.setattr(guion, '_iguales', lambda *_a: True)
    informe, codigo = guion.crear_tipos_regulador(N(GetProjectFolder=lambda *_a: abierta), {'tensiones_kv': [22.9]})
    assert codigo == 0 and activada and len(informe['creados']) == len(unidades_para(22.9))


def test_cada_obra_aplicada_queda_georreferenciada(monkeypatch):
    """042:RF-36 — de lo que grabó la etapa: el banco en su barra, el tramo en sus dos extremos, con UTM del perfil."""
    from types import SimpleNamespace as N

    guion = cargar_herramienta('obras_pf.py', 'obras_rf36', tools_en_path=True)

    def elemento(clase, nombre, **k):
        return N(GetClassName=lambda: clase, loc_name=nombre, **k)

    a, b = elemento('ElmTerm', 'A', GPSlat=-13.7, GPSlon=-76.1), elemento('ElmTerm', 'B', GPSlat=-13.8, GPSlon=-76.2)
    banco = elemento('ElmShnt', 'Banco', bus1=N(cterm=a))
    linea = elemento('ElmLne', 'L1', bus1=N(cterm=a), bus2=N(cterm=b))
    etapa = N(GetContents=lambda *_a: [elemento('ElmShnt', 'Banco'), elemento('ElmLne', 'L1'), elemento('StaCubic', 'C')])
    variacion = N(loc_name='Obra_1', GetContents=lambda *_a: [etapa])
    vivos = {'ElmShnt': [banco], 'ElmLne': [linea]}
    app = N(GetCalcRelevantObjects=lambda patron: vivos.get(patron[2:], []),
            GetProjectFolder=lambda _c: N(GetContents=lambda *_a: [variacion]))
    monkeypatch.setattr(guion, 'datos_perfil', lambda: {'crs_origen': 'EPSG:32718'})
    monkeypatch.setattr(guion, 'gps_de', lambda t: (t.GPSlat, t.GPSlon))
    filas = [{'variacion': 'Obra_1'}, {'variacion': None}]
    guion.georreferenciar_obras(app, filas)
    sitio = {u['elemento']: u['puntos'] for u in filas[0]['ubicacion']}
    assert [p['barra'] for p in sitio['Banco']] == ['A'] and [p['barra'] for p in sitio['L1']] == ['A', 'B']
    assert sitio['Banco'][0]['crs'] == 'EPSG:32718' and sitio['Banco'][0]['este'] > 0 and 'ubicacion' not in filas[1]


def test_los_puentes_de_la_red():
    """042:RF-44, 042:RF-45 — acopladores cerrados y equipos en servicio unen dos barras; el abierto o fuera de servicio, no."""
    from pathlib import Path
    from types import SimpleNamespace as N

    guion = cargar_herramienta('obras_pf.py', 'obras_rf44', tools_en_path=True)

    def barra(n):
        return N(cterm=N(loc_name=n))

    objetos = {'ElmCoup': [N(loc_name='cerrado', on_off=1, outserv=0, bus1=barra('A'), bus2=barra('B')),
                           N(loc_name='abierto', on_off=0, outserv=0, bus1=barra('B'), bus2=barra('C')),
                           N(loc_name='fuera', on_off=1, outserv=1, bus1=barra('C'), bus2=barra('D'))],
               'ElmVoltreg': [N(loc_name='reg', outserv=0, bus1=barra('D'), bus2=barra('E'))],
               'ElmTr2': [N(loc_name='tr', outserv=0, bushv=barra('E'), buslv=barra('F'))]}
    app = N(GetCalcRelevantObjects=lambda patron: objetos.get(patron[2:], []))
    puentes = guion.puentes_de_la_red(app)
    assert {p['nombre'] for p in puentes} == {'cerrado', 'reg', 'tr'} and all(p['puente'] and p['largo_m'] == 0.0 for p in puentes)
    assert next(p for p in puentes if p['nombre'] == 'tr')['hasta'] == 'F'
    fuente = (Path(__file__).resolve().parents[1] / 'tools' / 'obras_pf.py').read_text(encoding='utf-8')
    assert 'por cercanía GPS (042:RF-45)' in fuente


def test_el_tipo_del_proyecto_biblioteca_se_encuentra_por_el_nombre_pedido():
    """042:RF-46 — Pisco: la biblioteca conservaba su nombre anterior y el regulador nunca encontraba su tipo."""
    from types import SimpleNamespace as N

    guion = cargar_herramienta('obras_pf.py', 'obras_rf46', tools_en_path=True)
    tipo = N(loc_name='VR32_10kV_50A', GetClassName=lambda: 'TypVoltreg')
    carpeta = N(GetContents=lambda *_a: [tipo])
    otro = N(loc_name='IGEA_Biblioteca_tipos', GetContents=lambda *_a: [])
    vacia = N(GetContents=lambda *_a: [])
    app = N(GetLocalLibrary=lambda _c: vacia, GetGlobalLibrary=lambda _c: vacia)
    guion.biblioteca_de_otro = lambda _p: carpeta
    guion.datos_tipo = lambda _o: {}
    tipos = guion.leer_tipos(app, ['TypVoltreg'], otro, 'CSG_Biblioteca_tipos')
    assert [(t['nombre'], t['proyecto']) for t in tipos] == [('VR32_10kV_50A', 'CSG_Biblioteca_tipos')]
    assert guion.leer_tipos(app, ['TypVoltreg'], otro)[0]['proyecto'] == 'IGEA_Biblioteca_tipos'
