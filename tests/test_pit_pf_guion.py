"""Spec 107 T12 — ``tools/pit_pf.py`` con el doble de DIgSILENT (``tests/fake_pf.py``) (107:RF-2, RF-3, RF-5)."""
from __future__ import annotations

import dataclasses

import pytest

from apoyo import cargar_herramienta
from datos_pit import perfil_a
from fake_pf import Obj

from convertersmartgrid.dominio.pit import PitError
from convertersmartgrid.dominio.pit.ambito import AreaPit, areas_del_perfil, reunir
from convertersmartgrid.aplicacion.pit.red_area import desde_ambito
from convertersmartgrid.adaptadores.pit.red_pandapower import calcular, referencias

guion = cargar_herramienta('pit_pf.py', 'pit_pf_t12', tools_en_path=True)


class _Cub:
    def __init__(self, barra):
        self._b = barra

    def GetParent(self):
        return self._b


class _Orden(Obj):
    def Execute(self):
        self._app_doble.ejecutadas.append(self.loc_name)
        if self._app_doble.cambia_demanda:
            self._app_doble.carga.plini += 1.0
        return 0

    def GetAttribute(self, attr):
        return 1.5


class _Caso(Obj):
    def Activate(self):
        self._app_doble.activo = self


class _Carpeta:
    def __init__(self, hijos):
        self._hijos = hijos

    def GetContents(self, *_a):
        return list(self._hijos)


class _App:
    """Un proyecto de transmisión hecho con los elementos del caso sintético A."""

    def __init__(self, caso, *, cambia_demanda=False):
        self.cambia_demanda, self.ejecutadas = cambia_demanda, []
        el = {t: [e for e in caso['elementos'] if e['tipo'] == t] for t in ('barra', 'red_externa', 'linea', 'trafo2')}
        self.b = {e['id']: Obj(None, 'ElmTerm', e['id'], uknom=e['kv']) for e in el['barra']}
        self.objetos = {'*.ElmTerm': list(self.b.values()), '*.ElmTr3': [], '*.ElmShnt': [],
                        '*.ElmXnet': [Obj(None, 'ElmXnet', g['id'], bus1=_Cub(self.b[g['barra']]), usetp=g['vm_pu'])
                                      for g in el['red_externa']],
                        '*.ElmLne': [], '*.ElmTr2': []}
        for e in el['linea']:
            if e['desde'] not in self.b or e['hasta'] not in self.b:
                continue
            tipo = Obj(None, 'TypLne', 't', uline=e['kv'], rline=e['r_ohm_per_km'], xline=e['x_ohm_per_km'],
                       cline=e['c_nf_per_km'] / 1000, sline=e['max_i_ka'])
            self.objetos['*.ElmLne'].append(Obj(None, 'ElmLne', e['id'], typ_id=tipo, dline=e['longitud_km'],
                                                bus1=_Cub(self.b[e['desde']]), bus2=_Cub(self.b[e['hasta']])))
        for e in el['trafo2']:
            tipo = Obj(None, 'TypTr2', 't', strn=e['sn_mva'], utrn_h=e['vn_hv_kv'], utrn_l=e['vn_lv_kv'],
                       uktr=e['vk_percent'], pcutr=e['vkr_percent'] * e['sn_mva'] * 10, pfe=e['pfe_kw'],
                       curmg=e['i0_percent'])
            self.objetos['*.ElmTr2'].append(Obj(None, 'ElmTr2', e['id'], typ_id=tipo, bushv=_Cub(self.b[e['hv']]),
                                                buslv=_Cub(self.b[e['lv']])))
        self.carga = Obj(None, 'ElmLod', 'carga', plini=5.0, qlini=1.0)
        self.objetos['*.ElmLod'] = [self.carga]
        self.casos = [_Caso(None, 'IntCase', f'C{a}', _app_doble=self) for a in caso['anios']]
        self.activo = self.casos[0]
        self.ordenes = {c: _Orden(None, c, c, _app_doble=self) for c in guion.ESTUDIOS}

    def GetCalcRelevantObjects(self, patron):
        # Como DIgSILENT: una clase que el proyecto no tiene da una lista vacía.
        return self.objetos.get(patron, [])

    def GetActiveStudyCase(self):
        return self.activo

    def GetProjectFolder(self, nombre):
        return _Carpeta(self.casos if nombre == 'study' else [])

    def GetFromStudyCase(self, clase):
        return self.ordenes[clase]


