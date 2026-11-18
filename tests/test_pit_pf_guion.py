"""Spec 107 T12 — ``tools/pit_pf.py`` con el doble de DIgSILENT (``tests/fake_pf.py``) (107:RF-2, RF-3, RF-5)."""
from __future__ import annotations

import dataclasses

import pytest

from apoyo import cargar_herramienta
from datos_pit import perfil_a
from fake_pf import Obj

from convertersmartgrid.dominio.pit import PitError
from convertersmartgrid.dominio.pit.ambito import areas_del_perfil, reunir
from convertersmartgrid.aplicacion.pit.red_area import desde_ambito
from convertersmartgrid.adaptadores.pit.red_pandapower import calcular

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
        return self.objetos[patron]

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
