"""Spec 011, T6 a T8: ``tools/estudios_pf.py``, un estudio en un caso y los guiones
del operador, contra ``fake_pf``.

El doble resuelve el flujo con pérdidas cuadráticas, escala las cargas escalables si el
escalado por alimentador queda encendido, y sus órdenes imitan lo que haría DIgSILENT
(abrir un interruptor, crear una variación, escribir en la ventana de salida). La prueba
real la hace el usuario (T19).
"""
from __future__ import annotations

import json
import random
import sys
import types
import copy

import pytest

import fake_pf
from apoyo import cargar_herramienta, contexto_nativo

casos_pf = cargar_herramienta('casos_pf.py', 'casos_t6', tools_en_path=True)
guion = cargar_herramienta('estudios_pf.py', 'estudios_t6', tools_en_path=True)

SEMILLAS = (2, 19, 31, 77)
AJUSTE = 'Ajuste_{f}_20261011_090000'


def _variacion(app, nombre):
    v = app.carpetas['scheme'].CreateObject('IntScheme', nombre)
    v.NewStage(f'Etapa_{nombre}', 0, 1)
    app.grabando = None
    return v


def _red(rng=None, *, escenario=False):
    """Proyecto calibrado con los tres casos; alimentadores sorteados."""
    rng = rng or random.Random(0)
    alims = tuple(f'F{i}' for i in range(1, rng.randint(2, 4) + 1))
    app = fake_pf.proyecto(alimentadores=alims, cargas_por_alim=rng.randint(2, 5), bt=True,
                           flujo=True, escenario=escenario)
    ajustes = [{'feeder': f, 'variacion': _variacion(app, AJUSTE.format(f=f)).loc_name,
                'cuadrado': True} for f in alims]
    base = {'variaciones': [a['variacion'] for a in ajustes], 'feeders': list(alims),
            'ajustes': ajustes, 'excluidos': []}
    informe, codigo = casos_pf.preparar(app, {'project': 'P', 'feeders': list(alims), 'base': base})
    assert codigo == 0, informe
    app.escrituras.clear()
    return app, list(alims)


def _plan(feeders, estudio='flujo', caso='sin', **extra):
    return {'project': 'P', 'feeders': feeders, 'estudio': estudio, 'caso': caso,
            'stamp': '20261011_120000',
            'native_action_context': contexto_nativo('P', feeders, 'estudios'), **extra}


def _alim(app, f):
    return next(a for a in app.proyecto.GetContents('*.ElmFeeder', 1) if a.loc_name == f)


def test_identidad_nativa_no_depende_del_wrapper_python():
    """PowerFactory puede devolver dos wrappers para la misma variación; la limpieza de
    optimizadores no debe confundir una variación previa con una creada por el estudio."""
    app, _feeders = _red()
    previa = app.carpetas['scheme'].GetContents('*.IntScheme', 1)[0]
    assert copy.copy(previa) is not previa
    assert guion._clave_nativa(copy.copy(previa)) == guion._clave_nativa(previa)


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_mide_cada_alimentador(semilla):
    """011:RF-31, 011:RF-33 — por alimentador: convergencia, tensiones extremas con su barra,
    elemento más cargado, cabecera, pérdidas, y las listas que juzga la web."""
    app, feeders = _red(random.Random(semilla))
    informe, rc = guion.ejecutar(app, _plan(feeders))
    assert rc == 0, informe
    assert sorted(informe['medidas']) == feeders
    for f, m in informe['medidas'].items():
        assert m['converge'] and m['barras'] and m['elementos']
        assert m['vm_min'] == min(u for _, u in m['barras'])
        assert m['vm_min_barra'] in {n for n, _ in m['barras']}
        assert m['cargabilidad_max'] == max(c for *_, c in m['elementos'])
        assert m['cabecera_kw'] > 0 and m['perdidas_kw'] > 0


def test_no_converge_no_se_ejecuta_el_estudio():
    """011:RF-17 — si el flujo previo del caso no converge, el estudio no se lanza."""
    app, feeders = _red()
    app.ldf.limite = 0.0
    orden = fake_pf.Orden(app, 'TOPO', clase='ComTieopt')
    app.ordenes['ComTieopt'] = orden
    informe, rc = guion.ejecutar(app, _plan(feeders, 'punto_apertura'))
    assert rc == 2 and 'no converge' in informe['error'] and orden.ejecuciones == 0