def test_help_sin_digsilent(capsys):
    """107:RF-2 — el guion dice para qué sirve sin necesitar DIgSILENT."""
    with pytest.raises(SystemExit) as fin:
        guion.main(['--help'])
    assert fin.value.code == 0 and '--exportar-red' in capsys.readouterr().out


def test_exportar_red_al_contrato_y_converge_con_el_motor_abierto():
    """107:RF-2, 107:RF-5 — la red exportada entra en RedArea y la misma red converge con pandapower."""
    caso = perfil_a(33)
    # DIgSILENT no dice a qué SET pertenece una barra: el ámbito se toma desde la media tensión de la copia.
    area = dataclasses.replace(areas_del_perfil(caso['perfil'], caso['area'])[0],
                               tension_min_kv=min(e['kv'] for e in caso['elementos'] if e['tipo'] == 'barra'))
    plan = {'project': 'copia', 'area': caso['area'], 'titular': caso['pistas']['titulares'][0]}
    elementos = guion.exportar_red(_App(caso), plan)
    red = desde_ambito(reunir(area, elementos))
    assert not red.faltantes and red.de_tipo('trafo2') and red.de_tipo('linea')
    assert all(e['fuente']['proyecto'] == 'copia' for t in red.elementos.values() for e in t)
    # ROJO-INVÁLIDO (c3): sin su red externa, pandapower lanza «No reference bus» antes de cualquier aserción.
    assert red.de_tipo('red_externa'), 'la red exportada no trae su red externa de referencia'
    r = calcular(red, {f'B-{s}-MT': (1.0, 0.3) for s in caso['pistas']['sets']})
    assert r.converge


def test_estudios_por_anio_sin_dejar_nada_cambiado():
    """107:RF-3 — ComLdf, ComSimoutage y ComRel3 en el caso de cada año; nada queda cambiado."""
    caso = perfil_a(33)
    app = _App(caso)
    plan = {'anios': {str(a): f'C{a}' for a in caso['anios']}, 'estudios': list(guion.ESTUDIOS)}
    informe, codigo = guion.estudiar(app, plan)
    assert codigo == 0 and informe['cambios'] == [] and informe['motor'] == 'digsilent'
    assert app.ejecutadas == list(guion.ESTUDIOS) * len(caso['anios'])
    assert app.activo is app.casos[0]


def test_un_estudio_que_cambia_la_demanda_se_dice():
    """107:RF-3 — si algo queda cambiado, el informe lo nombra y el guion sale con 2."""
    caso = perfil_a(33)
    informe, codigo = guion.estudiar(_App(caso, cambia_demanda=True),
                                     {'anios': {str(caso['anios'][0]): f'C{caso["anios"][0]}'}, 'estudios': ['ComLdf']})
    assert codigo == 2 and 'la demanda de carga' in informe['error']


def _red_exportada(caso, app=None):
    """La red del área a partir de lo que exporta el guion, con el ámbito desde la media tensión de la copia."""
    area = dataclasses.replace(areas_del_perfil(caso['perfil'], caso['area'])[0],
                               tension_min_kv=min(e['kv'] for e in caso['elementos'] if e['tipo'] == 'barra'))
    plan = {'project': 'copia', 'area': caso['area'], 'titular': caso['pistas']['titulares'][0]}
    return desde_ambito(reunir(area, guion.exportar_red(app or _App(caso), plan)))


