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
        app.flujos = getattr(app, 'flujos', 0) + 1
        if getattr(app, 'ldf_falla', False):
            return 1
        # Repetir el flujo sobre el mismo caso da lo mismo que el anterior: lo que una prueba dejó resuelto no cambia.
        for i, b in enumerate(app.objetos['*.ElmTerm']):
            if getattr(b, 'm:u', None) is None and getattr(b, 'm_u', None) is None:
                object.__setattr__(b, 'm_u', 1.0 - 0.001 * i)
        for i, o in enumerate(app.objetos['*.ElmLne'] + app.objetos['*.ElmTr2']):
            object.__setattr__(o, 'c:loading', 10.0 + i)
        # 107:RF-43: como en DIgSILENT, lo resuelto (los límites de Q de un SVC con la tensión, c:Qmin y c:Qmax) solo
        # existe después del flujo.
        for s in app.objetos.get('*.ElmSvs', []):
            for k, v in (getattr(s, 'tras_flujo', None) or {}).items():
                object.__setattr__(s, k, v)
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


# --- 107:RF-27: unidades, paralelos, cubículos, tomas, compensaciones y fuera de servicio (corrida de 107 T14, 22-11) -
# En la copia de transmisión: «cline» en nF/km por las unidades del proyecto (se tomaba como µF/km: 1 000 veces la
# capacidad), trafos con hasta 67 unidades en paralelo exportados como una, 68 lados con su interruptor de cubículo abierto
# exportados como conectados, las reactancias en derivación con Q 0 (se leía «qcapn») y las tomas sin exportar.

class _TipoConUnidad(Obj):
    """Un TypLne que dice la unidad de su capacitancia, como ``GetAttributeUnit`` de DIgSILENT."""

    def GetAttributeUnit(self, attr):
        return self._unidades.get(attr, '')


class _CubConInterruptor(_Cub):
    def __init__(self, barra, *, abierto):
        super().__init__(barra)
        self._sw = [Obj(None, 'StaSwitch', 'SW', on_off=0 if abierto else 1)]

    def GetContents(self, patron='*'):
        return list(self._sw) if 'StaSwitch' in patron else []


def _linea_l1(app):
    return app.objetos['*.ElmLne'][0]


def test_la_capacitancia_se_convierte_desde_la_unidad_que_declara_el_proyecto():
    """107:RF-27 — «cline» en nF/km sale tal cual y en µF/km por 1 000; con la frecuencia del tipo (frnom)."""
    for unidad, cline, esperado in (('nF/km', 9.0, 9.0), ('uF/km', 0.009, 9.0)):
        app = _AppTransmision()
        t = _TipoConUnidad(None, 'TypLne', 't', uline=220.0, rline=0.05, xline=0.4, cline=cline, sline=1.0, frnom=60.0)
        object.__setattr__(t, '_unidades', {'cline': unidad})
        object.__setattr__(_linea_l1(app), 'typ_id', t)
        ln = next(e for e in guion.exportar_red(app, _PLAN_T) if e['tipo'] == 'linea')
        assert ln['c_nf_per_km'] == pytest.approx(esperado), (unidad, ln)
        assert ln['f_hz'] == 60.0


def test_las_unidades_en_paralelo_se_exportan_y_el_motor_abierto_las_cuenta():
    """107:RF-27 — ntnum del trafo y nlnum de la línea salen como «paralelo»; con dos trafos en paralelo la
    cargabilidad de cada uno es la mitad."""
    base = _AppTransmision()
    r1 = _flujo_t(_red_t(base), base)
    app = _AppTransmision()
    for tr in app.objetos['*.ElmTr2']:
        object.__setattr__(tr, 'ntnum', 2)
    object.__setattr__(_linea_l1(app), 'nlnum', 2)
    red = _red_t(app)
    assert {e.get('paralelo') for e in red.de_tipo('trafo2')} == {2}
    assert [e.get('paralelo') for e in red.de_tipo('linea')] == [2]
    r2 = _flujo_t(red, app)
    assert r2.converge and r1.converge
    for e in red.de_tipo('trafo2'):
        assert r2.cargabilidad_pct[e['id']] == pytest.approx(r1.cargabilidad_pct[e['id']] / 2, rel=0.05)


def test_un_interruptor_de_cubiculo_abierto_deja_la_rama_desconectada_de_ese_lado():
    """107:RF-27 — el StaSwitch abierto del cubículo de un lado sale como «abierto_en» y la rama no lleva flujo."""
    app = _AppTransmision()
    ln = _linea_l1(app)
    object.__setattr__(ln, 'bus2', _CubConInterruptor(app.b[('SY', '1')], abierto=True))
    red = _red_t(app)
    assert [e.get('abierto_en') for e in red.de_tipo('linea')] == [['hasta']]
    r = _flujo_t(red, app)
    assert not isinstance(r, Exception) and r.converge, r
    # Abierta en un extremo solo lleva su corriente de carga: sin potencia activa.
    assert abs(r.flujos.get(guion._id(ln), (0.0, 0.0))[0]) < 0.05, r.flujos.get(guion._id(ln))


def test_la_toma_del_trafo_se_exporta_y_cambia_la_tension_de_su_lado():
    """107:RF-27 — nntap, dutap, nntap0 y el lado de la toma salen al contrato y el motor abierto los aplica."""
    base = _AppTransmision()
    r1 = _flujo_t(_red_t(base), base)
    app = _AppTransmision()
    tipo = Obj(None, 'TypTr2', 't', strn=100.0, utrn_h=220.0, utrn_l=60.0, uktr=12.0, pcutr=300.0, pfe=50.0, curmg=0.1,
               dutap=2.5, nntap0=0, ntpmn=-5, ntpmx=5, tap_side=0)
    for tr in app.objetos['*.ElmTr2']:
        object.__setattr__(tr, 'typ_id', tipo)
        object.__setattr__(tr, 'nntap', 2)
    red = _red_t(app)
    t = red.de_tipo('trafo2')[0]
    assert (t.get('tap_pos'), t.get('tap_neutral'), t.get('tap_step_percent'), t.get('tap_side')) == (2, 0, 2.5, 'hv')
    r2 = _flujo_t(red, app)
    b3 = guion._id(app.b[('SY', '3')])
    assert abs(r2.tensiones_pu[b3] - r1.tensiones_pu[b3]) > 0.01


