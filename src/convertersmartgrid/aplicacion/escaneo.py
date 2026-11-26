"""Escaneo de un alimentador en DIgSILENT antes de recalibrar (spec 028).

Reglas sin DIgSILENT: de quién es cada generador, banco y variación que lee
``tools/escanear_alimentador_pf.py``, y qué barra toma la central de un alimentador. Lo propio
del conversor se reconoce solo por sus prefijos (RF-7): en Nasca (2026-10-28) el usuario pone
a mano la central y los bancos de NA295, y la calibración tiene que verlos sin que ningún
nombre de empresa, central o alimentador esté escrito en el código.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: Prefijos de lo que crea el conversor, con quién lo crea (specs 004, 006, 007, 011, 016, 021, 022).
PREFIJOS_PROPIOS: tuple[tuple[str, str], ...] = (
    ('Central_', 'central de la calibración (021)'),
    ('BC_CAL_', 'banco de la calibración (021:RF-64)'),
    ('Obra_', 'obra (011, 016)'),
    ('Carga_', 'carga nueva (007)'),
    ('Ajuste_', 'ajuste (006)'),
    ('Demandas_', 'demandas (004)'),
    ('Estudio_', 'estudio (011)'),
    ('Transferencia_', 'transferencia (011)'),
    ('REC_', 'tramo reconstruido (022)'),
    ('Fichas_', 'conductores con su ficha (032)'),
    ('SED_NTP_', 'transformadores de SED con su ficha (032)'),
)

#: Variaciones del catálogo (spec 032): activas en «Sin proyecto» y «Con proyecto», nunca en
#: el «Caso base», que conserva los conductores y los kVA del archivo (032:RF-27).
PREFIJOS_CATALOGO: tuple[str, ...] = ('Fichas_', 'SED_NTP_')

#: Clases de generador que se buscan en el alimentador (RF-2).
CLASES_GENERADOR: tuple[str, ...] = ('ElmGenstat', 'ElmSym', 'ElmPvsys', 'ElmAsm')


def origen_de(nombre: str, variacion: str | None = None) -> dict[str, Any]:
    """Quién creó un objeto: el conversor, por su nombre o el de su variación, o el operador
    (RF-3, RF-4, RF-5, RF-7)."""
    for texto in (nombre or '', variacion or ''):
        for prefijo, que in PREFIJOS_PROPIOS:
            if texto.startswith(prefijo):
                return {'origen': 'conversor', 'por': que}
    return {'origen': 'operador', 'por': None}


def resumen(escaneo: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    """Cuántos generadores, bancos y cargas cambiadas tiene cada alimentador, y de quién."""
    out = {}
    for a, d in (escaneo.get('alimentadores') or {}).items():
        gens = d.get('generadores') or []
        bancos = d.get('bancos') or []
        out[a] = {'generadores': len(gens),
                  'generadores_del_operador': sum(g.get('origen') == 'operador' for g in gens),
                  'bancos': len(bancos),
                  'bancos_del_operador': sum(b.get('origen') == 'operador' for b in bancos),
                  'bancos_de_calibracion': sum(b.get('origen') == 'conversor' for b in bancos),
                  'cargas_cambiadas': len(d.get('cargas_cambiadas') or []),
                  'tramos_nuevos': len(d.get('tramos_nuevos') or []),
                  'tramos_cambiados': len(d.get('tramos_cambiados') or [])}           # RF-26
    return out


def nodo_de_central(escaneo: Mapping[str, Any] | None, alimentador: str) -> str | None:
    """La barra de la central de ``alimentador`` según el escaneo (RF-11, RF-12, RF-15).

    La del generador en servicio que puso el operador y, si no hay, la del que creó la
    calibración. Con dos o más barras distintas del mismo origen no se elige: lo decide el
    operador.
    """
    d = ((escaneo or {}).get('alimentadores') or {}).get(alimentador) or {}
    gens = [g for g in d.get('generadores') or [] if g.get('en_servicio') and g.get('barra')]
    for origen in ('operador', 'conversor'):
        barras = sorted({str(g['barra']) for g in gens if g.get('origen') == origen})
        if len(barras) == 1:
            return barras[0]
        if barras:
            return None
    return None




#: 028:RF-45: qué se compara de cada clase entre el «Caso base» y «Sin proyecto», y bajo qué lista sale.
CLASES_FRENTE_AL_BASE = {'ElmLne': 'tramo', 'ElmLod': 'carga', 'ElmLodlv': 'carga', 'ElmShnt': 'banco',
                         'ElmCoup': 'maniobra', 'StaSwitch': 'maniobra', 'ElmTr2': 'sed'}
#: 028:RF-45 (usuario, 26-11): de un tramo solo cuentan las obras, otro conductor (la sección) o más ternas; la longitud y
#: los parámetros de su ficha no («solo cuando se haya incrementado nueva terna o cambiado de sección de cable»).
CAMBIOS_DE_OBRA_EN_TRAMOS = ('tipo', 'ternas')


def diferencias_frente_al_base(base: Mapping[tuple[str, str], Mapping[str, Any]],
                               sin: Mapping[tuple[str, str], Mapping[str, Any]]) -> dict[str, list]:
    """028:RF-45 — lo que cambió en «Sin proyecto» respecto del «Caso base», donde el operador no tocó nada.

    ``base`` y ``sin`` son la foto de un alimentador en cada caso: ``(clase, nombre) → atributos``. Salen los tramos y
    bancos nuevos, los tramos quitados y lo cambiado de tramos, cargas, bancos y maniobras con su antes y su después;
    lo igual no sale. El 26-11 el operador cambió en «Sin proyecto» de PA217 tramos, cargas, bancos y maniobras y el
    escaneo decía «ninguno»: solo comparaba con el DGS, las variaciones del operador y la última calibración.
    """
    out: dict[str, list] = {k: [] for k in ('tramos_nuevos', 'tramos_cambiados', 'tramos_quitados', 'cargas_cambiadas',
                                            'bancos_nuevos', 'bancos_cambiados', 'maniobras_cambiadas', 'sed_nuevas',
                                            'sed_cambiadas')}
    for clave in sorted(set(base) | set(sin)):
        clase, nombre = clave
        que = CLASES_FRENTE_AL_BASE.get(clase)
        if que is None:
            continue
        antes, despues = base.get(clave), sin.get(clave)
        if antes is None:
            if que in ('tramo', 'banco'):
                out[f'{que}s_nuevos'].append({que: nombre, **dict(despues or {})})
            elif que == 'sed':
                out['sed_nuevas'].append({'sed': nombre, **dict(despues or {})})
            continue
        if despues is None:
            if que == 'tramo':
                out['tramos_quitados'].append({'tramo': nombre, **dict(antes)})
            continue
        cambios = {k: (antes.get(k), despues.get(k)) for k in sorted(set(antes) | set(despues))
                   if k not in ('desde', 'hasta') and antes.get(k) != despues.get(k)
                   and (que != 'tramo' or k in CAMBIOS_DE_OBRA_EN_TRAMOS)}
        if cambios:
            lista = {'tramo': 'tramos_cambiados', 'carga': 'cargas_cambiadas', 'banco': 'bancos_cambiados',
                     'maniobra': 'maniobras_cambiadas', 'sed': 'sed_cambiadas'}[que]
            out[lista].append({que: nombre, 'cambios': cambios})
    return out
