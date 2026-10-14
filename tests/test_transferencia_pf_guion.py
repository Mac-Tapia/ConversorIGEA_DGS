"""Spec 011, T15c: ``tools/transferencia_pf.py`` contra ``fake_pf``.

Dos alimentadores en cadena, A y B, unidos por un enlace normalmente abierto entre sus
últimas barras. El flujo de carga del doble entiende la transferencia: con el enlace
cerrado y un tramo de un alimentador abierto (su seccionador o el tramo fuera de
servicio), las SED del lado del enlace pasan al otro, y la cargabilidad del primer tramo
del que recibe sube con lo que recibe. Con la capacidad de ese tramo se fija en qué paso
deja de ser viable. La prueba real la hace el usuario (T19).
"""
from __future__ import annotations

import random

import pytest

import fake_pf
from apoyo import cargar_herramienta

casos_pf = cargar_herramienta('casos_pf.py', 'casos_t15c', tools_en_path=True)
guion = cargar_herramienta('transferencia_pf.py', 'transferencia_t15c', tools_en_path=True)

SEMILLAS = (4, 27, 58, 90)
SIN, CON = 'Sin proyecto', 'Con proyecto'
P_SED_KW = 50.0                    # plini de cada carga de fake_pf.proyecto (0,05 MW)


class _Troncal(fake_pf.Obj):
    def GetCompleteBbPath(self, _reverso, _hasta_enlace=0):
        return list(self.camino)

    def GetTieOpenPoint(self):
        return self.enlace


def _alim(app, f):
    return next(a for a in app.proyecto.GetContents('*.ElmFeeder', 1) if a.loc_name == f)


def _por_indice(objs):
    return sorted(objs, key=lambda o: int(o.loc_name.rsplit('_', 1)[1][1:]))


def _sin_grabar(obj, **attrs):
    for k, v in attrs.items():
        object.__setattr__(obj, k, v)


def _corte(alim):
    """Índice del tramo abierto de un alimentador (seccionador o fuera de servicio), o None."""
    for j, ln in enumerate(_por_indice(alim.GetObjs('ElmLne')), start=1):
        cubs = [c for b in alim.GetObjs('ElmTerm') for c in b.GetContents('*.StaCubic')
                if c.obj_id is ln]
        if getattr(ln, 'outserv', 0) or any(not getattr(sw, 'on_off', 1)
                                            for c in cubs for sw in c.GetContents('*.StaSwitch')):
            return j
    return None


def _flujo(app, capacidad_kw):
    """``ComLdf`` que mueve las SED del lado del enlace al otro alimentador.

    ``capacidad_kw`` es la del primer tramo de cada alimentador: un número para los dos o
    un diccionario por alimentador. Cada carga cuenta con su factor de escala ``scale0``.
    """
    capacidades = (capacidad_kw if isinstance(capacidad_kw, dict)
                   else {'A': capacidad_kw, 'B': capacidad_kw})
    app.capacidades = capacidades

    def efecto(app_, _orden):
        a, b = _alim(app_, 'A'), _alim(app_, 'B')
        cargas = {f: [c.plini * 1000 * (getattr(c, 'scale0', 1.0) or 1.0)
                      for c in _por_indice(x.GetObjs('ElmLod'))] for f, x in (('A', a), ('B', b))}
        total = {f: sum(v) for f, v in cargas.items()}
        if app_.enlace.on_off:
            for cede, recibe in (('A', 'B'), ('B', 'A')):
                j = _corte(_alim(app_, cede))
                if j is not None:
                    pasa = sum(cargas[cede][j - 1:])
                    total[cede] -= pasa
                    total[recibe] += pasa
        for f, x in (('A', a), ('B', b)):
            l1 = _por_indice(x.GetObjs('ElmLne'))[0]
            object.__setattr__(l1, 'c:loading', 100.0 * total[f] / capacidades[f])
            object.__setattr__(l1, 'm_Psum:bus1', total[f] / 1000.0)
            object.__setattr__(l1, 'm_Qsum:bus1', total[f] / 3000.0)
            for i, barra in enumerate(_por_indice(x.GetObjs('ElmTerm'))):
                object.__setattr__(barra, 'm_u', 1.0 - 0.001 * i)
        app_.ldf_valido = True
    return fake_pf.Orden(app, 'ComLdf', efecto=efecto)


