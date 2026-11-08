"""Puertas de calidad y contaminación del dataset del asistente."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .ajuste_condicionado import MIN_ORDENES_REALES


CALIDADES = (
    'gold_human', 'gold_native', 'silver_deterministic',
    'silver_teacher_verified', 'silver_maestro_texto_real', 'context', 'quarantine',
)


def texto_canonico(texto: str) -> str:
    normalizado = unicodedata.normalize('NFKC', str(texto)).casefold()
    return re.sub(r'\s+', ' ', normalizado).strip()


def resumir_calidad(registros: Iterable[Any]) -> dict[str, Any]:
    filas = list(registros)
    calidades = Counter(str(getattr(r, 'quality', '')) for r in filas)
    tareas = Counter(str(getattr(r, 'tarea', '')) for r in filas if getattr(r, 'tarea', ''))
    return {
        'records': len(filas),
        'qualities': dict(sorted(calidades.items())),
        'tasks': dict(sorted(tareas.items())),
        'unique_groups': len({str(getattr(r, 'group_id', '')) for r in filas}),
    }


def _leaks(valores: Mapping[str, set[str]]) -> list[str]:
    return sorted(valor for valor, particiones in valores.items()
                  if valor and len(particiones) > 1)


def auditar_contaminacion(
    particiones: Mapping[str, Sequence[Any]],
) -> dict[str, Any]:
    """Detecta fuga exacta y de grupo antes de publicar train/validation/test."""
    por_texto: dict[str, set[str]] = defaultdict(set)
    por_grupo: dict[str, set[str]] = defaultdict(set)
    por_alimentador: dict[str, set[str]] = defaultdict(set)
    desconocidas: set[str] = set()
    filas = []
    for nombre, registros in particiones.items():
        for registro in registros:
            filas.append(registro)
            por_texto[texto_canonico(getattr(registro, 'texto', ''))].add(nombre)
            por_grupo[str(getattr(registro, 'group_id', ''))].add(nombre)
            if getattr(registro, 'tipo', '') == 'episodio':                # 043:RF-4
                for alimentador in getattr(registro, 'alimentadores', ()) or ():
                    por_alimentador[str(alimentador)].add(nombre)
            calidad = str(getattr(registro, 'quality', ''))
            if calidad not in CALIDADES:
                desconocidas.add(calidad)
    exactas = _leaks(por_texto)
    grupos = _leaks(por_grupo)
    alimentadores = _leaks(por_alimentador)
    unknown = sorted(desconocidas)
    return {
        'valid': not exactas and not grupos and not alimentadores and not unknown,
        'exact_text_leaks': exactas,
        'group_leaks': grupos,
        'feeder_leaks': alimentadores,
        'unknown_qualities': unknown,
        **resumir_calidad(filas),
    }


def auditar_ordenes(*, reales: int, sinteticas: int, prueba_real: int, parametros: int | None = None,
                    umbrales: Any = None) -> dict[str, Any]:
    """El informe del dataset del asistente (RF-33, RF-34): sus puertas solo valen medidas con
    órdenes reales, y con menos de 200 se pide confirmación de todo (RF-19).

    ``umbrales`` es el de ``digital_twin.auditoria.Umbrales`` u otro con ``min_ordenes_reales``. Está
    aquí, con las puertas de calidad del dataset del asistente, porque lo pide el entrenamiento
    del asistente (aplicación), que no debe importar la auditoría del gemelo (002:RF-2)."""
    minimo = umbrales.min_ordenes_reales if umbrales is not None else MIN_ORDENES_REALES
    avisos = []
    if reales < minimo:
        avisos.append(f'{reales} órdenes reales de las {minimo} que hacen falta: toda acción '
                      'que escribe pide confirmación (027:RF-19).')
    if prueba_real == 0:
        avisos.append('sin órdenes reales en la prueba: sus métricas son de órdenes sintéticas y no valen '
                      'como puertas (027:RF-34).')
    if parametros:
        avisos.append(f'{parametros:,} parámetros frente a {reales + sinteticas:,} órdenes, '
                      f'{reales} reales (027:RF-33).')
    return {'reales': reales, 'sinteticas': sinteticas, 'prueba_real': prueba_real,
            'parametros': parametros,
            'puertas_con_reales': prueba_real > 0 and reales >= minimo,
            'avisos': avisos}