def _otra_red_externa(app, caso, **attrs):
    """Una segunda red externa, en la barra de AT de la primera SET (un segundo punto de entrega)."""
    barra = app.b[f'B-{caso["pistas"]["sets"][0]}-AT']
    app.objetos['*.ElmXnet'].append(Obj(None, 'ElmXnet', 'RE-2', bus1=_Cub(barra), usetp=1.0, **attrs))
    return barra.loc_name


def _flujo(red, caso):
    """El resultado del flujo, o la excepción que lanza: la prueba falla por su aserción y no por un error."""
    try:
        return calcular(red, {f'B-{s}-MT': (1.0, 0.3) for s in caso['pistas']['sets']})
    except Exception as exc:  # noqa: BLE001 - justificado: la aserción dice qué excepción salió
        return exc


def test_la_red_exportada_lleva_su_barra_de_suministro_como_referencia():
    """107:RF-3 — la red externa sale con la tensión de su barra y llega a la red del área como su referencia."""
    caso = perfil_a(33)
    fuente = next(e for e in caso['elementos'] if e['tipo'] == 'red_externa')
    red = _red_exportada(caso)
    assert [(g['id'], g['barra'], g.get('kv')) for g in red.de_tipo('red_externa')] == \
        [(fuente['id'], fuente['barra'], fuente['kv'])]
    r = _flujo(red, caso)
    assert not isinstance(r, Exception) and r.converge
    assert r.tensiones_pu[fuente['barra']] == pytest.approx(fuente['vm_pu'])


def test_la_compensacion_exportada_lleva_la_tension_de_su_barra():
    """107:RF-2 — un banco de DIgSILENT no tiene tensión propia: sale con la de su barra y no se cae del ámbito."""
    caso = perfil_a(33)
    app = _App(caso)
    barra = app.b[f'B-{caso["pistas"]["sets"][0]}-MT']
    app.objetos['*.ElmShnt'].append(Obj(None, 'ElmShnt', 'Q-1', bus1=_Cub(barra), qcapn=2.0))
    red = _red_exportada(caso, app)
    assert [(q['id'], q['barra'], q.get('kv')) for q in red.de_tipo('compensacion')] == \
        [('Q-1', barra.loc_name, barra.uknom)]


def test_sin_barra_de_suministro_se_dice():
    """107:RF-3, 107:RF-4 — sin red externa no hay referencia: un PitError que lo nombra, no el error de pandapower."""
    caso = perfil_a(33)
    app = _App(caso)
    app.objetos['*.ElmXnet'] = []
    err = _flujo(_red_exportada(caso, app), caso)
    assert isinstance(err, PitError) and 'barra de suministro' in str(err)


def test_varias_redes_externas_sin_declarar_la_referencia_se_dice():
    """107:RF-3, 107:RF-4 — con dos puntos de entrega y sin su tipo de barra, no se toma el primero: se pide declararlo."""
    caso = perfil_a(33)
    app = _App(caso)
    _otra_red_externa(app, caso)
    err = _flujo(_red_exportada(caso, app), caso)
    assert isinstance(err, PitError) and 'no declara su tipo de barra' in str(err) and 'RE-2' in str(err)


def test_varias_redes_externas_declaradas_de_referencia_convergen():
    """107:RF-3 — las redes externas que DIgSILENT declara SL son todas la referencia, cada una con su consigna."""
    caso = perfil_a(33)
    app = _App(caso)
    for g in app.objetos['*.ElmXnet']:
        object.__setattr__(g, 'bustp', 'SL')
    otra = _otra_red_externa(app, caso, bustp='SL')
    red = _red_exportada(caso, app)
    assert sorted(g['id'] for g in red.de_tipo('red_externa')) == sorted([f'RE-{caso["area"]}', 'RE-2'])
    r = _flujo(red, caso)
    assert not isinstance(r, Exception) and r.converge and r.tensiones_pu[otra] == pytest.approx(1.0)