def test_la_reactancia_en_derivacion_absorbe_su_q_real_y_lo_fuera_de_servicio_no_se_exporta():
    """107:RF-27 — la compensación sale con su Q real (Qact, con sus escalones); la reactancia (shtype 1) inductiva.
    Una línea fuera de servicio no se exporta."""
    app = _AppTransmision()
    app.objetos['*.ElmShnt'] = [
        Obj(None, 'ElmShnt', 'R', app.b[('SY', '1')].GetParent(), shtype=1, qcapn=0.0, qrean=10.0, Qact=20.0, ncapa=2,
            bus1=_Cub(app.b[('SY', '1')])),
        Obj(None, 'ElmShnt', 'C', app.b[('SX', '3')].GetParent(), shtype=2, qcapn=5.0, Qact=5.0, ncapa=1,
            bus1=_Cub(app.b[('SX', '3')]))]
    otra = Obj(None, 'ElmLne', 'L2', _linea_l1(app).GetParent(), typ_id=_linea_l1(app).typ_id, dline=10.0, outserv=1,
               bus1=_Cub(app.b[('SX', '1')]), bus2=_Cub(app.b[('SY', '1')]))
    app.objetos['*.ElmLne'].append(otra)
    exportada = guion.exportar_red(app, _PLAN_T)
    q = {e['nombre']: e['q_mvar'] for e in exportada if e['tipo'] == 'compensacion'}
    assert q == {'R': -20.0, 'C': 5.0}, q
    assert [e['nombre'] for e in exportada if e['tipo'] == 'linea'] == ['L1']


def test_la_compensacion_con_otra_nominal_sale_con_su_q_en_la_nominal_de_la_barra():
    """107:RF-39 — la Q de una compensación con tensión nominal propia (ushnm) distinta de la de su barra sale referida a
    la nominal de la barra, (kV de la barra / ushnm)²: el motor abierto la monta con la nominal de la barra. Sin
    ushnm, como antes. (Copia de transmisión: una reactancia de 10 Mvar a 145 kV en una barra de 138 kV y unos
    condensadores de 11,25 Mvar a 11,5 kV en una de 10,5 kV.)"""
    app = _AppTransmision()
    kv = app.b[('SY', '1')].uknom
    app.objetos['*.ElmShnt'] = [
        Obj(None, 'ElmShnt', 'R', app.b[('SY', '1')].GetParent(), shtype=1, qcapn=0.0, qrean=10.0, Qact=10.0,
            ushnm=kv * 145.0 / 138.0, bus1=_Cub(app.b[('SY', '1')])),
        Obj(None, 'ElmShnt', 'C', app.b[('SX', '3')].GetParent(), shtype=2, qcapn=3.75, Qact=11.25,
            ushnm=app.b[('SX', '3')].uknom * 11.5 / 10.5, bus1=_Cub(app.b[('SX', '3')])),
        Obj(None, 'ElmShnt', 'S', app.b[('SX', '3')].GetParent(), shtype=2, qcapn=2.0, Qact=2.0,
            bus1=_Cub(app.b[('SX', '3')]))]
    q = {e['nombre']: e['q_mvar'] for e in guion.exportar_red(app, _PLAN_T) if e['tipo'] == 'compensacion'}
    assert q['R'] == pytest.approx(-10.0 * (138.0 / 145.0) ** 2), q
    assert q['C'] == pytest.approx(11.25 * (10.5 / 11.5) ** 2), q
    assert q['S'] == 2.0, q


def test_rf42_con_el_flujo_hecho_la_compensacion_sale_con_su_admitancia_resuelta():
    """107:RF-42 — con el flujo de DIgSILENT hecho (m:Q de la compensación y m:u de su barra), la Q en la nominal de la
    barra es −m:Q/u², sea cual sea el tipo de filtro; sin resultados, la de RF-27 y RF-39. (Copia de transmisión: dos
    filtros amortiguados de 3,5.º armónico daban 11,19 Mvar a 1,0594 p.u. con una Qact que a esa tensión son 9,22.)"""
    app = _AppTransmision()
    barra = app.b[('SX', '3')]
    setattr(barra, 'm:u', 1.0594)
    app.objetos['*.ElmShnt'] = [
        Obj(None, 'ElmShnt', 'F', barra.GetParent(), shtype=4, qcapn=7.745, Qact=8.21, bus1=_Cub(barra),
            **{'m_Q:bus1': -11.193}),
        Obj(None, 'ElmShnt', 'R', barra.GetParent(), shtype=1, qrean=10.0, Qact=10.0, bus1=_Cub(barra),
            **{'m_Q:bus1': 11.2236}),
        Obj(None, 'ElmShnt', 'S', app.b[('SY', '1')].GetParent(), shtype=2, qcapn=2.0, Qact=2.0,
            bus1=_Cub(app.b[('SY', '1')]))]
    q = {e['nombre']: e['q_mvar'] for e in guion.exportar_red(app, _PLAN_T) if e['tipo'] == 'compensacion'}
    assert q['F'] == pytest.approx(11.193 / 1.0594 ** 2), q
    assert q['R'] == pytest.approx(-11.2236 / 1.0594 ** 2), q
    assert q['S'] == 2.0, q


# --- 107:RF-28: los SVC como nudos PV y el desfase de los grupos de conexión (corrida de 107 T14, 22-11) --------------
# En la copia de transmisión hay 13 SVC (hasta 315 Mvar en 500 kV) que regulan la tensión de su barra y no se exportaban;
# y los trafos tienen grupos de 1, 5, 7 y 11 h: DIgSILENT da en baja el ángulo de alta menos 30° × grupo horario
# (verificado con «tr2 cal_671», grupo 5: −46,6° en alta y 163,4° en baja).


def test_el_svc_se_exporta_como_nudo_pv_con_su_consigna_y_sus_limites():
    """107:RF-28 — el ElmSvs en servicio sale como red externa PV sin potencia activa, con la consigna de tensión
    (usetp) y sus límites de Q; el motor abierto mantiene la tensión de su barra en la consigna."""
    app = _AppTransmision()
    barra = app.b[('SY', '3')]
    app.objetos['*.ElmSvs'] = [Obj(None, 'ElmSvs', 'SVC', barra.GetParent(), usetp=1.01, qmax=40.0, qmin=30.0,
                                   bus1=_Cub(barra), tras_flujo={'c:Qmin': -30.0, 'c:Qmax': 40.0})]
    red = _red_t(app)
    svc = [e for e in red.de_tipo('red_externa') if e['nombre'] == 'SVC']
    assert len(svc) == 1, red.de_tipo('red_externa')
    s = svc[0]
    assert (s['tipo_barra'], s['p_mw'], s['vm_pu'], s['q_max_mvar'], s['q_min_mvar']) == ('PV', 0.0, 1.01, 40.0, -30.0)
    r = _flujo_t(red, app)
    assert not isinstance(r, Exception) and r.converge, r
    assert r.tensiones_pu[guion._id(barra)] == pytest.approx(1.01, abs=1e-6)