def _bbone(app):
    """``ComBbone`` que deja una troncal por alimentador hasta el enlace."""
    def efecto(app_, _orden):
        for cede, recibe in (('A', 'B'), ('B', 'A')):
            x = _alim(app_, cede)
            red = x.GetParent()
            t = _Troncal(app_, 'ElmBbone', f'BB_{cede}', red)
            red._hijos.append(t)
            barras, lineas = _por_indice(x.GetObjs('ElmTerm')), _por_indice(x.GetObjs('ElmLne'))
            t.camino = [o for par in zip(barras, lineas + [None]) for o in par if o is not None]
            t.pBbStart, t.pBbEnd, t.enlace = x, _alim(app_, recibe), app_.enlace
    orden = fake_pf.Orden(app, 'BB', clase='ComBbone', efecto=efecto)
    app.ordenes['ComBbone'] = orden
    return orden


def _seccionador(app, alim, j, uso='dct'):
    """Un interruptor del export en el cubículo de cabecera del tramo ``j``."""
    ln = _por_indice(alim.GetObjs('ElmLne'))[j - 1]
    barra = _por_indice(alim.GetObjs('ElmTerm'))[j - 1]
    cub = next(c for c in barra.GetContents('*.StaCubic') if c.obj_id is ln)
    sw = fake_pf.Interruptor(app, 'StaSwitch', f'SW_{alim.loc_name}_{j}', cub)
    cub._hijos.append(sw)
    _sin_grabar(sw, on_off=1, aUsage=uso)
    return sw


def _red(rng, *, n=None, seccionadores=(), otros=(), escenario=False):
    """A y B con ``n`` SED cada uno, el enlace, los casos preparados y los seccionadores."""
    n = n or rng.randint(3, 6)
    app = fake_pf.proyecto(alimentadores=('A', 'B'), cargas_por_alim=n, bt=True, flujo=True,
                           escenario=escenario)
    ajustes = []
    for f in ('A', 'B'):
        v = app.carpetas['scheme'].CreateObject('IntScheme', f'Ajuste_{f}_20261012_090000')
        v.NewStage(f'Etapa_{f}', 0, 1)
        app.grabando = None
        ajustes.append({'feeder': f, 'variacion': v.loc_name, 'cuadrado': True})
    base = {'variaciones': [x['variacion'] for x in ajustes], 'feeders': ['A', 'B'],
            'ajustes': ajustes, 'excluidos': []}
    informe, codigo = casos_pf.preparar(app, {'project': 'P', 'feeders': ['A', 'B'], 'base': base,
                                              'caso_base_sin_verificar': {}})
    assert codigo == 0, informe
    a, b = _alim(app, 'A'), _alim(app, 'B')
    fin_a, fin_b = _por_indice(a.GetObjs('ElmTerm'))[-1], _por_indice(b.GetObjs('ElmTerm'))[-1]
    red = fin_a.GetParent()
    enlace = fake_pf.Interruptor(app, 'ElmCoup', 'NA_AB', red)
    red._hijos.append(enlace)
    _sin_grabar(enlace, on_off=0, aUsage='swt')
    for lado, barra in enumerate((fin_a, fin_b)):
        cub = fake_pf.Obj(app, 'StaCubic', f'c{lado}_NA_AB', barra)
        barra._hijos.append(cub)
        _sin_grabar(cub, obj_id=enlace, obj_bus=lado)
    app.enlace = enlace
    for j in seccionadores:
        _seccionador(app, a, j)
    for j, uso in otros:
        _seccionador(app, a, j, uso)
    app.atributos_en_variacion = True
    _bbone(app)
    app.escrituras.clear()
    app.creados.clear()
    return app, n


def _plan(**extra):
    return {'project': 'P', 'feeders': ['A', 'B'], 'casos': [SIN], **extra}


def _de(informe, cede, caso=SIN):
    return next(r for r in informe['resultados'] if r['cede'] == cede and r['caso'] == caso)