def test_una_red_externa_pv_se_dice():
    """107:RF-3, 107:RF-4 — el PIT no modela una red externa PV: se nombra en vez de tratarla como referencia."""
    caso = perfil_a(33)
    app = _App(caso)
    for g in app.objetos['*.ElmXnet']:
        object.__setattr__(g, 'bustp', 'SL')
    _otra_red_externa(app, caso, bustp='PV')
    err = _flujo(_red_exportada(caso, app), caso)
    assert isinstance(err, PitError) and 'RE-2 (PV)' in str(err)

# --- 107:RF-25: un proyecto de transmisión sintético (107 T44) -------------------------------------------------------
# Dos subestaciones sintéticas (SX y SY) con las mismas barras «1», «2» y «3», como en un proyecto de transmisión; en
# cada una, un acoplamiento cerrado «A12» une la barra «1» con la «2» (y en SX otro abierto en paralelo). La referencia
# del flujo es una máquina (ip_ctrl) y la red externa es PQ con su consigna.

_AREA_T = AreaPit('AREA-T', ('TIT-T',), (), {}, 60.0, {})
_PLAN_T = {'project': 'copia', 'area': 'AREA-T', 'titular': 'TIT-T'}


class _OrdenLdf(Obj):
    """El ComLdf del doble: deja una tensión por barra y una cargabilidad por rama, distintas en cada elemento."""

    def Execute(self):
        app = self._app_doble
        for i, b in enumerate(app.objetos['*.ElmTerm']):
            object.__setattr__(b, 'm_u', 1.0 - 0.001 * i)
        for i, o in enumerate(app.objetos['*.ElmLne'] + app.objetos['*.ElmTr2']):
            object.__setattr__(o, 'c:loading', 10.0 + i)
        return 0


class _AppTransmision:
    def __init__(self, *, maquina_referencia=True):
        red = Obj(None, 'ElmNet', 'RED')
        subs = {s: Obj(None, 'ElmSubstat', s, red) for s in ('SX', 'SY')}
        self.b = {(s, n): Obj(None, 'ElmTerm', n, sub, uknom=kv)
                  for s, sub in subs.items() for n, kv in (('1', 220.0), ('2', 220.0), ('3', 60.0))}
        tl = Obj(None, 'TypLne', 't', uline=220.0, rline=0.05, xline=0.4, cline=0.009, sline=1.0)
        tt = Obj(None, 'TypTr2', 't', strn=100.0, utrn_h=220.0, utrn_l=60.0, uktr=12.0, pcutr=300.0, pfe=50.0,
                 curmg=0.1)
        cub = {k: _Cub(v) for k, v in self.b.items()}
        acoples = [Obj(None, 'ElmCoup', 'A12', subs[s], on_off=1, bus1=_Cub(self.b[(s, '1')]),
                       bus2=_Cub(self.b[(s, '2')])) for s in subs]
        acoples.append(Obj(None, 'ElmCoup', 'A12b', subs['SX'], on_off=0, bus1=_Cub(self.b[('SX', '1')]),
                           bus2=_Cub(self.b[('SX', '2')])))
        maquinas = [Obj(None, 'ElmSym', 'G', subs['SX'], ip_ctrl=1 if maquina_referencia else 0, usetp=1.02,
                        bus1=cub[('SX', '1')]),
                    Obj(None, 'ElmSym', 'G', subs['SY'], ip_ctrl=0, usetp=1.0, bus1=cub[('SY', '1')])]
        self.cargas = [Obj(None, 'ElmLod', 'C', subs[s], plini=p, qlini=0.3 * p) for s, p in (('SX', 20.0), ('SY', 30.0))]
        self.objetos = {
            '*.ElmTerm': list(self.b.values()),
            '*.ElmLne': [Obj(None, 'ElmLne', 'L1', red, typ_id=tl, dline=80.0, bus1=cub[('SX', '1')],
                             bus2=cub[('SY', '1')])],
            '*.ElmTr2': [Obj(None, 'ElmTr2', 'T1', subs[s], typ_id=tt, bushv=_Cub(self.b[(s, '2')]),
                             buslv=_Cub(self.b[(s, '3')])) for s in subs],
            '*.ElmCoup': acoples, '*.ElmSym': maquinas, '*.ElmLod': self.cargas,
            '*.ElmXnet': [Obj(None, 'ElmXnet', 'EQ', subs['SY'], bustp='PQ', usetp=1.0, pgini=20.0, qgini=5.0,
                              bus1=cub[('SY', '1')])],
        }
        self.activo = _Caso(None, 'IntCase', 'C', _app_doble=self)
        self.ldf = _OrdenLdf(None, 'ComLdf', 'ComLdf', _app_doble=self)

    def GetCalcRelevantObjects(self, patron):
        return self.objetos.get(patron, [])

    def GetActiveStudyCase(self):
        return self.activo

    def GetProjectFolder(self, nombre):
        return _Carpeta([])

    def GetFromStudyCase(self, clase):
        return self.ldf