def test_el_desfase_del_grupo_de_conexion_se_exporta_y_lo_usa_el_motor_abierto():
    """107:RF-28 — nt2ag del trafo de dos devanados y nt3ag de cada devanado del de tres salen como desfase en grados
    (30° × grupo horario, relativo a alta), y el motor abierto los lleva a la red de pandapower."""
    from convertersmartgrid.adaptadores.pit import red_pandapower as rp
    import pandapower as pp

    app = _AppTransmision()
    for tr in app.objetos['*.ElmTr2']:
        object.__setattr__(tr.typ_id, 'nt2ag', 5.0)
    red = _red_t(app)
    assert {e.get('shift_degree') for e in red.de_tipo('trafo2')} == {150.0}
    net, _bus, _l, trafos, _t3 = rp._red(pp, red, _cargas_t(app), set())
    assert set(net.trafo.shift_degree.round(6)) == {150.0}
    r = _flujo_t(red, app)
    assert not isinstance(r, Exception) and r.converge, r
    tipo3 = Obj(None, 'TypTr3', 't3', nt3ag_h=0.0, nt3ag_m=0.0, nt3ag_l=11.0)
    tr3 = Obj(None, 'ElmTr3', 'T3', typ_id=tipo3)
    assert guion._desfases_tr3(tipo3) == {'shift_mv_degree': 0.0, 'shift_lv_degree': 330.0}
    assert tr3.typ_id is tipo3


# --- 107:RF-29: una nominal común por zona galvánica (corrida de 107 T14, 22-11) ---------------------------------------
# En la copia de transmisión, 275 líneas unen barras de nominal distinta (220 y 221 kV, 60 y 62,4 kV…); pandapower trabaja
# en por unidad de cada barra y esa línea hacía de transformador ideal 220/221: miles de Mvar y el flujo no convergía.

def _red_vn(kv_b, *, carga_mw=10.0):
    area = AreaPit('AREA-VN', ('TIT',), (), {}, 0.0, {})
    comun = {'areas': ['AREA-VN'], 'titular': 'TIT'}
    elementos = [{'id': 'A', 'tipo': 'barra', 'kv': 220.0, **comun},
                 {'id': 'B', 'tipo': 'barra', 'kv': kv_b, **comun},
                 {'id': 'EXT', 'tipo': 'red_externa', 'barra': 'A', 'kv': 220.0, 'vm_pu': 1.0, 'tipo_barra': 'SL', **comun},
                 {'id': 'L', 'tipo': 'linea', 'desde': 'A', 'hasta': 'B', 'kv': 220.0, 'longitud_km': 0.1,
                  'r_ohm_per_km': 0.026, 'x_ohm_per_km': 0.21, 'c_nf_per_km': 0.0, 'max_i_ka': 1.0, **comun}]
    return desde_ambito(reunir(area, elementos)), {'B': (carga_mw, 0.0)}


def test_dos_barras_de_nominal_distinta_unidas_por_una_linea_estan_a_la_misma_tension_en_kv():
    """107:RF-29 — una línea corta entre una barra de 220 kV y otra de 221 kV: la de 221 queda a la misma tensión en kV
    que la de 220 (salvo la caída de la línea), es decir a 220/221 en su propia nominal, y la cargabilidad es la de la
    corriente de la carga."""
    red, cargas = _red_vn(221.0)
    r = calcular(red, cargas)
    assert r.converge, r.mensaje
    assert r.tensiones_pu['A'] == pytest.approx(1.0, abs=1e-9)
    assert r.tensiones_pu['B'] == pytest.approx(220.0 / 221.0, abs=2e-4), r.tensiones_pu
    # 10 MW a 220 kV: unos 26 A de 1 kA.
    assert r.cargabilidad_pct['L'] == pytest.approx(2.62, abs=0.1), r.cargabilidad_pct


def test_con_la_misma_nominal_la_red_no_cambia():
    """107:RF-29 — con las dos barras a 220 kV el resultado es el de siempre: la barra B a 1 p.u. menos la caída."""
    red, cargas = _red_vn(220.0)
    r = calcular(red, cargas)
    assert r.converge and r.tensiones_pu['B'] == pytest.approx(1.0, abs=2e-4)


# --- 107:RF-30: la impedancia dependiente de la toma del trafo de tres devanados (corrida de 107 T14, 22-11) -----------
# En la copia de transmisión, un trafo de tres devanados de prueba tenía en su tipo ``itapzdep`` = 1 y estaba en la toma
# máxima del lado de alta: DIgSILENT usaba las vk de esa toma (``uktr3mx_*``) y no las nominales (``uktr3_*``), y el motor
# abierto, con las nominales, ponía el punto estrella junto a media en vez de junto a alta: ~460 MW de desajuste.

def _app_tr3(itapzdep, n3tap, itapos=1):
    app = _AppTransmision()
    tipo = Obj(None, 'TypTr3', 't3', strn3_h=240.0, strn3_m=240.0, strn3_l=80.0, utrn3_h=200.0, utrn3_m=62.46,
               utrn3_l=10.0, uktr3_h=12.6, uktr3_m=1.7, uktr3_l=6.8, uktrr3_h=0.28, uktrr3_m=0.16, uktrr3_l=0.17,
               uktr3mn_h=11.1, uktr3mn_m=10.1, uktr3mn_l=5.9, uktr3mx_h=11.9, uktr3mx_m=10.2, uktr3mx_l=4.6,
               uktrr3mn_h=0.8, uktrr3mn_m=0.5, uktrr3mn_l=0.9, uktrr3mx_h=0.8, uktrr3mx_m=0.5, uktrr3mx_l=0.9,
               pcut3_h=670.0, pcut3_m=125.0, pcut3_l=135.0, pfe=130.0, curm3=0.17, du3tp_h=5.0, n3tp0_h=0,
               n3tmn_h=-2, n3tmx_h=2, nt3ag_h=0.0, nt3ag_m=0.0, nt3ag_l=11.0, itapzdep=itapzdep, itapos=itapos)
    sub = app.b[('SY', '1')]._padre
    # La barra de baja a 66 kV: el ámbito del área de prueba empieza en 60 kV y una de 10 kV quedaría fuera con el trafo.
    bt = Obj(None, 'ElmTerm', '4', sub, uknom=66.0)
    app.objetos['*.ElmTerm'].append(bt)
    app.objetos['*.ElmTr3'] = [Obj(None, 'ElmTr3', 'T3', sub, typ_id=tipo, n3tap_h=n3tap,
                                   bushv=_Cub(app.b[('SY', '2')]), busmv=_Cub(app.b[('SY', '3')]), buslv=_Cub(bt))]
    return app


