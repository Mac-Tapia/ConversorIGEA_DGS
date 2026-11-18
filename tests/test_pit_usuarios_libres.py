"""PIT-F113-118 — usuarios libres y demandas incorporadas (F-113 a F-118), desde el libro de cargas nuevas y el perfil
(107:RF-9). Cargas, usuarios, alimentadores y redes sintéticos; las pérdidas, del registro real (primera empresa con
fijación vigente, sin nombrarla).
"""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest

from convertersmartgrid.aplicacion.cargas_pf import CargaNueva
from convertersmartgrid.dominio.pit import PitError
from convertersmartgrid.adaptadores.pit.demanda_regulatoria import Topologia
from convertersmartgrid.aplicacion.pit.red_area import RedArea
from convertersmartgrid.dominio.registro_normativo import RegistroError, cargar_registro

RAIZ = Path(__file__).resolve().parents[1]
NORMATIVA = RAIZ / 'config' / 'normativa'
FECHA = '2026-11-16'
FUENTE = {'nombre': 'libro de cargas nuevas sintético', 'huella': 'c' * 16}
TOPO = Topologia(sistemas={'SIS-1': ['SET-A']}, sets={'SET-A': ['TA:lv']}, devanados={'TA:lv': ['AL1', 'AL2']})


def _modulo():
    """El módulo de la tarjeta: su ausencia es la falla de la aserción, no un error de importación."""
    assert importlib.util.find_spec('convertersmartgrid.adaptadores.pit.usuarios_libres') is not None, \
        'falta convertersmartgrid.adaptadores.pit.usuarios_libres (PIT-F113-118)'
    return importlib.import_module('convertersmartgrid.adaptadores.pit.usuarios_libres')


def _registro_y_empresa():
    registro = cargar_registro(NORMATIVA)
    for empresa in registro.empresas_de('vad.perdidas.factores_expansion'):
        try:
            rv = registro.regla_de_empresa('vad.perdidas.factores_expansion', empresa, FECHA)
        except RegistroError:
            continue
        return registro, empresa, rv.regla.valor['empresas'][empresa]['fe']
    raise AssertionError('el registro real no trae ninguna fijación vigente')


def _red():
    return RedArea('AREA-S', elementos={'barra': [{'id': 'BA', 'set': 'SET-A', 'rol': 'carga', 'kv': 10.0}],
                                        'trafo2': [{'id': 'TA', 'set': 'SET-A', 'hv': 'HA', 'lv': 'BA'}], 'trafo3': []})


SALIDA_3B = {'anio': 2031, 'f101': {'filas': [{'nivel': 'devanado', 'nombre': 'TA:lv', 'fc': 0.5, 'fcp': 0.8, 'fs': 0.6}]},
             'f103': {'filas': [{'devanado': 'TA:lv', 'fphms': 0.9, 'fpmwhs': 1.0}]}}


def _carga(nombre='Carga nueva sintética', kw=1000.0, anio=2, etapas=()):
    return CargaNueva(sed='', hoja='Nuevas', alimentador='AL1', barra='', lat=None, lon=None, kva_instalado=1250.0,
                      kw=kw, kvar=200.0, fp=0.98, anio_ingreso=anio, etapas=etapas, descripcion=nombre)


def test_107_rf9_usuarios_demanda_incorporada_del_libro_con_su_ingreso_y_sus_factores_deducidos():
    """107:RF-9 (PIT-F113-118) — una carga del libro de cargas nuevas entra en su año de ingreso, se ubica por su
    alimentador (SET, barra y tensión) y da F-114 a F-118 con el FC, el FCP y el FS de su devanado, anotados como
    deducidos; F-115 lleva las pérdidas de su nivel (MT · PEMT) de la fijación de la empresa."""
    mod = _modulo()
    registro, empresa, fe = _registro_y_empresa()
    ub = mod.ubicacion_de_alimentadores(TOPO, _red())
    assert ub['AL1'] == {'sistema': 'SIS-1', 'set': 'SET-A', 'devanado': 'TA:lv', 'barra': 'BA', 'tension_kv': 10.0,
                         'motivo': None}
    p = mod.proyeccion_usuarios(registro, empresa, SALIDA_3B, ub, anio_0=2030, cargas_nuevas=[_carga()], fecha=FECHA)
    f116 = p['filas']['F-116'][0]
    assert f116['potencia_mw'][:4] == [0.0, 0.0, 1.0, 1.0] and f116['set'] == 'SET-A' and f116['barra'] == 'BA'
    assert p['filas']['F-117'][0]['potencia_mw'][2] == pytest.approx(0.8)
    assert p['filas']['F-118'][0]['potencia_mw'][2] == pytest.approx(0.6)
    e = p['filas']['F-114'][0]['energia_mwh'][2]
    assert e == pytest.approx(1.0 * 8760 * 0.5) and p['filas']['F-115'][0]['energia_mwh'][2] == pytest.approx(e * fe['PEMT'])
    assert mod.DEDUCIDO in p['filas']['F-117'][0]['_motivos']['_calculo:potencia_mw']
    uno = p['filas']['F-113'][0]
    assert uno['maxima_mw'] == 1.0 and uno['coincidente_set_mw'] == pytest.approx(0.8) and uno['fphms'] == 0.9