# --------------------------------------------------------------------------- RF-105 a RF-110
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_dos_sentidos_por_el_enlace_con_la_carga_de_cada_paso(semilla):
    """011:RF-105, 011:RF-106, 011:RF-108, 011:RF-109, 011:RF-110 — los dos sentidos por el
    enlace; del enlace a la cabecera del que cede, un paso por barra y por seccionador, con
    la carga que queda del lado del enlace."""
    rng = random.Random(semilla)
    n = rng.randint(3, 6)
    secc = sorted(rng.sample(range(2, n + 1), rng.randint(1, n - 1)))
    app, _ = _red(rng, n=n, seccionadores=secc)
    app.ldf = _flujo(app, capacidad_kw=10_000.0)
    informe, codigo = guion.calcular(app, _plan())
    assert codigo == 0, informe
    assert {(r['cede'], r['recibe'], r['enlace']) for r in informe['resultados']} == {
        ('A', 'B', 'NA_AB'), ('B', 'A', 'NA_AB')}
    pasos = _de(informe, 'A')['pasos']
    nodos = [p for p in pasos if p['tipo'] == 'nodo']
    # Barras del enlace hacia la cabecera, sin la cabecera: A_Bn … A_B1.
    assert [p['punto'] for p in nodos] == [f'A_B{k}' for k in range(n, 0, -1)]
    for p in nodos:
        k = int(p['punto'].rsplit('B', 1)[1])
        assert p['carga_kw'] == pytest.approx((n - k + 1) * P_SED_KW)
    for p in (p for p in pasos if p['tipo'] == 'seccionador'):
        j = int(p['punto'].rsplit('_', 1)[1])
        assert p['carga_kw'] == pytest.approx((n - j + 1) * P_SED_KW)
    assert {p['punto'] for p in pasos if p['tipo'] == 'seccionador'} == {f'SW_A_{j}' for j in secc}


def test_solo_cuentan_los_seccionadores():
    """011:RF-118, 011:RF-128 — un interruptor o un seccionalizador del camino no es un punto
    de maniobra; un seccionador sí."""
    app, n = _red(random.Random(1), n=4, seccionadores=[3], otros=[(2, 'cbk'), (4, 'swt')])
    app.ldf = _flujo(app, capacidad_kw=10_000.0)
    informe, codigo = guion.calcular(app, _plan())
    assert codigo == 0, informe
    puntos = {p['punto'] for p in _de(informe, 'A')['pasos'] if p['tipo'] == 'seccionador'}
    assert puntos == {'SW_A_3'}


def test_proyecto_que_no_distingue_seccionadores():
    """011:RF-129 — con todos los equipos como interruptor (un DGS anterior), solo por nodos
    y se pide reconvertir; con la entrada cargada, se reconocen por su número."""
    app, n = _red(random.Random(2), n=4, otros=[(2, 'cbk'), (3, 'cbk')])
    app.ldf = _flujo(app, capacidad_kw=10_000.0)
    informe, _ = guion.calcular(app, _plan())
    r = _de(informe, 'A')
    assert r['maximo_seccionador'] is None and any('volver a convertir' in a for a in r['avisos'])
    informe, _ = guion.calcular(app, _plan(seccionadores=['SW_A_3']))
    r = _de(informe, 'A')
    assert r['maximo_seccionador']['punto'] == 'SW_A_3'


# --------------------------------------------------------------------------- RF-111 a RF-117
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_el_limite_corta_en_el_paso_conocido(semilla):
    """011:RF-111, 011:RF-112, 011:RF-113, 011:RF-114 — con la capacidad del que recibe para
    ``m`` SED más, los pasos hasta ``m`` son viables y el siguiente no, limitado por la
    sobrecarga de su primer tramo."""
    rng = random.Random(semilla)
    n = rng.randint(4, 7)
    m = rng.randint(1, n - 1)
    secc = list(range(2, n + 1))
    app, _ = _red(rng, n=n, seccionadores=secc)
    app.ldf = _flujo(app, capacidad_kw=(n + m + 0.5) * P_SED_KW)
    informe, codigo = guion.calcular(app, _plan())
    assert codigo == 0, informe
    r = _de(informe, 'A')
    assert r['maximo_nodo'] == {'punto': f'A_B{n - m + 1}', 'carga_kw': m * P_SED_KW,
                                'carga_kva': pytest.approx(r['maximo_nodo']['carga_kva'])}
    assert r['maximo_seccionador']['punto'] == f'SW_A_{n - m + 1}'
    assert r['limita']['motivo'] == 'sobrecarga' and r['limita']['elemento'] == 'B_L1'


def test_ningun_paso_viable_dice_que_lo_impide():
    """011:RF-116 — si el que recibe ya no admite ni la primera SED, el sentido no admite
    transferencia y se dice el elemento."""
    app, n = _red(random.Random(3), n=3, seccionadores=[2])
    app.ldf = _flujo(app, capacidad_kw=3 * P_SED_KW)
    informe, _ = guion.calcular(app, _plan())
    r = _de(informe, 'A')
    assert r['admite'] is False and any('B_L1' in a for a in r['avisos'])