def _vk3(app):
    t = _red_t(app).de_tipo('trafo3')[0]
    return tuple(round(float(t.get(k)), 4) for k in ('vk_hv_percent', 'vk_mv_percent', 'vk_lv_percent',
                                                    'vkr_hv_percent', 'vkr_mv_percent', 'vkr_lv_percent'))


def test_con_impedancia_dependiente_de_la_toma_el_trafo3_sale_con_las_vk_de_su_toma():
    """107:RF-30 — con ``itapzdep`` = 1, en la toma máxima salen las vk y vkr de la toma máxima; en la mínima, las de
    la mínima; a medio camino entre el neutro y la máxima, el punto medio; en el neutro, las nominales."""
    assert _vk3(_app_tr3(1, 2)) == (11.9, 10.2, 4.6, 0.8, 0.5, 0.9)
    assert _vk3(_app_tr3(1, -2)) == (11.1, 10.1, 5.9, 0.8, 0.5, 0.9)
    assert _vk3(_app_tr3(1, 1))[:3] == (round((12.6 + 11.9) / 2, 4), round((1.7 + 10.2) / 2, 4),
                                         round((6.8 + 4.6) / 2, 4))
    assert _vk3(_app_tr3(1, 0))[:3] == (12.6, 1.7, 6.8)


def test_sin_impedancia_dependiente_de_la_toma_el_trafo3_sale_con_las_vk_nominales():
    """107:RF-30, 107:RF-38 — con ``itapzdep`` = 0 salen las vk nominales en el neutro, y fuera de él con la toma en el
    borne (``itapos`` = 1)."""
    assert _vk3(_app_tr3(0, 0))[:3] == (12.6, 1.7, 6.8)
    assert _vk3(_app_tr3(0, 2))[:3] == (12.6, 1.7, 6.8)


def _estrella(vk_hm, vk_ml, vk_lh, sn=(240.0, 240.0, 80.0)):
    """Las tres ramas de estrella en % sobre la potencia de alta, desde los pares en la base de cada par."""
    hm, ml, lh = vk_hm * sn[0] / min(sn[0], sn[1]), vk_ml * sn[0] / min(sn[1], sn[2]), vk_lh * sn[0] / min(sn[2], sn[0])
    return ((hm + lh - ml) / 2, (hm + ml - lh) / 2, (ml + lh - hm) / 2)


# --- 107:RF-38: la rama del devanado con toma en ohmios (corrida de 107 T14 del 22-11) -------------------------------
# En la copia de transmisión dos trafos de tres devanados de 200/62,46 kV con la toma en el punto estrella estaban en la
# toma +2 de alta (t = 1,1): con las tensiones de DIgSILENT, pandapower les daba 94,4 MW a cada uno y DIgSILENT 116,5,
# porque DIgSILENT deja la rama de alta en ohmios y pandapower la escala con t². Su red de 60 kV quedaba descuadrada
# ±50 MW; los de la misma ficha con la toma en el borne ya cuadraban.

def test_con_la_toma_en_la_estrella_la_rama_del_devanado_queda_en_ohmios_de_su_lado():
    """107:RF-38 — con la toma en el punto estrella (``itapos`` = 0) y en +2 de alta (5 % por paso, t = 1,1), la rama
    de estrella de alta sale dividida por t² y las de media y baja no cambian, en vk y en vkr."""
    t = 1.1
    vk = _vk3(_app_tr3(0, 2, itapos=0))
    zh, zm, zl = _estrella(12.6, 1.7, 6.8)
    ah, am, al = _estrella(*vk[:3])
    assert (round(ah, 3), round(am, 3), round(al, 3)) == (round(zh / t**2, 3), round(zm, 3), round(zl, 3))
    rh, rm, rl = _estrella(670.0 / (10 * 240.0), 125.0 / (10 * 80.0), 135.0 / (10 * 80.0))
    bh, bm, bl = _estrella(*vk[3:])
    assert (round(bh, 3), round(bm, 3), round(bl, 3)) == (round(rh / t**2, 3), round(rm, 3), round(rl, 3))


def test_con_la_rama_en_ohmios_pandapower_da_el_flujo_de_digsilent():
    """107:RF-38 — el trafo exportado en la toma +2, entre dos tensiones fijas y con baja en vacío, lleva en pandapower
    la potencia del modelo de DIgSILENT: rama de alta en ohmios a la tensión nominal del tipo y la de media en p.u. de
    media, referida a alta por la relación de la toma."""
    import cmath
    import math
    import warnings

    import pandapower as pp
    warnings.filterwarnings('ignore')
    t3 = _red_t(_app_tr3(0, 2, itapos=0)).de_tipo('trafo3')[0]
    v1, v2 = 0.99 * cmath.exp(1j * math.radians(-47.1)), 1.01 * cmath.exp(1j * math.radians(-50.5))
    n = pp.create_empty_network(sn_mva=100)
    b = [pp.create_bus(n, kv) for kv in (220.0, 60.0, 66.0)]
    pp.create_ext_grid(n, b[0], vm_pu=abs(v1), va_degree=math.degrees(cmath.phase(v1)))
    pp.create_ext_grid(n, b[1], vm_pu=abs(v2), va_degree=math.degrees(cmath.phase(v2)))
    num = ('sn_hv_mva', 'sn_mv_mva', 'sn_lv_mva', 'vn_hv_kv', 'vn_mv_kv', 'vn_lv_kv', 'vk_hv_percent', 'vk_mv_percent',
           'vk_lv_percent', 'vkr_hv_percent', 'vkr_mv_percent', 'vkr_lv_percent', 'tap_step_percent', 'tap_neutral',
           'tap_pos', 'tap_min', 'tap_max')
    pp.create_transformer3w_from_parameters(n, *b, pfe_kw=0.0, i0_percent=0.0, tap_changer_type='Ratio',
                                            tap_side=t3.get('tap_side'), **{k: float(t3.get(k)) for k in num})
    pp.runpp(n, calculate_voltage_angles=True, numba=False)
    zh, zm, _ = _estrella(12.6, 1.7, 6.8)
    rh, rm, _ = _estrella(670.0 / (10 * 240.0), 125.0 / (10 * 80.0), 135.0 / (10 * 80.0))

    def rama(z, r):
        return complex(r, math.copysign(math.sqrt(max(z * z - r * r, 0.0)), z)) / 100

    rel = 200.0 * 1.1 / 62.46
    z = rama(zh, rh) * 200.0**2 / 240.0 + rama(zm, rm) * 62.46**2 / 240.0 * rel**2
    i = (v1 * 220.0 - v2 * 60.0 * rel) / z
    p_dig = (v1 * 220.0 * i.conjugate()).real
    assert float(n.res_trafo3w.p_hv_mw[0]) == pytest.approx(p_dig, rel=0.02)


