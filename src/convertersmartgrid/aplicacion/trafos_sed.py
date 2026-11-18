"""Transformadores nuevos para las SED fijas sobrecargadas (spec 020, RF-6 a RF-11).

Por qué. En PA217 (2026-10-16) la SED fija SE30940 recibía los 3818 kVA de su cliente
sobre 400 kVA (955 %), y con cargas PQ «Sin proyecto» no convergía ni con las escaladas al
0,5 % de su kVA. Se resolvió a mano (015, T26) con la menor potencia de la ficha que deja
la máxima al 80 % o menos y, por encima de la mayor de la tabla (630 kVA en la NTP
370.400), unidades iguales en paralelo: las fórmulas de la norma para potencias fuera de
tabla no valen tan lejos (la de pérdidas con carga decrece desde unos 1600 kVA).

Las tablas y el umbral vienen del perfil de empresa (``perfil_empresa.transformadores_sed``),
nunca del código (P13). Esta regla es distinta de ``sed_potencia``, que corre al convertir
con la carga del archivo, cubre el 100 % y no lleva ficha.
"""

from __future__ import annotations

import math
from typing import Any


def sed_sobre_umbral(demandas_kva: dict[str, float], kva: dict[str, float | None],
                     umbral_pct: float) -> list[dict[str, Any]]:
    """SED fijas o escaladas cuya demanda calibrada pasa del umbral del perfil (032:RF-20, RF-28).

    Antes solo se miraban las fijas por encima del 100 % (020:RF-1), y las SED que el
    conversor redimensionaba al convertir dejaban de verse en el «Caso base». Con los kVA
    del archivo (032:RF-1) la propuesta va aquí. ``nivel`` distingue las que pasan del
    100 % (``sobre_100``) de las que están entre el umbral y el 100 % (``sobre_umbral``).
    Una SED sin potencia instalada no se compara.
    """
    out = []
    for sed, s in demandas_kva.items():
        k = kva.get(sed)
        if not k or k <= 0:
            continue
        pct = 100.0 * s / k
        if pct > umbral_pct + 1e-9:
            out.append({'sed': sed, 'kva_carga': s, 'kva': k, 'carga_pct': pct,
                        'nivel': 'sobre_100' if pct > 100.0 + 1e-9 else 'sobre_umbral'})
    return sorted(out, key=lambda x: (-x['carga_pct'], x['sed']))


def tabla_para(tablas: list[dict[str, Any]], kv_primaria: float | None) -> dict[str, Any] | None:
    """La tabla cuyo rango (``kv_min`` excluido, ``kv_max`` incluido) tiene la tensión (RF-8)."""
    if kv_primaria is None:
        return None
    return next((t for t in tablas if t['kv_min'] < kv_primaria <= t['kv_max']), None)


def nombre_tipo(kva: float, codigo: str, kv_at: float | None, v_bt: float | None,
                grupo: str | None) -> str:
    """Nombre del tipo propio, el mismo que se creó a mano en PA217 (015, T26; 020:RF-21).

    ``TR_630kVA_NTP370400_22.9-220V_DYN5``: potencia, norma, tensiones y grupo, para que dos
    SED de distinta tensión de baja o grupo no compartan tipo. DIgSILENT guarda 22,9 kV como
    22.899999618…: se redondea antes de escribirlo.
    """
    at = '?' if kv_at is None else f'{round(kv_at, 3):g}'
    bt = '?' if v_bt is None else f'{round(v_bt, 1):g}'
    partes = [f'TR_{kva:g}kVA'] + ([codigo] if codigo else []) + [f'{at}-{bt}V']
    return '_'.join(partes + ([grupo.upper()] if grupo else []))


def proponer(kva_carga: float, kv_primaria: float | None, tablas: list[dict[str, Any]],
             umbral_pct: float) -> dict[str, Any]:
    """Potencia, unidades en paralelo y ficha para una demanda de ``kva_carga`` (RF-6, RF-7).

    Sin propuesta (RF-10, RF-11), ``kva`` es ``None`` y ``motivo`` dice por qué.
    """
    if not tablas:
        return {'kva': None, 'motivo': 'el perfil de empresa no trae tablas de fichas de '
                                        'transformadores (calibracion.transformadores_sed)'}
    tabla = tabla_para(tablas, kv_primaria)
    if tabla is None:
        tension = 'desconocida' if kv_primaria is None else f'{kv_primaria:g} kV'
        return {'kva': None, 'motivo': f'la tensión primaria ({tension}) no cae en ninguna '
                                        'tabla de fichas del perfil'}
    limite = umbral_pct / 100.0
    tamanos = sorted(tabla['fichas'])
    kva = next((k for k in tamanos if kva_carga <= limite * k), None)
    unidades = 1
    if kva is None:
        kva = tamanos[-1]
        unidades = math.ceil(kva_carga / (limite * kva))
    po, pc, io, uk = tabla['fichas'][kva]
    return {'kva': kva, 'unidades': unidades, 'po_w': po, 'pc_w': pc, 'io_pct': io,
            'uk_pct': uk, 'norma': tabla['norma'], 'codigo': tabla['codigo'],
            'carga_pct_prevista': 100.0 * kva_carga / (kva * unidades)}
