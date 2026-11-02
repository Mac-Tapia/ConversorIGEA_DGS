"""Puertas de calidad y contaminación del dataset del asistente."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


CALIDADES = (
    'gold_human', 'gold_native', 'silver_deterministic',
    'silver_teacher_verified', 'context', 'quarantine',
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