def test_sin_impedancia_dependiente_la_vkr_de_cada_par_va_en_la_base_del_par():
    """107:RF-30 — la parte resistiva de cada par sale de sus pérdidas en el cobre sobre la potencia del par, como en
    DIgSILENT (``uktrr3_*`` = ``pcut3_*`` / (10 · potencia del par), con AT-MT en min(AT, MT), MT-BT en min(MT, BT) y
    BT-AT en min(BT, AT)): la sonda del 22-11 leyó en un trafo de 240/240/80 MVA ``uktrr3_m`` = 0,1558 % y el
    exportador daba 0,0519 %, las pérdidas de MT-BT sobre los 240 MVA de media en vez de los 80 del par."""
    app = _app_tr3(0, 0)
    tipo = app.objetos['*.ElmTr3'][0].typ_id
    for k, v in (('strn3_h', 240.0), ('strn3_m', 180.0), ('strn3_l', 60.0)):
        object.__setattr__(tipo, k, v)
    assert _vk3(app)[3:] == (round(670.0 / (10 * 180.0), 4), round(125.0 / (10 * 60.0), 4),
                             round(135.0 / (10 * 60.0), 4))


# --- 107:RF-31: el control de tensión de las máquinas y de los SVC (corrida de 107 T14, 22-11) --------------------------
# En la copia de transmisión las máquinas síncronas salían como inyección fija con la Q que dio DIgSILENT, y los SVC como
# nudos PV con su consigna en su propia barra: el motor abierto no convergía desde arranque plano; con las máquinas como
# nudos PV sí. Los SVC regulan un nudo remoto (la barra de alta) y la mitad estaba en su límite de Q.

def test_rf31_la_maquina_con_control_de_tension_sale_como_pv_y_la_de_q_constante_no():
    """107:RF-31 — una ElmSym con ``av_mode`` «constv» sale como red externa PV con su consigna (usetp), su potencia
    (pgini por el número de unidades) y sus límites de Q (los de DIgSILENT, c:Qmin y c:Qmax); una con «constq» no se
    exporta: su generación sigue siendo inyección del caso."""
    app = _AppTransmision()
    barra = app.b[('SY', '3')]
    sub = barra.GetParent()
    app.objetos['*.ElmSym'] += [
        Obj(None, 'ElmSym', 'GV', sub, ip_ctrl=0, av_mode='constv', usetp=1.02, pgini=10.0, ngnum=2,
            **{'c:Qmin': -8.0, 'c:Qmax': 12.0}, bus1=_Cub(barra)),
        Obj(None, 'ElmSym', 'GQ', sub, ip_ctrl=0, av_mode='constq', usetp=1.0, pgini=5.0, ngnum=1, bus1=_Cub(barra))]
    red = _red_t(app)
    por_nombre = {e['nombre']: e for e in red.de_tipo('red_externa')}
    assert 'GQ' not in por_nombre and 'GV' in por_nombre, sorted(por_nombre)
    g = por_nombre['GV']
    assert (g['tipo_barra'], g['vm_pu'], g['p_mw'], g['q_min_mvar'], g['q_max_mvar']) == ('PV', 1.02, 20.0, -8.0, 12.0)
    r = _flujo_t(red, app)
    assert not isinstance(r, Exception) and r.converge, r
    assert r.tensiones_pu[guion._id(barra)] == pytest.approx(1.02, abs=1e-6)


def test_rf31_el_svc_regula_su_nudo_remoto_y_el_de_q_constante_sale_pq():
    """107:RF-31 — el ElmSvs con control de tensión (``i_ctrl`` 1) y nudo remoto (``p_rem``) sale con ese nudo como
    ``barra_control``, y el motor abierto deja ese nudo, no la barra del SVC, en la consigna; con control de Q
    (``i_ctrl`` 2) sale PQ con su Q (qsetp)."""
    app = _AppTransmision()
    barra, remoto = app.b[('SY', '3')], app.b[('SY', '2')]
    sub = barra.GetParent()
    app.objetos['*.ElmSvs'] = [
        Obj(None, 'ElmSvs', 'SVR', sub, usetp=1.0, i_ctrl=1, p_rem=remoto, qmax=200.0, qmin=200.0, bus1=_Cub(barra),
            tras_flujo={'c:Qmin': -200.0, 'c:Qmax': 200.0}),
        Obj(None, 'ElmSvs', 'SVQ', sub, usetp=1.0, i_ctrl=2, qsetp=3.0, qmax=10.0, qmin=10.0, bus1=_Cub(barra))]
    red = _red_t(app)
    por_nombre = {e['nombre']: e for e in red.de_tipo('red_externa')}
    assert por_nombre['SVR'].get('barra_control') == guion._id(remoto), por_nombre['SVR']
    assert (por_nombre['SVQ']['tipo_barra'], por_nombre['SVQ'].get('q_mvar')) == ('PQ', 3.0)
    r = _flujo_t(red, app)
    assert not isinstance(r, Exception) and r.converge, r
    assert r.tensiones_pu[guion._id(remoto)] == pytest.approx(1.0, abs=1e-4)
    assert abs(r.tensiones_pu[guion._id(barra)] - 1.0) > 1e-3


def test_rf41_el_svc_de_un_controlador_de_estacion_en_control_de_q_entrega_su_q_resuelta():
    """107:RF-41 — un SVC con control de tensión propio que un controlador de estación lleva en control de Q (i_ctrl 1
    del ElmStactrl, que lo nombra en psym) sale PQ con la Q que resolvió DIgSILENT (m:Q, convenio de carga: +163,9
    absorbe), no PV a su consigna; el que no tiene controlador sigue PV. (Copia de transmisión: el SVC del horno de
    Aceros absorbía 163,9 Mvar para dejar 0 en su cubículo de 220 kV.)"""
    app = _AppTransmision()
    barra = app.b[('SY', '3')]
    sub = barra.GetParent()
    svc = Obj(None, 'ElmSvs', 'SVA', sub, usetp=1.0, i_ctrl=1, qmax=170.0, qmin=0.0, bus1=_Cub(barra),
              **{'m_Q:bus1': 163.9})
    libre = Obj(None, 'ElmSvs', 'SVL', sub, usetp=1.0, i_ctrl=1, qmax=10.0, qmin=10.0, bus1=_Cub(barra),
                **{'m_Q:bus1': 2.0})
    app.objetos['*.ElmSvs'] = [svc, libre]
    app.objetos['*.ElmStactrl'] = [Obj(None, 'ElmStactrl', 'QC', sub, outserv=0, i_ctrl=1, qsetp=0.0, psym=[svc])]
    por_nombre = {e['nombre']: e for e in _red_t(app).de_tipo('red_externa')}
    assert (por_nombre['SVA']['tipo_barra'], por_nombre['SVA'].get('q_mvar')) == ('PQ', -163.9), por_nombre['SVA']
    assert por_nombre['SVL']['tipo_barra'] == 'PV', por_nombre['SVL']