def test_107_rf9_usuarios_libre_del_perfil_y_carga_fraccionada_por_etapas():
    """107:RF-9 (PIT-F113-118) — un usuario libre de pit.usuarios_libres entra desde el año 0; una carga fraccionada
    suma sus etapas año a año; un usuario sin alimentador conocido queda sin ubicación con su motivo."""
    mod = _modulo()
    registro, empresa, _fe = _registro_y_empresa()
    libres = mod.usuarios_del_perfil({'pit': {'usuarios_libres': [
        {'nombre': 'Usuario libre sintético', 'alimentador': 'AL2', 'kw': 3000},
        {'nombre': 'Usuario sin red', 'alimentador': 'AL9', 'kw': 500}]}})
    ub = mod.ubicacion_de_alimentadores(TOPO, _red())
    p = mod.proyeccion_usuarios(registro, empresa, SALIDA_3B, ub, anio_0=2030, libres=libres, fecha=FECHA,
                                cargas_nuevas=[_carga(etapas=((2031, 400.0), (2033, 600.0)))])
    filas = {f['nombre']: f for f in p['filas']['F-116']}
    assert filas['Carga nueva sintética']['potencia_mw'][:4] == [0.0, 0.4, 0.4, 1.0]
    assert filas['Usuario libre sintético']['potencia_mw'][0] == 3.0
    assert filas['Usuario sin red']['set'] is None and 'AL9' in filas['Usuario sin red']['_motivos']['set']
    with pytest.raises(PitError, match='kw'):
        mod.usuarios_del_perfil({'pit': {'usuarios_libres': [{'nombre': 'X', 'alimentador': 'AL1', 'kw': 0}]}})


def test_107_rf9_usuarios_sin_ninguna_fuente_salen_vacios_con_su_aviso_y_llenan_por_el_motor():
    """107:RF-9 (PIT-F113-118) — sin cargas nuevas ni usuarios libres, F-113 a F-118 salen vacíos con su aviso (nunca
    con una causa genérica) y ya no están entre los pendientes; con ellos, el motor los llena en la plantilla."""
    mod = _modulo()
    from convertersmartgrid.adaptadores.pit import llenado
    registro, empresa, _fe = _registro_y_empresa()
    ub = mod.ubicacion_de_alimentadores(TOPO, _red())
    vacia = mod.proyeccion_usuarios(registro, empresa, SALIDA_3B, ub, anio_0=2030, fecha=FECHA)
    assert all(not f for f in vacia['filas'].values()) and 'pit.usuarios_libres' in vacia['avisos'][0]
    assert vacia['para_resumen'] == {'sin_usuarios_libres': vacia['avisos'][0]}
    assert not set(llenado.CAUSAS_DE_PENDIENTE) & {f'F-11{n}' for n in range(3, 9)}
    llena = mod.proyeccion_usuarios(registro, empresa, SALIDA_3B, ub, anio_0=2030, cargas_nuevas=[_carga()], fecha=FECHA)
    hecho = llenado.llenar_formatos(registro, {'usuarios': {'fuente': FUENTE, 'proyeccion': llena, 'area': 'AREA-S'}},
                                    FECHA)
    estados = {f['codigo']: f['estado'] for f in hecho['formatos']}
    assert all(estados[f'F-11{n}'] == 'llenado' for n in range(3, 9))
    c113 = {c['celda']: c['valor'] for c in hecho['resultados']['F-113']['celdas']}
    assert c113['F-113!D15'] == 'Carga nueva sintética' and c113['F-113!B4'] == 'AREA-S'
    c116 = {c['celda']: c['valor'] for c in hecho['resultados']['F-116']['celdas']}
    assert c116['F-116!H13'] == 1.0 and c116['F-116!F13'] == 0.0


def test_107_rf9_usuarios_se_suman_en_los_resumenes_f119_a_f122():
    """107:RF-9 (PIT-F113-118) — la proyección de los usuarios es la parte «libres» de los resúmenes: F-120 suma por
    barra la F-116 de los usuarios con la F-110 de los regulados."""
    mod = _modulo()
    from convertersmartgrid.adaptadores.pit.demanda_cadena import cadena_regulatoria
    from convertersmartgrid.adaptadores.pit.demanda_resumen import resumen_demanda
    registro, empresa, _fe = _registro_y_empresa()
    salida = {**SALIDA_3B, 'f102': {'filas': [{'sistema': 'SIS-1', 'set': 'SET-A', 'devanado': 'TA:lv'}]}}
    ventas = {'SIS-1': {n: [100.0] * 31 for n in ('at', 'mt', 'bt')}}
    cadena = cadena_regulatoria(registro, empresa, salida, _red(), ventas, fecha=FECHA)
    p = mod.proyeccion_usuarios(registro, empresa, salida, mod.ubicacion_de_alimentadores(TOPO, _red()), anio_0=2030,
                                cargas_nuevas=[_carga(anio=0)], fecha=FECHA)
    r = resumen_demanda(registro, cadena, p['para_resumen'], FECHA)
    reg = cadena['filas']['F-110'][0]['potencia_mw'][0]
    fila = next(f for f in r['filas']['F-120'] if f['barra'] == 'BA')
    assert fila['potencia_mw'][0] == pytest.approx(reg + 1.0)
