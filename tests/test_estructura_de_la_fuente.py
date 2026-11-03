"""Spec 055: la estructura sale de la propia fuente cuando el Excel y el perfil no cubren lo cargado."""
from __future__ import annotations

from types import SimpleNamespace

from convertersmartgrid.estructura import asignar, estructura_de_dict, estructura_de_la_fuente
from convertersmartgrid.web import services
from vnr_etl.connectors import sqlserver_vnr as sv

FILAS = {'A1': {'sistema_codigo': 'S1', 'sistema_nombre': 'Sistema Uno', 'sector': '2', 'set_codigo': 'T1', 'set_nombre': 'Norte'},
         'A2': {'sistema_codigo': 'S1', 'sistema_nombre': 'Sistema Uno', 'sector': '2', 'set_codigo': '', 'set_nombre': ''},
         'B1': {'sistema_codigo': 'S2', 'sistema_nombre': 'Sistema Dos', 'sector': '3', 'set_codigo': 'T2', 'set_nombre': 'Sur'},
         'C1': {'sistema_codigo': '', 'sistema_nombre': '', 'sector': '', 'set_codigo': '', 'set_nombre': ''}}


def test_cada_sistema_es_un_zonal_con_sus_set():
    """055:RF-3 — con el grupo «sin SET» de su sistema, convertible como los demás."""
    e = estructura_de_la_fuente(FILAS)
    assert e.zonales == ['Sistema Dos', 'Sistema Uno']
    assert e.set_de('A1').rotulo == 'T1 Norte' and e.set_de('A1').zonal == 'Sistema Uno'
    assert e.set_de('A2').zonal == 'Sistema Uno' and 'sin SET' in e.set_de('A2').codigo
    assert e.sistemas['S2'].sector == '3' and e.alimentador('B1').sistema == 'S2'


def test_lo_que_no_trae_estructura_sigue_cargado_y_convertible():
    """055:RF-4 / 055:RF-5 — queda «Sin SET», no desaparece; sin nada en toda la fuente, no hay estructura."""
    a = asignar(estructura_de_la_fuente(FILAS), list(FILAS))
    assert a.sin_set == ['C1'] and sorted(a.set_de) == ['A1', 'A2', 'B1']
    assert estructura_de_la_fuente({'C1': FILAS['C1']}) is None and estructura_de_la_fuente({}) is None


def test_una_set_que_da_a_dos_sistemas():
    """055:RF-3 — aquí una SET es de un zonal: lleva una por sistema, y ninguno pierde sus alimentadores."""
    e = estructura_de_la_fuente({
        'A1': {'sistema_codigo': 'S1', 'sistema_nombre': 'Uno', 'set_codigo': 'T1', 'set_nombre': 'Norte'},
        'B1': {'sistema_codigo': 'S2', 'sistema_nombre': 'Dos', 'set_codigo': 'T1', 'set_nombre': 'Norte'}})
    assert e.set_de('A1').zonal == 'Uno' and e.set_de('B1').zonal == 'Dos' and len(e.sets) == 2


def test_vnr_guarda_lo_que_dice_de_cada_alimentador():
    """055:RF-1 — con el código operativo del alimentador, y solo de los cargados."""
    datos = sv.DatosVnr(salidas=[{'CodSalidaMT': 'W1', 'CodSet': 'T1', 'CodSisElectrico': 'S1'},
                                 {'CodSalidaMT': 'W2', 'CodSet': 'T1', 'CodSisElectrico': 'S1'}],
                        sets=[{'CodSet': 'T1', 'Nombre': 'Norte'}],
                        sistemas=[{'CodSisElectrico': 'S1', 'Nombre': 'Sistema Uno', 'CodSectorTipico': '2'}])
    r = sv.estructura_de_salidas(datos, {'W1': 'A1', 'W2': 'W2'}, {'A1'})
    assert r == {'A1': {'sistema_codigo': 'S1', 'sistema_nombre': 'Sistema Uno', 'sector': '2', 'set_codigo': 'T1',
                        'set_nombre': 'Norte'}}
    tablas = sv.tablas_por_campos({'empSistemaElectrico': ['CodSisElectrico', 'Nombre', 'CodSectorTipico', 'CodEmpresa']})
    assert tablas['sistema'] == 'empSistemaElectrico'


def _espacio(alimentadores=('A1', 'B1'), fuente=FILAS, excel=None):
    return SimpleNamespace(demanda={'estructura': {'path': excel}} if excel else {},
                           inventory={'feeders': [{'feeder': a} for a in alimentadores]},
                           dataset=SimpleNamespace(estructura_fuente=fuente))


def _perfil(monkeypatch, estructura):
    monkeypatch.setattr('convertersmartgrid.perfil_empresa.estructura_empresa', lambda *a, **k: estructura)


def _tabla():
    return estructura_de_dict({'zonales': [{'nombre': 'Z', 'sets': [{'codigo': 'T9', 'nombre': 'Otra', 'alimentadores': ['A1']}]}]})


def test_el_perfil_que_asigna_gana_a_la_fuente(monkeypatch):
    """055:RF-2 — el perfil, si asigna SET a alguno de los cargados."""
    _perfil(monkeypatch, _tabla())
    e, origen = services._estructura_y_origen(_espacio())
    assert origen == 'perfil' and e.set_de('A1').codigo == 'T9'


def test_sin_excel_ni_perfil_que_cubra_manda_la_fuente(monkeypatch):
    """055:RF-2 — el perfil de otra empresa no asigna ninguno, y la web dice de dónde sale."""
    _perfil(monkeypatch, _tabla())
    e, origen = services._estructura_y_origen(_espacio(alimentadores=('B1',)))
    assert origen == 'fuente' and e.set_de('B1').codigo == 'T2'
    _perfil(monkeypatch, None)
    assert services._estructura_y_origen(_espacio())[1] == 'fuente'


def test_el_excel_gana_a_todo(monkeypatch, tmp_path):
    """055:RF-2 — lo que sube el operador manda."""
    _perfil(monkeypatch, None)
    monkeypatch.setattr('convertersmartgrid.estructura.leer_tabla_excel', lambda ruta: _tabla())
    assert services._estructura_y_origen(_espacio(excel=str(tmp_path / 'x.xlsx')))[1] == 'excel'


def test_una_fuente_sin_estructura_no_inventa(monkeypatch):
    """055:RF-4 — TXT o .mdb sin estructura ni perfil: ninguna, y se dice; un perfil sin cubrir sigue siendo el perfil."""
    _perfil(monkeypatch, None)
    assert services._estructura_y_origen(_espacio(fuente={})) == (None, None)
    _perfil(monkeypatch, _tabla())
    assert services._estructura_y_origen(_espacio(alimentadores=('B1',), fuente={}))[1] == 'perfil'