def test_rf31_el_pv_en_su_limite_de_q_deja_de_sostener_la_tension():
    """107:RF-31 — el motor abierto aplica los límites de Q: un SVC con 0,5 Mvar como mucho no sostiene una consigna que
    pide más, y su barra queda por debajo de ella."""
    app = _AppTransmision()
    barra = app.b[('SY', '3')]
    app.objetos['*.ElmSvs'] = [Obj(None, 'ElmSvs', 'SVC', barra.GetParent(), usetp=1.10, qmax=0.5, qmin=0.5,
                                   bus1=_Cub(barra), tras_flujo={'c:Qmin': -0.5, 'c:Qmax': 0.5})]
    r = _flujo_t(_red_t(app), app)
    assert not isinstance(r, Exception) and r.converge, r
    assert r.tensiones_pu[guion._id(barra)] < 1.10 - 1e-3


def test_rf43_la_exportacion_calcula_el_flujo_y_el_svc_lleva_los_limites_que_resuelve_digsilent():
    """107:RF-43 — antes de leer la red se calcula el flujo del caso activo: los límites del SVC son los que resuelve
    DIgSILENT (c:Qmin, c:Qmax), no sus nominales. (Copia AD08, 24-11: el SVC de Trujillo, un reactor de 50 Mvar sin
    condensadores, tiene qmin 0 y qmax 50; sin flujo salía capacitivo [0, 50] y su barra subía a 1,21 p.u. donde
    DIgSILENT da 0,97; resuelto es [−47,1, 0]: solo absorbe.)"""
    app = _AppTransmision()
    barra, remoto = app.b[('SY', '3')], app.b[('SY', '2')]
    app.objetos['*.ElmSvs'] = [Obj(None, 'ElmSvs', 'REACTOR', barra.GetParent(), usetp=1.0, i_ctrl=1, p_rem=remoto,
                                   qmin=0.0, qmax=50.0, bus1=_Cub(barra),
                                   tras_flujo={'c:Qmin': -47.1, 'c:Qmax': 0.0})]
    red = _red_t(app)
    assert app.flujos == 1
    s = {e['nombre']: e for e in red.de_tipo('red_externa')}['REACTOR']
    assert (s['q_min_mvar'], s['q_max_mvar']) == (-47.1, 0.0), s
    assert not s.get('limites_q_sin_resolver')


def test_rf43_sin_flujo_el_svc_sale_sin_limites_y_el_motor_abierto_lo_dice():
    """107:RF-43 — si el flujo de DIgSILENT no converge, el SVC no lleva límites inventados con sus nominales: sale sin
    ellos, marcado, y el motor abierto lo avisa en su mensaje."""
    app = _AppTransmision()
    app.ldf_falla = True
    barra = app.b[('SY', '3')]
    app.objetos['*.ElmSvs'] = [Obj(None, 'ElmSvs', 'REACTOR', barra.GetParent(), usetp=1.0, i_ctrl=1, qmin=0.0,
                                   qmax=50.0, bus1=_Cub(barra))]
    red = _red_t(app)
    s = {e['nombre']: e for e in red.de_tipo('red_externa')}['REACTOR']
    assert 'q_min_mvar' not in s and 'q_max_mvar' not in s and s.get('limites_q_sin_resolver') is True, s
    r = _flujo_t(red, app)
    assert not isinstance(r, Exception), r
    assert 'sin límites de Q resueltos' in r.mensaje, r.mensaje


def test_rf31_dos_maquinas_en_la_misma_barra_con_consignas_distintas_calculan_con_una_y_se_avisa():
    """107:RF-31 — dos máquinas en paralelo en la misma barra con consignas 1,000 y 1,002: pandapower no admite dos
    consignas en una barra; el motor abierto toma la primera, calcula y lo dice en el mensaje."""
    app = _AppTransmision()
    barra = app.b[('SY', '3')]
    sub = barra.GetParent()
    app.objetos['*.ElmSym'] += [
        Obj(None, 'ElmSym', 'G1', sub, ip_ctrl=0, av_mode='constv', usetp=1.0, pgini=5.0, ngnum=1, bus1=_Cub(barra)),
        Obj(None, 'ElmSym', 'G2', sub, ip_ctrl=0, av_mode='constv', usetp=1.002, pgini=5.0, ngnum=1, bus1=_Cub(barra))]
    r = _flujo_t(_red_t(app), app)
    assert not isinstance(r, Exception) and r.converge, r
    assert r.tensiones_pu[guion._id(barra)] == pytest.approx(1.0, abs=1e-6)
    assert 'misma barra' in r.mensaje and 'G2' in r.mensaje, r.mensaje


# --- 107:RF-32: los controladores de estación (corrida de 107 T14, 22-11) ----------------------------------------------
# En la copia de transmisión 61 controladores de estación (ElmStactrl) regulaban un nudo (rembar) con su consigna y
# repartían la Q entre sus máquinas (cvqq); la consigna propia de cada máquina no contaba: dos en paralelo con 1,000 y
# 1,002 dejaban su barra a 1,02, la del controlador.

def _app_estacion(barras):
    app = _AppTransmision()
    remoto = app.b[('SY', '2')]
    ctrl = Obj(None, 'ElmStactrl', 'CE', remoto.GetParent(), outserv=0, i_ctrl=0, usetp=1.03, rembar=remoto,
               cvqq=[50.0, 50.0])
    for k, clave in enumerate(barras):
        barra = app.b[clave]
        app.objetos['*.ElmSym'].append(Obj(None, 'ElmSym', f'GE{k}', barra.GetParent(), ip_ctrl=0, av_mode='constv',
                                           usetp=1.0 + 0.002 * k, pgini=5.0, ngnum=1, c_pstac=ctrl,
                                           **{'c:Qmin': -50.0, 'c:Qmax': 50.0}, bus1=_Cub(barra)))
    return app, remoto