def test_sin_enlace_no_calcula_y_lo_dice():
    """011:RF-107 — sin punto de enlace entre los dos, nada se calcula y se nombran los dos."""
    app, _ = _red(random.Random(4), n=3)

    def sin_troncales(_app, _o):
        return None

    app.ordenes['ComBbone'] = fake_pf.Orden(app, 'BB', clase='ComBbone', efecto=sin_troncales)
    app.ldf = _flujo(app, capacidad_kw=10_000.0)
    informe, codigo = guion.calcular(app, _plan())
    assert codigo == 2 and 'A' in informe['error'] and 'B' in informe['error']
    assert 'enlace' in informe['error']


# --------------------------------------------------------------------------- RF-119 y RF-120
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_todo_vuelve_a_su_estado_y_no_se_graba_nada(semilla):
    """011:RF-119, 011:RF-120 — al terminar, cada interruptor y cada tramo está como estaba,
    el enlace abierto, ninguna variación ni troncal nueva, el escenario del caso activo y
    la etapa que grababa, la misma; ninguna maniobra fue a un escenario."""
    rng = random.Random(semilla)
    n = rng.randint(3, 5)
    app, _ = _red(rng, n=n, seccionadores=[2], escenario=True)
    app.ldf = _flujo(app, capacidad_kw=(n + 1.5) * P_SED_KW)
    caso = next(c for c in casos_pf.casos_del_proyecto(app).values() if c.loc_name == SIN)
    caso.Activate()
    grababa = app.carpetas['scheme'].CreateObject('IntScheme', 'Del_operador')
    grababa.NewStage('Etapa_operador', 0, 1)
    etapa = app.GetRecordingStage()
    escenario = app.GetActiveScenario()
    estado = {(o.loc_name, a): getattr(o, a, None) for o in app.proyecto.GetContents('*', 1)
              for a in ('on_off', 'outserv') if hasattr(o, a)}
    variaciones = {v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme')}
    app.escrituras.clear()
    informe, codigo = guion.calcular(app, _plan())
    assert codigo == 0, informe
    assert all(r['restituido'] for r in informe['restitucion'].values())
    caso.Activate()
    assert {(o.loc_name, a): getattr(o, a, None) for o in app.proyecto.GetContents('*', 1)
            for a in ('on_off', 'outserv') if hasattr(o, a)} == estado
    assert app.enlace.on_off == 0
    assert {v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme')} == variaciones
    assert app.GetCalcRelevantObjects('*.ElmBbone') == []
    assert app.GetActiveScenario() is escenario and app.GetRecordingStage() is etapa
    maniobras = [e for e in app.escrituras if e[1] in ('on_off', 'outserv')]
    assert maniobras and all(e[4] is None for e in maniobras)          # ningún escenario
    assert all(e[3] is not etapa for e in maniobras)                    # ni la del operador
    assert not grababa.__dict__.get('_cambios')


def test_cancelar_tambien_restituye():
    """011:RF-119 — si se cancela a mitad, todo vuelve igual y el informe lo dice."""
    app, n = _red(random.Random(5), n=4, seccionadores=[2, 3])
    app.ldf = _flujo(app, capacidad_kw=10_000.0)
    llamadas = []

    def cancelado():
        llamadas.append(1)
        return len(llamadas) > 3

    informe, codigo = guion.calcular(app, _plan(), cancelado=cancelado)
    assert codigo == 2 and informe['cancelado']
    assert app.enlace.on_off == 0
    assert all(getattr(sw, 'on_off', 1) == 1
               for sw in app.proyecto.GetContents('*.StaSwitch', 1))
    assert all(not getattr(ln, 'outserv', 0) for ln in app.proyecto.GetContents('*.ElmLne', 1))


def test_dos_casos_y_fichero(tmp_path):
    """011:RF-104, 011:RF-121 — en los dos casos pedidos, y el fichero con una fila por caso,
    sentido, enlace y paso."""
    app, n = _red(random.Random(6), n=3, seccionadores=[2])
    app.ldf = _flujo(app, capacidad_kw=10_000.0)
    informe, codigo = guion.calcular(app, _plan(casos=[SIN, CON]))
    assert codigo == 0, informe
    assert {r['caso'] for r in informe['resultados']} == {SIN, CON}
    destino = guion.escribir_fichero(informe['resultados'], tmp_path / 't.csv')
    filas = destino.read_text(encoding='utf-8-sig').splitlines()[1:]
    assert len(filas) == sum(len(r['pasos']) for r in informe['resultados'])


def test_plan_invalido():
    """011:RF-104 — dos alimentadores distintos y casos con proyecto o sin proyecto."""
    app, _ = _red(random.Random(7), n=3)
    assert guion.calcular(app, {**_plan(), 'feeders': ['A']})[1] == 2
    informe, codigo = guion.calcular(app, _plan(casos=['Caso base']))
    assert codigo == 2 and 'Caso base' in informe['error']


def test_restituye_aunque_borrar_la_variacion_no_deshaga_las_maniobras():
    """011:RF-119 — si borrar la variación temporal no devolviera los interruptores (el
    doble sin ``atributos_en_variacion``), el guion los devuelve él y lo comprueba."""
    app, n = _red(random.Random(8), n=4, seccionadores=[2, 3])
    app.atributos_en_variacion = False
    app.ldf = _flujo(app, capacidad_kw=10_000.0)
    informe, codigo = guion.calcular(app, _plan())
    assert codigo == 0, informe
    assert all(r['restituido'] for r in informe['restitucion'].values())
    assert app.enlace.on_off == 0
    assert all(sw.on_off == 1 for sw in app.proyecto.GetContents('*.StaSwitch', 1))
    assert all(ln.outserv == 0 for ln in app.proyecto.GetContents('*.ElmLne', 1))


# =========================================================================== T15d
class _Frontera(fake_pf.Obj):
    """``ElmBoundary``: guarda los cubículos que se le añaden."""

    def AddCubicle(self, cub):
        self.__dict__.setdefault('cubiculos', []).append(cub)
        return 0


class _Capacidad(fake_pf.Obj):
    """``ComTransfer`` por elementos, calculado por su cuenta: lo que el que recibe (el de
    la barra de la frontera) admite hasta su capacidad, menos lo que ya tiene sin la parte
    importada. Así coincide con la bisección solo si las dos hacen lo correcto."""

    def Execute(self):
        app = self._app
        app.tc_ejecuciones = getattr(app, 'tc_ejecuciones', 0) + 1
        if getattr(app, 'tc_falla', None) == 'licencia':
            raise RuntimeError('No licence available')
        (cub,) = self.p_boundary.cubiculos
        barra = cub.GetParent()
        recibe = next(a for a in app.proyecto.GetContents('*.ElmFeeder', 1)
                      if barra in a.GetObjs('ElmTerm'))
        importadas = {id(o) for o in self.p_impElms.All()}
        propias = sum(c.plini * 1000 * (getattr(c, 'scale0', 1.0) or 1.0)
                      for c in recibe.GetObjs('ElmLod') if id(c) not in importadas)
        object.__setattr__(self, '_mw', (app.capacidades[recibe.loc_name] - propias) / 1000.0)
        assert self.iSave == guion.TC_NO_GUARDAR and self.iopt_selreg == 1
        return 0

    def IsLastIterationFeasible(self):
        return 0 if getattr(self._app, 'tc_falla', None) == 'inviable' else 1

    def GetTransferCalcData(self):
        return [self._mw, 7]


@pytest.fixture
def con_comtransfer(monkeypatch):
    monkeypatch.setitem(fake_pf._CLASES, 'ComTransfer', _Capacidad)
    monkeypatch.setitem(fake_pf._CLASES, 'ElmBoundary', _Frontera)


def _capacidad_de(informe, cede='A'):
    return _de(informe, cede)['capacidad']


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_capacidad_igual_con_comtransfer_y_por_flujos(semilla, monkeypatch):
    """011:RF-122, 011:RF-123, 011:RF-124, 011:RF-125 — en la configuración del seccionador
    viable más lejano, la capacidad del enlace es lo que el que recibe admite hasta su
    límite; ``ComTransfer`` y los flujos sucesivos dan la misma cifra, y el margen es la
    capacidad menos lo que ya transfiere."""
    rng = random.Random(semilla)
    n = rng.randint(4, 6)
    m = rng.randint(1, n - 1)
    capacidad = (n + m + 0.5) * P_SED_KW
    esperada = capacidad - n * P_SED_KW            # lo que B admite además de lo suyo

    cifras = {}
    for metodo in ('ComTransfer', 'flujos sucesivos'):
        with monkeypatch.context() as mp:
            if metodo == 'ComTransfer':
                mp.setitem(fake_pf._CLASES, 'ComTransfer', _Capacidad)
                mp.setitem(fake_pf._CLASES, 'ElmBoundary', _Frontera)
            app, _ = _red(random.Random(semilla), n=n, seccionadores=list(range(2, n + 1)))
            app.ldf = _flujo(app, capacidad_kw=capacidad)
            informe, codigo = guion.calcular(app, _plan())
        assert codigo == 0, informe
        c = _capacidad_de(informe)
        assert c['metodo'] == metodo and c['punto'] == f'SW_A_{n - m + 1}'
        assert c['transferida_kw'] == pytest.approx(m * P_SED_KW)
        assert c['margen_kw'] == pytest.approx(c['capacidad_kw'] - c['transferida_kw'])
        cifras[metodo] = c['capacidad_kw']
    assert cifras['ComTransfer'] == pytest.approx(esperada)
    assert cifras['flujos sucesivos'] == pytest.approx(esperada, rel=2e-3)


@pytest.mark.parametrize('falla', ['licencia', 'inviable'])
def test_capacidad_sin_licencia_o_inviable_por_flujos(falla, con_comtransfer):
    """011:RF-125 — sin licencia, o sin solución viable, se calcula por flujos sucesivos y
    el informe lo dice."""
    app, _ = _red(random.Random(11), n=4, seccionadores=[2, 3, 4])
    app.tc_falla = falla
    app.ldf = _flujo(app, capacidad_kw=6.5 * P_SED_KW)
    informe, codigo = guion.calcular(app, _plan())
    assert codigo == 0, informe
    c = _capacidad_de(informe)
    assert c['metodo'] == 'flujos sucesivos' and app.tc_ejecuciones >= 1
    assert c['capacidad_kw'] == pytest.approx(2.5 * P_SED_KW, rel=2e-3)
    assert any('flujos sucesivos' in a for a in c['avisos'])


def test_capacidad_solo_con_los_limites_del_que_recibe(con_comtransfer):
    """011:RF-127 — los límites se aplican al que recibe y a la parte transferida: el que
    cede, sobrecargado en lo que le queda, no limita la capacidad."""
    app, _ = _red(random.Random(12), n=4, seccionadores=[2, 3, 4])
    app.ldf = _flujo(app, capacidad_kw={'A': 1.0, 'B': 6.5 * P_SED_KW})
    app.tc_falla = 'licencia'
    informe, codigo = guion.calcular(app, _plan())
    assert codigo == 0, informe
    assert _capacidad_de(informe)['capacidad_kw'] == pytest.approx(2.5 * P_SED_KW, rel=2e-3)


def test_capacidad_no_deja_nada_en_el_proyecto(con_comtransfer):
    """011:RF-126 — ni el análisis, ni su frontera, ni sus selecciones, ni el punto escalado
    quedan en el proyecto; nada va a un escenario."""
    app, _ = _red(random.Random(13), n=4, seccionadores=[2, 3, 4], escenario=True)
    app.ldf = _flujo(app, capacidad_kw=6.5 * P_SED_KW)
    for falla in (None, 'licencia'):
        app.tc_falla = falla
        app.escrituras.clear()
        informe, codigo = guion.calcular(app, _plan())
        assert codigo == 0, informe
        assert not app.proyecto.GetContents('*.ComTransfer', 1)
        assert not app.proyecto.GetContents('*.ElmBoundary', 1)
        assert not [s for s in app.proyecto.GetContents('*.SetSelect', 1)
                    if s.loc_name.startswith(guion.NOMBRE_TC)]
        assert all((getattr(c, 'scale0', 1.0) or 1.0) == 1.0
                   for c in app.proyecto.GetContents('*.ElmLod', 1))
        escalado = [e for e in app.escrituras if e[1] == 'scale0']
        assert all(e[4] is None for e in escalado)


def test_capacidad_sin_seccionador_viable_no_se_calcula():
    """011:RF-122 — sin seccionador viable no hay configuración en la que medir el enlace."""
    app, _ = _red(random.Random(14), n=3)
    app.ldf = _flujo(app, capacidad_kw=10_000.0)
    informe, codigo = guion.calcular(app, _plan())
    assert codigo == 0, informe
    assert _capacidad_de(informe) is None