def _red_t(app=None):
    return desde_ambito(reunir(_AREA_T, guion.exportar_red(app or _AppTransmision(), _PLAN_T)))


def _cargas_t(app):
    """La demanda de cada carga del doble en la barra «3» de su subestación, por su id."""
    return {guion._id(app.b[(s, '3')]): (c.plini, c.qlini) for s, c in zip(('SX', 'SY'), app.cargas)}


def _flujo_t(red, app):
    try:
        return calcular(red, _cargas_t(app))
    except Exception as exc:  # noqa: BLE001 - justificado: la aserción dice qué excepción salió
        return exc


def test_cada_barra_de_cada_subestacion_tiene_su_id():
    """107:RF-25 — las barras «1», «2» y «3» de dos subestaciones son seis barras: id por su ruta desde la red, y el
    nombre aparte; las ramas se conectan a esos ids."""
    app = _AppTransmision()
    elementos = guion.exportar_red(app, _PLAN_T)
    ids = [e['id'] for e in elementos]
    assert len(ids) == len(set(ids)), f'ids repetidos: {sorted(i for i in ids if ids.count(i) > 1)}'
    barras = [e for e in elementos if e['tipo'] == 'barra']
    assert len(barras) == 6 and sorted({b['nombre'] for b in barras}) == ['1', '2', '3']
    assert 'RED.ElmNet/SX.ElmSubstat/1.ElmTerm' in {b['id'] for b in barras}
    linea = next(e for e in elementos if e['tipo'] == 'linea')
    assert (linea['desde'], linea['hasta']) == ('RED.ElmNet/SX.ElmSubstat/1.ElmTerm',
                                                'RED.ElmNet/SY.ElmSubstat/1.ElmTerm')


def test_ids_repetidos_en_la_exportacion_se_dicen():
    """107:RF-25 — si dos elementos quedan con el mismo id (fuera de una red), la exportación lo dice en vez de unirlos."""
    app = _App(perfil_a(33))
    app.objetos['*.ElmTerm'].append(Obj(None, 'ElmTerm', app.objetos['*.ElmTerm'][0].loc_name, uknom=60.0))
    with pytest.raises(ValueError, match='repite el id'):
        guion.exportar_red(app, {'project': 'copia', 'area': 'A', 'titular': 'T'})


