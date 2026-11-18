"""Manifiesto del benchmark: lo que hace falta para reproducirlo sin revelar el origen (112:RF-5, RF-12).

Lleva la huella SHA-256 del contenido del origen (y la del dataset del 089, si lo hay), la versión del generador, la
semilla PÚBLICA (nunca la de los seudónimos, RF-12), las transformaciones, las columnas omitidas por nombre, la
tolerancia con su fuente, las métricas de referencia del original y del benchmark y la huella de cada fichero emitido.
Se escribe en JSON canónico (``evaluacion_harness.contratos``): el mismo contenido da los mismos bytes.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ...dominio.evaluacion_harness.contratos import canonico

NOMBRE = 'manifiesto.json'
ESQUEMA = 'csg-benchmark-v1'

TRANSFORMACIONES_RED = (
    'identificadores por permutación sorteada por tipo, coherentes entre RED, CARGA y BD_Equipo',
    'coordenadas de un trazado sintético por el grafo, en un origen neutro lejos del original',
    'longitudes eléctricas perturbadas con la semilla secreta, recortadas a la tolerancia del estudio',
    'solo las secciones y columnas de una lista cerrada; el texto libre fuera',
    'los tipos sin ficha, con la ficha que el modelo toma por parecido de nombre',
    'perfil de empresa neutro, con el patrón de medición traducido a los seudónimos',
)
TRANSFORMACIONES_SERIES = (
    'series: identificador del mapa, escala sorteada en [0,5, 2] y semanas completas desplazadas',
    'series: feriados, temperatura y mes de calendario como columnas; la potencia solo en bandas',
)
RIESGOS_SERIES = (
    'series: con el mes y el día de la semana de cada fila se rehace la fecha original (aclaración de RF-11); los '
    'valores van escalados y los identificadores seudonimizados',
)
RIESGOS = (
    'con la semilla secreta y la lista de códigos originales se rehace el mapa: la semilla se queda en el equipo',
    'una serie de patrón único (una carga industrial) conserva su forma: solo se publica su banda de potencia',
    'derivado de una red real: solo para uso local, la vía de publicación lo rechaza (aclaración de RF-13 y RF-14)',
)


def huella_ficheros(rutas: Iterable[Path | str]) -> str:
    """SHA-256 del contenido de los ficheros del origen, en su orden, sin sus nombres ni sus rutas."""
    h = hashlib.sha256()
    for ruta in rutas:
        datos = Path(ruta).read_bytes()
        h.update(len(datos).to_bytes(8, 'big'))
        h.update(datos)
    return h.hexdigest()


def revision_git() -> str | None:
    """La revisión del código que generó el benchmark, si se genera desde un árbol de git; si no, ``None``."""
    from ...dominio.runtime_paths import raiz_programa

    try:
        r = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=raiz_programa(), capture_output=True, text=True,
                           timeout=10, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    texto = r.stdout.strip()
    return texto if len(texto) == 40 else None


def construir(*, huella_origen: str, huella_089: str | None, semilla_publica: str, columnas_omitidas: Mapping,
              secciones_omitidas: Mapping, tipos_completados: int, tolerancia, perfil_neutro,
              metricas: Mapping[str, Any], carpeta: Path, con_series: bool,
              geometria: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """El manifiesto, ya normalizado como lo leerá cualquiera: lo que se devuelve es lo que se escribe."""
    from ... import __version__

    ficheros = _ficheros(carpeta)
    manifiesto = {
        'esquema': ESQUEMA,
        'uso_local': True,
        'origen': {'huella': huella_origen, 'huella_089': huella_089},
        'generador': {'version': __version__, 'revision': revision_git()},
        'semilla_publica': semilla_publica,
        'transformaciones': list(TRANSFORMACIONES_RED) + (list(TRANSFORMACIONES_SERIES) if con_series else []),
        'columnas_omitidas': columnas_omitidas,
        'secciones_omitidas': secciones_omitidas,
        'tipos_completados': tipos_completados,
        'tolerancia': asdict(tolerancia),
        'metricas_referencia': metricas,
        'perfil_neutro': asdict(perfil_neutro),
        'ficheros': ficheros,
        'riesgos': list(RIESGOS) + (list(RIESGOS_SERIES) if con_series else []),
    }
    if geometria is not None:
        manifiesto['geometria'] = dict(geometria)
    return json.loads(canonico(manifiesto))


def _ficheros(carpeta: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(carpeta).iterdir()) if p.is_file() and p.name != NOMBRE}


def construir_publicable(*, huellas_origen: Iterable[str], semilla_publica: str, minimos: Mapping[str, int],
                         estadisticas: Mapping[str, Any], carpeta: Path,
                         geometria: Mapping[str, Any]) -> dict[str, Any]:
    """El manifiesto de la red sintética publicable: agregados, mínimos y control, sin ninguna métrica del origen."""
    from ... import __version__

    manifiesto = {
        'esquema': ESQUEMA,
        'uso_local': False,
        'origen': {'huellas': sorted(huellas_origen)},
        'generador': {'version': __version__, 'revision': revision_git()},
        'semilla_publica': semilla_publica,
        'transformaciones': ['red sintética (ExportSpec) con los recuentos y los cuantiles agregados del origen; '
                             'ningún tramo, nudo ni carga del origen'],
        'minimos': dict(minimos),
        'estadisticas': dict(estadisticas),
        'geometria': dict(geometria),
        'ficheros': _ficheros(carpeta),
    }
    return json.loads(canonico(manifiesto))


def escribir(carpeta: Path | str, manifiesto: Mapping[str, Any]) -> Path:
    ruta = Path(carpeta) / NOMBRE
    ruta.write_bytes(canonico(manifiesto))
    return ruta