def test_rf32_las_maquinas_de_un_controlador_de_estacion_regulan_su_nudo_con_su_consigna():
    """107:RF-32 — dos máquinas en la misma barra con un controlador de estación (c_pstac) salen con el nudo del
    controlador (rembar) como barra_control y su consigna (usetp del controlador), y el motor abierto deja ese nudo en
    1,03, no en la consigna propia de las máquinas."""
    app, remoto = _app_estacion([('SY', '3'), ('SY', '3')])
    red = _red_t(app)
    ge = [e for e in red.de_tipo('red_externa') if e['nombre'].startswith('GE')]
    assert [(e.get('barra_control'), e['vm_pu']) for e in ge] == [(guion._id(remoto), 1.03)] * 2, ge
    r = _flujo_t(red, app)
    assert not isinstance(r, Exception) and r.converge, r
    assert r.tensiones_pu[guion._id(remoto)] == pytest.approx(1.03, abs=1e-4)


def test_rf32_un_controlador_con_maquinas_en_dos_barras_reparte_el_ajuste():
    """107:RF-32 — un controlador con una máquina en cada subestación y el nudo en una de ellas: el motor abierto deja el
    nudo en su consigna sin oscilar (el ajuste de la consigna se reparte entre las máquinas del mismo nudo)."""
    app, remoto = _app_estacion([('SY', '3'), ('SX', '3')])
    r = _flujo_t(_red_t(app), app)
    assert not isinstance(r, Exception) and r.converge, r
    assert r.tensiones_pu[guion._id(remoto)] == pytest.approx(1.03, abs=1e-4)


def test_rf40_el_controlador_con_estatismo_deja_su_nudo_en_la_tension_resuelta():
    """107:RF-40 — un controlador de estación con estatismo (i_droop 1, ddroop > 0) no deja su nudo en la consigna: sus
    máquinas salen con la tensión que resolvió DIgSILENT en el nudo (m:u) y marcadas como aproximadas; sin estatismo,
    con la consigna. (Copia de transmisión: el STATCOM de Pucallpa, 1 % sobre 80 Mvar, dejaba su nudo en 0,9927 y el
    motor abierto, con 1,000, subía el grupo de Pucallpa 0,006 p.u.)"""
    app, remoto = _app_estacion([('SY', '3')])
    ctrl = app.objetos['*.ElmSym'][-1].c_pstac
    ctrl.i_droop, ctrl.ddroop = 1, 1.0
    setattr(remoto, 'm:u', 1.021)
    ge = [e for e in _red_t(app).de_tipo('red_externa') if e['nombre'].startswith('GE')]
    assert [(e['vm_pu'], e.get('estatismo_aproximado')) for e in ge] == [(1.021, True)], ge
    ctrl.ddroop = 0.0
    ge = [e for e in _red_t(app).de_tipo('red_externa') if e['nombre'].startswith('GE')]
    assert [(e['vm_pu'], e.get('estatismo_aproximado')) for e in ge] == [(1.03, None)], ge


# --- 107:RF-33: la solución de tensión alta (corrida de 107 T14, 22-11) -------------------------------------------------
# En la copia de transmisión una radial larga de 60 kV tenía dos soluciones: desde arranque plano el NR caía en la de
# tensión baja (0,50 p.u. donde DIgSILENT da 1,00); con la carga llevada de 0,5 a 1 desde la solución anterior, en la alta.

def _radial_rf33(p_mw):
    area = AreaPit('AREA-R', ('TIT',), (), {}, 0.0, {})
    comun = {'areas': ['AREA-R'], 'titular': 'TIT'}
    el = [{'id': 'B0', 'tipo': 'barra', 'kv': 60.0, **comun},
          {'id': 'EXT', 'tipo': 'red_externa', 'barra': 'B0', 'kv': 60.0, 'vm_pu': 1.04, 'tipo_barra': 'SL', **comun}]
    for i in range(1, 4):
        el += [{'id': f'B{i}', 'tipo': 'barra', 'kv': 60.0, **comun},
               {'id': f'L{i}', 'tipo': 'linea', 'desde': f'B{i - 1}', 'hasta': f'B{i}', 'kv': 60.0, 'longitud_km': 30.0,
                'r_ohm_per_km': 0.28, 'x_ohm_per_km': 0.47, 'c_nf_per_km': 9.7, 'max_i_ka': 0.4, **comun}]
    return desde_ambito(reunir(area, el)), {'B3': (p_mw, 0.2 * p_mw)}


def _primero_en_la_baja(monkeypatch):
    """El primer flujo de ``calcular`` cae en la solución de tensión baja (como desde arranque plano en la red real):
    se arranca desde 0,5 p.u.; los siguientes son los de siempre."""
    import pandapower

    original, llamadas = pandapower.runpp, []

    def runpp(net, **kw):
        if llamadas:
            return original(net, **kw)
        llamadas.append(kw)
        original(net, **{**kw, 'init': 'dc'})
        net.res_bus['vm_pu'] = [1.04 if b in set(net.ext_grid.bus) else 0.5 for b in net.res_bus.index]
        net.res_bus['va_degree'] = 0.0
        return original(net, **{**kw, 'init': 'results', 'max_iteration': 40})

    monkeypatch.setattr(pandapower, 'runpp', runpp)
    return llamadas


def test_rf33_si_cae_en_la_solucion_baja_reintenta_por_continuacion_y_se_queda_con_la_alta(monkeypatch):
    """107:RF-33 — una radial con dos soluciones: el primer flujo da 0,34 p.u. al final; con barras por debajo de 0,8 el
    motor abierto reintenta llevando la carga de 0,5 a 1 desde la solución anterior, se queda con la de tensión alta
    (0,79) y lo dice en el mensaje. Sin DIgSILENT."""
    red, cargas = _radial_rf33(19.0)
    llamadas = _primero_en_la_baja(monkeypatch)
    r = calcular(red, cargas)
    assert llamadas, 'el doble no intervino'
    assert r.converge, r.mensaje
    assert r.tensiones_pu['B3'] == pytest.approx(0.789, abs=0.01), r.tensiones_pu
    assert 'continuación' in r.mensaje, r.mensaje


def test_rf33_sin_barras_bajas_no_reintenta():
    """107:RF-33 — con todas las barras por encima de 0,8 p.u. no hay segundo intento ni aviso."""
    red, cargas = _radial_rf33(12.0)
    r = calcular(red, cargas)
    assert r.converge and r.tensiones_pu['B3'] == pytest.approx(0.913, abs=0.01)
    assert 'continuación' not in r.mensaje


# --- 107:RF-34: el estatismo de los SVC (corrida de 107 T14, 22-11) ------------------------------------------------------
# En la copia de transmisión dos SVC con estatismo del 2 % dejaban su nudo de alta en 0,9947 con consigna 1,000; ninguna
# fórmula con sus atributos reproducía los siete casos medidos, y el motor los fijaba en 1,000: todo el Sur quedaba +0,005.