def test_los_acoplamientos_cerrados_unen_las_barras_de_la_subestacion():
    """107:RF-25 — el ElmCoup sale como unión con su estado; cerrado, el motor abierto une sus dos barras y la barra
    partida no deja sin tensión a su transformador."""
    app = _AppTransmision()
    red = _red_t(app)
    uniones = {(u['nombre'], u['desde'].split('/')[1], u['cerrado']) for u in red.de_tipo('union')}
    assert uniones == {('A12', 'SX.ElmSubstat', True), ('A12', 'SY.ElmSubstat', True),
                       ('A12b', 'SX.ElmSubstat', False)}, uniones
    assert not red.faltantes, red.faltantes
    r = _flujo_t(red, app)
    assert not isinstance(r, Exception) and r.converge, r
    assert not r.sin_tension and len(r.tensiones_pu) == 6
    for s in ('SX', 'SY'):
        assert r.tensiones_pu[guion._id(app.b[(s, '1')])] == pytest.approx(r.tensiones_pu[guion._id(app.b[(s, '2')])])
    assert set(r.cargabilidad_pct) == {e['id'] for t in ('linea', 'trafo2') for e in red.de_tipo(t)}


def test_un_acoplamiento_sin_estado_queda_en_faltantes():
    """107:RF-25, 107:RF-4 — sin el estado del acoplamiento no se supone cerrado ni abierto."""
    app = _AppTransmision()
    object.__delattr__(app.objetos['*.ElmCoup'][0], 'on_off')
    red = _red_t(app)
    assert [(f['tipo'], f['falta']) for f in red.faltantes] == [('union', ['cerrado'])]


def test_la_maquina_de_referencia_es_la_referencia_y_la_red_externa_pq_entra_con_su_consigna():
    """107:RF-25 — sin red externa SL, la máquina que DIgSILENT declara de referencia (ip_ctrl) es la barra de
    suministro, con su consigna de tensión; la red externa PQ entra como inyección con su consigna."""
    app = _AppTransmision()
    red = _red_t(app)
    refs = [(g['nombre'], g.get('tipo_barra'), g['barra']) for g in red.de_tipo('red_externa')
            if g.get('maquina_referencia')]
    assert refs == [('G', 'SL', guion._id(app.b[('SX', '1')]))], refs
    assert [g['nombre'] for g in referencias(red)] == ['G']
    eq = next(g for g in red.de_tipo('red_externa') if g['nombre'] == 'EQ')
    assert (eq['tipo_barra'], eq['p_mw'], eq['q_mvar']) == ('PQ', 20.0, 5.0)
    r = _flujo_t(red, app)
    assert not isinstance(r, Exception) and r.converge, r
    assert r.tensiones_pu[guion._id(app.b[('SX', '1')])] == pytest.approx(1.02)


def test_sin_red_externa_sl_ni_maquina_de_referencia_se_dice():
    """107:RF-25, 107:RF-3 — una red externa PQ sola no es la referencia: el error nombra que falta la máquina."""
    app = _AppTransmision(maquina_referencia=False)
    err = _flujo_t(_red_t(app), app)
    assert isinstance(err, PitError) and 'máquina de referencia' in str(err) and 'EQ.ElmXnet (PQ)' in str(err), err


def test_los_resultados_de_digsilent_y_del_motor_abierto_se_emparejan_por_id():
    """107:RF-25 — ComLdf da una tensión por barra y una cargabilidad por rama con los ids de la red exportada, y el
    motor abierto da las mismas claves."""
    app = _AppTransmision()
    red = _red_t(app)
    ldf = guion._ejecutar(app, 'ComLdf')
    assert set(ldf['tensiones_pu']) == {b['id'] for b in red.de_tipo('barra')}
    assert len(ldf['tensiones_pu']) == 6
    assert set(ldf['cargabilidad_pct']) == {e['id'] for t in ('linea', 'trafo2') for e in red.de_tipo(t)}
    assert len(ldf['cargabilidad_pct']) == 3
    r = _flujo_t(red, app)
    assert not isinstance(r, Exception) and r.converge, r
    assert set(r.tensiones_pu) == set(ldf['tensiones_pu']) and set(r.cargabilidad_pct) == set(ldf['cargabilidad_pct'])