def test_sin_escalado_por_alimentador_y_sin_tocar_demandas():
    """011:RF-20, 011:RF-22 — el escalado del operador se apaga durante el estudio y se
    restituye; ninguna demanda cambia."""
    app, feeders = _red()
    app.ldf.iopt_fls = 1
    antes = {o.loc_name: o.plini for o in app.proyecto.GetContents('*.ElmLod', 1)}
    informe, rc = guion.ejecutar(app, _plan(feeders, 'flujo_desequilibrado'))
    assert rc == 0, informe
    assert {o.loc_name: o.plini for o in app.proyecto.GetContents('*.ElmLod', 1)} == antes
    assert app.ldf.iopt_fls == 1 and app.ldf.iopt_net == 0


def test_avisa_si_la_cabecera_se_aparta_del_ajuste():
    """011:RF-21 — en «Sin proyecto», cada cabecera contra el objetivo de su ajuste."""
    app, feeders = _red()
    medido, _ = guion.ejecutar(app, _plan(feeders))
    objetivos = {f: {'kw': m['cabecera_kw'], 'kvar': m['cabecera_kvar']}
                 for f, m in medido['medidas'].items()}
    bien, _ = guion.ejecutar(app, _plan(feeders, objetivos=objetivos))
    assert bien['avisos'] == []
    objetivos[feeders[0]]['kw'] *= 1.2
    mal, _ = guion.ejecutar(app, _plan(feeders, objetivos=objetivos, tolerancia=0.01))
    assert len(mal['avisos']) == 1 and feeders[0] in mal['avisos'][0]
    con, _ = guion.ejecutar(app, _plan(feeders, caso='con', objetivos=objetivos))
    assert con['avisos'] == []           # en «Con proyecto» la cabecera ya no es la medida