def test_rf34_el_svc_con_estatismo_toma_la_tension_resuelta_de_su_nudo_y_lo_avisa():
    """107:RF-34 — un SVC con estatismo (``ddroop`` > 0, ``i_droop`` 1) y nudo remoto sale con la tensión resuelta de ese
    nudo en el caso exportado (m:u) como consigna, y el motor abierto deja el nudo en ella y avisa de que el estatismo es
    aproximado."""
    app = _AppTransmision()
    barra, remoto = app.b[('SY', '3')], app.b[('SY', '2')]
    object.__setattr__(remoto, 'm_u', 0.995)
    app.objetos['*.ElmSvs'] = [Obj(None, 'ElmSvs', 'SVD', barra.GetParent(), usetp=1.0, i_ctrl=1, p_rem=remoto,
                                   ddroop=2.0, i_droop=1, qmax=200.0, qmin=200.0, bus1=_Cub(barra))]
    red = _red_t(app)
    s = next(e for e in red.de_tipo('red_externa') if e['nombre'] == 'SVD')
    assert s['vm_pu'] == pytest.approx(0.995), s
    r = _flujo_t(red, app)
    assert not isinstance(r, Exception) and r.converge, r
    assert r.tensiones_pu[guion._id(remoto)] == pytest.approx(0.995, abs=1e-4)
    assert 'estatismo aproximado' in r.mensaje, r.mensaje


def test_rf34_sin_estatismo_la_consigna_es_la_del_svc():
    """107:RF-34 — sin estatismo, la consigna es la usetp del SVC aunque el nudo tenga otra tensión resuelta."""
    app = _AppTransmision()
    barra, remoto = app.b[('SY', '3')], app.b[('SY', '2')]
    object.__setattr__(remoto, 'm_u', 0.995)
    app.objetos['*.ElmSvs'] = [Obj(None, 'ElmSvs', 'SVN', barra.GetParent(), usetp=1.0, i_ctrl=1, p_rem=remoto,
                                   ddroop=0.0, i_droop=0, qmax=200.0, qmin=200.0, bus1=_Cub(barra))]
    s = next(e for e in _red_t(app).de_tipo('red_externa') if e['nombre'] == 'SVN')
    assert s['vm_pu'] == pytest.approx(1.0)


# --- 107:RF-35: la conductancia de las líneas (corrida de 107 T14, 22-11) ------------------------------------------------
# En la copia de transmisión 67 tipos de línea traían conductancia (gline, en µS/km); sin ella el motor abierto perdía
# unos 100 MW de pérdidas (DIgSILENT 337 MW en líneas, el modelo 294 con las mismas tensiones) y la máquina de referencia
# generaba 110 MW menos.

def test_rf35_la_conductancia_de_la_linea_se_exporta_y_suma_sus_perdidas():
    """107:RF-35 — el gline del tipo sale como g_us_per_km y el motor abierto lo usa: con 0,5 µS/km en 80 km de 220 kV la
    línea disipa unos 40 µS × (220 kV)² ≈ 1,9 MW más."""
    sin = _AppTransmision()
    r0 = _flujo_t(_red_t(sin), sin)
    app = _AppTransmision()
    tipo = app.objetos['*.ElmLne'][0].typ_id
    object.__setattr__(tipo, 'gline', 0.5)
    red = _red_t(app)
    assert red.de_tipo('linea')[0].get('g_us_per_km') == pytest.approx(0.5)
    r1 = _flujo_t(red, app)
    assert not isinstance(r1, Exception) and r1.converge, r1
    assert r1.perdidas_mw - r0.perdidas_mw == pytest.approx(1.9, abs=0.3), (r0.perdidas_mw, r1.perdidas_mw)


# --- 107:RF-36: la corriente nominal de la línea con su factor de reducción (corrida de 107 T14, 22-11) -----------------
# En la copia de transmisión DIgSILENT carga cada línea sobre Inom_a = sline · fline · nlnum; 27 líneas tenían fline
# distinto de 1 (0,19 a 1,4) y el motor abierto, con la sline del tipo, daba cargas de hasta 47 puntos menos.

def test_rf36_la_corriente_nominal_de_la_linea_lleva_su_factor_de_reduccion():
    """107:RF-36 — con fline = 0,5 la línea sale con la mitad de la corriente nominal del tipo y su cargabilidad en el
    motor abierto es el doble que con fline = 1."""
    base = _AppTransmision()
    r0 = _flujo_t(_red_t(base), base)
    app = _AppTransmision()
    object.__setattr__(app.objetos['*.ElmLne'][0], 'fline', 0.5)
    red = _red_t(app)
    assert red.de_tipo('linea')[0]['max_i_ka'] == pytest.approx(0.5)
    r1 = _flujo_t(red, app)
    lid = red.de_tipo('linea')[0]['id']
    assert r1.cargabilidad_pct[lid] == pytest.approx(2 * r0.cargabilidad_pct[lid], rel=1e-6)


# --- 107:RF-37: la potencia de referencia de la cargabilidad del trafo3 (corrida de 107 T14, 22-11) ---------------------
# En la copia de transmisión 20 trafos de tres devanados tenían en el elemento una potencia nominal (Snom_h/m/l) distinta
# de la del tipo (132 MVA frente a 80 del tipo): DIgSILENT carga sobre ella y el motor abierto daba 70,5 % donde
# DIgSILENT da 42,7 %, con el mismo flujo.

def test_rf37_la_cargabilidad_del_trafo3_usa_la_potencia_del_elemento():
    """107:RF-37 — con Snom del elemento 1,5 veces la del tipo, el trafo3 sale con esa potencia de referencia y su
    cargabilidad en el motor abierto es 1/1,5 la de antes, con el mismo flujo."""
    base = _app_tr3(0, 0)
    r0 = _flujo_t(_red_t(base), base)
    app = _app_tr3(0, 0)
    tr3 = app.objetos['*.ElmTr3'][0]
    for x, s in (('h', 360.0), ('m', 360.0), ('l', 120.0)):
        object.__setattr__(tr3, f'Snom_{x}', s)
    red = _red_t(app)
    t = red.de_tipo('trafo3')[0]
    assert (t.get('sn_carga_hv_mva'), t.get('sn_carga_mv_mva'), t.get('sn_carga_lv_mva')) == (360.0, 360.0, 120.0), t
    r1 = _flujo_t(red, app)
    assert r1.flujos[t['id']] == pytest.approx(r0.flujos[t['id']], rel=1e-9)
    assert r1.cargabilidad_pct[t['id']] == pytest.approx(r0.cargabilidad_pct[t['id']] / 1.5, rel=0.01)