def test_el_estado_del_estudio_distingue_cargas_con_el_mismo_nombre():
    """107:RF-25 — las dos cargas «C» son dos en el estado que se compara antes y después del estudio."""
    assert len(guion.estado(_AppTransmision())['demandas']) == 2


# --- 107:RF-26: las ramas serie de un proyecto de transmisión (corrida de 107 T14 del 21-11) --------------------------
# En la copia de transmisión, el Sur solo llega a la referencia por las líneas de 500 kV con condensadores serie
# (``ElmScap``): sin exportarlos quedaban sin suministro 1 499 barras con tensión en DIgSILENT y el flujo abierto no
# convergía. Aquí la línea L1 llega a una barra intermedia «M» y el condensador serie «BCS» la une con SY.

def _app_con_serie(*, con_reactancia=False):
    app = _AppTransmision()
    linea = app.objetos['*.ElmLne'][0]
    m = Obj(None, 'ElmTerm', 'M', linea.GetParent(), uknom=220.0)
    app.objetos['*.ElmTerm'].append(m)
    object.__setattr__(linea, 'bus2', _Cub(m))
    app.objetos['*.ElmScap'] = [Obj(None, 'ElmScap', 'BCS', m.GetParent(), xcap=30.0, ucn=220.0, Curn=1.5,
                                    bus1=_Cub(m), bus2=_Cub(app.b[('SY', '1')]))]
    if con_reactancia:
        app.objetos['*.ElmSind'] = [Obj(None, 'ElmSind', 'RS', m.GetParent(), rrea=0.2, xrea=4.0, ucn=220.0,
                                        bus1=_Cub(m), bus2=_Cub(app.b[('SY', '1')]))]
    return app


def test_el_condensador_serie_se_exporta_y_une_las_dos_subestaciones():
    """107:RF-26 — el ElmScap sale como rama serie con su reactancia capacitiva (X negativa, en ohmios); el motor
    abierto lo monta y la subestación que solo llega por él tiene tensión."""
    app = _app_con_serie()
    red = _red_t(app)
    serie = red.de_tipo('serie')
    assert [(s['nombre'], s['x_ohm'], s['r_ohm']) for s in serie] == [('BCS', -30.0, 0.0)], serie
    assert serie[0]['desde'] == guion._id(app.objetos['*.ElmTerm'][-1])
    assert serie[0]['hasta'] == guion._id(app.b[('SY', '1')])
    assert not red.faltantes, red.faltantes
    r = _flujo_t(red, app)
    assert not isinstance(r, Exception) and r.converge, r
    assert not r.sin_tension, r.sin_tension
    assert len(r.tensiones_pu) == 7


def test_la_reactancia_serie_se_exporta_con_su_resistencia_y_su_reactancia():
    """107:RF-26 — el ElmSind sale como rama serie con su R y su X (ohmios), y una rama serie fuera de servicio no se
    exporta."""
    app = _app_con_serie(con_reactancia=True)
    object.__setattr__(app.objetos['*.ElmScap'][0], 'outserv', 1)
    red = _red_t(app)
    assert [(s['nombre'], s['r_ohm'], s['x_ohm']) for s in red.de_tipo('serie')] == [('RS', 0.2, 4.0)]
    r = _flujo_t(red, app)
    assert not isinstance(r, Exception) and r.converge and not r.sin_tension, r


def test_una_rama_serie_sin_reactancia_queda_en_faltantes():
    """107:RF-26, 107:RF-4 — sin su reactancia no se supone: la rama serie queda en faltantes, nombrada."""
    app = _app_con_serie()
    object.__setattr__(app.objetos['*.ElmScap'][0], 'xcap', None)
    red = _red_t(app)
    assert [(f['tipo'], f['falta']) for f in red.faltantes if f['tipo'] == 'serie'] == [('serie', ['x_ohm'])], red.faltantes