def test_el_punto_de_apertura_propone_sin_aplicar():
    """011:RF-26 — la maniobra propuesta va al informe; el interruptor vuelve a su estado y
    no queda ninguna variación del estudio."""
    app, feeders = _red()
    alim = _alim(app, feeders[0])
    red = alim.GetParent()
    sw = red.CreateObject('StaSwitch', 'SW_ENLACE')
    sw.on_off = 1
    alim._objs.append(sw)
    variaciones = {v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme')}

    def topo(app_, _orden):
        sw.Open()
        app_.salida.append('Switching actions: open SW_ENLACE')

    app.ordenes['ComTieopt'] = fake_pf.Orden(app, 'TOPO', clase='ComTieopt', efecto=topo)
    informe, rc = guion.ejecutar(app, _plan(feeders, 'punto_apertura'))
    assert rc == 0, informe
    assert informe['propuesta']['maniobras'] == [
        {'elemento': 'SW_ENLACE', 'clase': 'StaSwitch', 'accion': 'abrir'}]
    assert any('SW_ENLACE' in x for x in informe['propuesta']['resumen'])
    assert sw.IsClosed() == 1
    assert {v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme')} == variaciones


def test_el_balance_y_el_perfil_no_dejan_cambios():
    """011:RF-26 — la variación que crea el balance se borra; el perfil da sus tomas."""
    app, feeders = _red()
    variaciones = {v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme')}

    def balance(app_, _orden):
        app_.carpetas['scheme'].CreateObject('IntScheme', 'Balance')
        app_.salida.append('Number of modified elements: 3')

    def perfil(app_, _orden):
        for tr in _alim(app_, feeders[0]).GetObjs('ElmTr2'):
            object.__setattr__(tr, 'c:nntap', 2.0)

    app.ordenes['ComBalance'] = fake_pf.Orden(app, 'BAL', clase='ComBalance', efecto=balance)
    app.ordenes['ComVoltplan'] = fake_pf.Orden(app, 'VPO', clase='ComVoltplan', efecto=perfil)
    bal, rc = guion.ejecutar(app, _plan([feeders[0]], 'balance_fases'))
    assert rc == 0 and 'Number of modified elements: 3' in bal['propuesta']['resumen']
    assert app.ordenes['ComBalance'].startElm is _alim(app, feeders[0])
    vpo, rc = guion.ejecutar(app, _plan(feeders, 'perfil_tension'))
    assert rc == 0 and vpo['propuesta']['tomas']
    assert {t['toma'] for t in vpo['propuesta']['tomas']} == {2}
    assert {v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme')} == variaciones


def test_escenario_y_variaciones_del_caso():
    """011:RF-38, 011:RF-49 — el estudio corre con el escenario de su caso, y el informe dice
    cuál y qué variaciones estaban activas; al terminar, el caso del principio."""
    app, feeders = _red(escenario=True)
    inicial = app.caso
    informe, rc = guion.ejecutar(app, _plan(feeders, caso='con'))
    assert rc == 0, informe
    assert informe['escenario'] == 'Con proyecto' and informe['caso'] == 'Con proyecto'
    assert set(informe['variaciones_activas']) >= {AJUSTE.format(f=f) for f in feeders}
    assert app.caso is inicial


def test_el_informe_lista_las_obras_activas_en_cada_caso():
    """011:RF-68 — el informe de cada estudio lista las obras activas en su caso: una obra
    solo de «Con proyecto» sale en ese y no en «Sin proyecto»; las demás variaciones activas
    no son obras."""
    app, feeders = _red()
    casos = casos_pf.casos_del_proyecto(app)
    casos['con'].Activate()
    _variacion(app, f'Obra_terna_{feeders[0]}')
    casos['sin'].Activate()
    _variacion(app, f'Obra_condensador_{feeders[0]}')
    sin, rc = guion.ejecutar(app, _plan(feeders, caso='sin'))
    assert rc == 0, sin
    con, rc = guion.ejecutar(app, _plan(feeders, caso='con'))
    assert rc == 0, con
    assert sin['obras_activas'] == [f'Obra_condensador_{feeders[0]}']
    assert con['obras_activas'] == [f'Obra_terna_{feeders[0]}']
    assert all(not a.startswith('Obra_') for a in (AJUSTE.format(f=f) for f in feeders))


def test_troncal_dice_que_alimentadores_une():
    """apoyo de 011:RF-31 — la troncal informa los alimentadores que une y su enlace."""
    app, feeders = _red()
    a, b = _alim(app, feeders[0]), _alim(app, feeders[1])

    class Troncal(fake_pf.Obj):
        def GetTieOpenPoint(self):
            return self.enlace

    def bbone(app_, _orden):
        red = a.GetParent()
        t = Troncal(app_, 'ElmBbone', 'BB1', red)
        red._hijos.append(t)
        t.pBbStart, t.pBbEnd = a, b
        t.enlace = fake_pf.Obj(app_, 'ElmCoup', 'NA_1')

    app.ordenes['ComBbone'] = fake_pf.Orden(app, 'BB', clase='ComBbone', efecto=bbone)
    informe, rc = guion.ejecutar(app, _plan(feeders, 'troncal'))
    assert rc == 0 and informe['troncales'] == [
        {'troncal': 'BB1', 'desde': a.loc_name, 'hasta': b.loc_name, 'enlace': 'NA_1'}]


def test_sin_casos_preparados_no_se_estudia():
    """apoyo de 011:RF-1 — sin los casos, el guion lo dice en vez de estudiar otro caso."""
    app = fake_pf.proyecto(alimentadores=('F1',), bt=True, flujo=True)
    informe, rc = guion.ejecutar(app, _plan(['F1']))
    assert rc == 2 and 'prepare los casos' in informe['error']


# =========================================================================== T7: N-1
class _Troncal(fake_pf.Obj):
    """``ElmBbone`` del doble: su camino y su punto de enlace."""

    def GetCompleteBbPath(self, _reverso, _hasta_enlace=0):
        return list(self.camino)

    def GetTieOpenPoint(self):
        return self.enlace


def _bbone_que_crea(alims_con_troncal):
    """``ComBbone`` que deja una troncal por alimentador: sus dos primeras líneas."""
    def efecto(app_, _orden):
        for a in app_.proyecto.GetContents('*.ElmFeeder', 1):
            if a.loc_name not in alims_con_troncal:
                continue
            red = a.GetParent()
            t = _Troncal(app_, 'ElmBbone', f'BB_{a.loc_name}', red)
            red._hijos.append(t)
            lineas = sorted(a.GetObjs('ElmLne'), key=lambda o: o.loc_name)
            t.pBbStart, t.pBbEnd, t.enlace = a, None, None
            t.camino = [o for par in zip(a.GetObjs('ElmTerm'), lineas[:2]) for o in par]
    return efecto


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_n1_una_contingencia_por_tramo_troncal(semilla):
    """011:RF-43, 011:RF-44, 011:RF-36 — la troncal se calcula aunque solo se pida el N-1; una
    contingencia por tramo troncal de cada marcado, ninguna en derivaciones, y en cada una
    las medidas que juzga la web."""
    rng = random.Random(semilla)
    app, feeders = _red(rng)
    bb = fake_pf.Orden(app, 'BB', clase='ComBbone', efecto=_bbone_que_crea(feeders))
    app.ordenes['ComBbone'] = bb
    informe, rc = guion.ejecutar(app, _plan(feeders, 'contingencias'))
    assert rc == 0, informe
    assert bb.ejecuciones == 1
    esperadas = sorted((f, ln) for f in feeders for ln in (f'{f}_L1', f'{f}_L2'))
    assert sorted((c['alimentador'], c['contingencia']) for c in informe['contingencias']) == esperadas
    for c in informe['contingencias']:
        assert c['converge'] and set(c['medidas']) == set(feeders)
        assert all(m['barras'] for m in c['medidas'].values())


def test_n1_con_el_modulo_de_contingencias():
    """011:RF-36 — el N-1 lo calcula ``ComSimoutage``: uno propio con un ``ComOutage`` por
    tramo troncal, cada contingencia leída con su traza hasta el final y cerrada, sin
    sacar nada de servicio a mano; el análisis creado no queda en el caso."""
    app, feeders = _red()
    app.ordenes['ComBbone'] = fake_pf.Orden(app, 'BB', clase='ComBbone', efecto=_bbone_que_crea(feeders))
    informe, rc = guion.ejecutar(app, _plan(feeders, 'contingencias'))
    assert rc == 0, informe
    assert app.n1_ejecuciones == 1
    assert len(app.trazas) == len(informe['contingencias']) == 2 * len(feeders)
    assert app.trazas_cerradas == app.trazas and all(t.paso == 1 for t in app.trazas)
    assert sorted(t.objs[0].loc_name for t in app.trazas) == sorted(
        c['contingencia'] for c in informe['contingencias'])
    assert not [e for e in app.escrituras if e[1] == 'outserv'], 'nada fuera de servicio a mano'
    assert not app.caso.GetContents('*.ComSimoutage'), 'el análisis creado se borra'
    assert app.en_falta == set()


def test_n1_alimentador_sin_troncal_queda_fuera():
    """011:RF-45 — el marcado sin troncal no entra en el N-1 y se dice."""
    app, feeders = _red(random.Random(4))
    con = feeders[:-1]
    app.ordenes['ComBbone'] = fake_pf.Orden(app, 'BB', clase='ComBbone', efecto=_bbone_que_crea(con))
    informe, rc = guion.ejecutar(app, _plan(feeders, 'contingencias'))
    assert rc == 0, informe
    assert informe['sin_troncal'] == [feeders[-1]]
    assert any(feeders[-1] in a and 'sin troncal' in a for a in informe['avisos'])
    assert {c['alimentador'] for c in informe['contingencias']} == set(con)


def test_n1_sin_orden_de_troncal():
    """011:RF-44 — sin ``ComBbone`` en el caso no hay N-1, y se dice."""
    app, feeders = _red()
    informe, rc = guion.ejecutar(app, _plan(feeders, 'contingencias'))
    assert rc == 2 and 'ComBbone' in informe['error']


# =========================================================================== T8: guiones
def _guion(padre, clase, nombre, *, parametros=(), objetos=(), rc=0, efecto=None):
    """Un ``ComDpl``/``ComPython`` con sus parámetros ``(nombre, tipo, valor, unidad, desc)``."""
    g = padre.CreateObject(clase, nombre)
    g.IntName = [p[0] for p in parametros]
    g.IntType = [p[1] for p in parametros]
    g.IntExpr = [str(p[2]) for p in parametros]
    g.IntUnit = [p[3] for p in parametros]
    g.IntDesc = [p[4] for p in parametros]
    g.obj_name = list(objetos)
    g.obj_id = [None] * len(objetos)
    object.__setattr__(g, 'rc', rc)
    object.__setattr__(g, 'efecto', efecto)
    return g


def _carpeta_guiones(app):
    app.carpetas['script'] = app.proyecto.CreateObject('IntPrjfolder', 'Scripts')
    return app.carpetas['script']


def _plan_guion(feeders, caso='sin', nombre='Revisar', origen='caso', **parametros):
    return {'project': 'P', 'feeders': feeders, 'caso': caso, 'stamp': '20261011_120000',
            'guion': {'nombre': nombre, 'origen': origen}, 'parametros': parametros,
            'native_action_context': contexto_nativo('P', feeders, 'guion')}


PARAMS = (('umbral', 'double', 0.95, 'p.u.', 'Tensión mínima'),
          ('pasos', 'int', 3, '', 'Iteraciones'),
          ('etiqueta', 'string', 'x', '', 'Prefijo'))


def test_guion_lista_los_del_caso_y_de_la_carpeta():
    """011:RF-27 — los ``ComDpl`` y ``ComPython`` de los casos y de la carpeta de guiones
    (con sus subcarpetas), cada uno con sus parámetros de entrada, sus objetos externos y
    los casos donde está."""
    app, feeders = _red()
    casos = casos_pf.casos_del_proyecto(app)
    for rol in ('sin', 'con'):
        _guion(casos[rol], 'ComDpl', 'Revisar', parametros=PARAMS, objetos=('linea',))
    _guion(casos['sin'], 'ComPython', 'Solo_sin')
    sub = _carpeta_guiones(app).CreateObject('IntPrjfolder', 'Operador')
    _guion(sub, 'ComPython', 'Informe')
    inicial = app.caso
    informe, rc = guion.ejecutar_guion(app, {'project': 'P', 'feeders': feeders})
    assert rc == 0, informe
    lista = {(g['nombre'], g['origen']): g for g in informe['guiones']}
    assert sorted(lista) == [('Informe', 'proyecto'), ('Revisar', 'caso'), ('Solo_sin', 'caso')]
    assert lista[('Revisar', 'caso')]['clase'] == 'ComDpl'
    assert lista[('Informe', 'proyecto')]['clase'] == 'ComPython'
    assert lista[('Revisar', 'caso')]['casos'] == ['sin', 'con']
    assert lista[('Solo_sin', 'caso')]['casos'] == ['sin']
    assert lista[('Informe', 'proyecto')]['casos'] == ['sin', 'con']
    assert lista[('Revisar', 'caso')]['parametros'] == [
        {'nombre': n, 'tipo': t, 'valor': str(v), 'unidad': u, 'descripcion': d}
        for n, t, v, u, d in PARAMS]
    assert lista[('Revisar', 'caso')]['objetos'] == ['linea']
    assert app.caso is inicial


@pytest.mark.parametrize('rol', ('sin', 'con'))
def test_guion_en_cada_caso_con_los_valores_del_operador(rol):
    """011:RF-28, 011:RF-29 — el guion corre en su caso con los valores escritos por el
    operador (convertidos al tipo de cada parámetro), y el informe da su código y lo que
    escribió en la ventana de salida; al terminar, el caso del principio."""
    app, feeders = _red()
    visto = {}

    def efecto(app_, g):
        visto['caso'] = app_.caso.loc_name
        visto['valores'] = dict(zip(g.IntName, g.IntExpr))
        app_.salida.extend(['Revisando...', f'umbral={g.IntExpr[0]}'])

    for caso in casos_pf.casos_del_proyecto(app).values():
        _guion(caso, 'ComDpl', 'Revisar', parametros=PARAMS, efecto=efecto)
    inicial = app.caso
    app.salida.append('de antes')
    informe, rc = guion.ejecutar_guion(
        app, _plan_guion(feeders, rol, umbral='0.9', pasos=5, etiqueta='obra'))
    assert rc == 0, informe
    assert visto == {'caso': casos_pf.NOMBRES[rol],
                     'valores': {'umbral': '0.9', 'pasos': '5', 'etiqueta': 'obra'}}
    assert informe['codigo_guion'] == 0 and informe['caso'] == casos_pf.NOMBRES[rol]
    assert informe['salida'] == ['Revisando...', 'umbral=0.9']
    assert app.caso is inicial


def test_guion_de_la_carpeta_con_objeto_externo():
    """011:RF-28 — un guion de la carpeta del proyecto corre en el caso pedido, y un
    parámetro de tipo objeto se pasa con ``SetExternalObject``."""
    app, feeders = _red()
    visto = {}

    def efecto(app_, g):
        visto['objeto'] = g.obj_id[0]
        visto['caso'] = app_.caso.loc_name

    _guion(_carpeta_guiones(app), 'ComPython', 'Informe', objetos=('linea',), efecto=efecto)
    linea = f'{feeders[0]}_L1'
    informe, rc = guion.ejecutar_guion(
        app, _plan_guion(feeders, 'con', 'Informe', 'proyecto', linea=f'{linea}.ElmLne'))
    assert rc == 0, informe
    assert visto['objeto'].loc_name == linea and visto['caso'] == 'Con proyecto'


@pytest.mark.parametrize('parametros, texto', [
    ({'no_existe': 1}, 'no_existe'),
    ({'pasos': '2.5'}, 'pasos'),
    ({'linea': 'NADA.ElmLne'}, 'NADA.ElmLne'),
])
def test_guion_con_valores_que_no_valen_no_se_ejecuta(parametros, texto):
    """011:RF-28 — un parámetro que el guion no tiene, un valor que no es de su tipo o un
    objeto que no está en la red: no se ejecuta, y se dice cuál."""
    app, feeders = _red()
    caso = casos_pf.casos_del_proyecto(app)['sin']
    g = _guion(caso, 'ComDpl', 'Revisar', parametros=PARAMS, objetos=('linea',))
    informe, rc = guion.ejecutar_guion(app, _plan_guion(feeders, **parametros))
    assert rc == 2 and texto in informe['error']
    assert getattr(g, 'ejecuciones', 0) == 0


def test_guion_que_falla_informa_y_deja_seguir():
    """011:RF-29, 011:RF-30 — el código de error y la salida del guion van al informe, el
    caso del principio vuelve, y el estudio siguiente se ejecuta con normalidad."""
    app, feeders = _red()

    def efecto(app_, _g):
        app_.salida.append('Error: división por cero en la línea 12')

    for caso in casos_pf.casos_del_proyecto(app).values():
        _guion(caso, 'ComDpl', 'Revisar', rc=1, efecto=efecto)
    inicial = app.caso
    informe, rc = guion.ejecutar_guion(app, _plan_guion(feeders))
    assert rc == 2
    assert informe['codigo_guion'] == 1
    assert 'código 1' in informe['error'] and 'Revisar' in informe['error']
    assert informe['salida'] == ['Error: división por cero en la línea 12']
    assert app.caso is inicial
    siguiente, rc = guion.ejecutar(app, _plan(feeders))
    assert rc == 0 and siguiente['medidas'], siguiente


def test_guion_que_no_esta_en_el_caso():
    """011:RF-28 — un guion que solo está en «Sin proyecto» no se busca en otro sitio."""
    app, feeders = _red()
    _guion(casos_pf.casos_del_proyecto(app)['sin'], 'ComPython', 'Solo_sin')
    informe, rc = guion.ejecutar_guion(app, _plan_guion(feeders, 'con', 'Solo_sin'))
    assert rc == 2 and 'Solo_sin' in informe['error'] and 'Con proyecto' in informe['error']


def test_guion_sin_casos_preparados():
    """apoyo de 011:RF-1 — sin los casos, ni se listan ni se ejecutan guiones."""
    app = fake_pf.proyecto(alimentadores=('F1',), bt=True, flujo=True)
    for plan in ({'project': 'P', 'feeders': ['F1']}, _plan_guion(['F1'])):
        informe, rc = guion.ejecutar_guion(app, plan)
        assert rc == 2 and 'prepare los casos' in informe['error']


def test_guion_por_linea_de_ordenes(tmp_path, monkeypatch):
    """011:RF-27, 011:RF-29 — ``--guion`` sin guion en el plan lista; con guion, lo ejecuta."""
    app, feeders = _red()
    for caso in casos_pf.casos_del_proyecto(app).values():
        _guion(caso, 'ComDpl', 'Revisar', parametros=PARAMS)
    monkeypatch.setitem(sys.modules, 'powerfactory',
                        types.SimpleNamespace(GetApplicationExt=lambda: app))
    plan, salida = tmp_path / 'plan.json', tmp_path / 'informe.json'
    args = ['--guion', '--plan', str(plan), '--output-json', str(salida)]
    plan.write_text(json.dumps({
        'project': 'P', 'feeders': feeders,
        'native_action_context': contexto_nativo('P', feeders, 'guion'),
    }), encoding='utf-8')
    assert guion.main(args) == 0
    assert [g['nombre'] for g in json.loads(salida.read_text(encoding='utf-8'))['guiones']] == ['Revisar']
    plan.write_text(json.dumps(_plan_guion(feeders, pasos=2)), encoding='utf-8')
    assert guion.main(args) == 0
    assert json.loads(salida.read_text(encoding='utf-8'))['codigo_guion'] == 0
