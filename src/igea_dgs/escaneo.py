"""Escaneo de un alimentador en DIgSILENT antes de recalibrar (spec 028).

Reglas sin DIgSILENT: de quién es cada generador, banco y variación que lee
``tools/escanear_alimentador_pf.py``, y qué barra toma la central de un alimentador. Lo propio
del conversor se reconoce solo por sus prefijos (RF-7): en Nasca (2026-10-28) el usuario pone
a mano la central y los bancos de NA205, y la calibración tiene que verlos sin que ningún
nombre de empresa, central o alimentador esté escrito en el código.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
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
)

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
                  'tramos_nuevos': len(d.get('tramos_nuevos') or [])}
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



def tramos_del_dgs(ruta: Path | str) -> set[str]:
    """Los ``loc_name`` de los tramos (``ElmLne``) de un DGS: los que venían en el aceptado, para
    saber cuáles son nuevos (RF-17)."""
    from .dgs import DGS_ENCODING

    nombres: set[str] = set()
    dentro = False
    with open(ruta, encoding=DGS_ENCODING, errors='replace') as f:
        for linea in f:
            if linea.startswith('$$'):
                dentro = linea.startswith('$$ElmLne;')
                continue
            if dentro and linea.strip() and not linea.startswith('*'):
                campos = linea.strip().split(';')
                if len(campos) > 2:
                    nombres.add(campos[2])
    return nombres
