"""Lectura CAPEX y recibo de su fuente efectiva, sin copiar el libro (072:RF-28)."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ... import pide_economia
from ..fuentes_estables import abrir_fuente_estable


def leer_capex_con_procedencia(
    ruta: Path | str, config: Mapping[str, Any], *, contexto_unidades: Mapping[str, Any],
) -> tuple[list[pide_economia.ObraCapex], list[str], dict[str, Any]]:
    """El recibo identifica los bytes y opciones que consumió el único lector CAPEX.

    La configuración mutable se fija antes de abrir: el recibo y el lector reciben la
    misma selección de hoja/columnas. La escala/moneda son las declaradas por el cálculo;
    este adaptador no convierte valores ni acredita vigencia/aprobación presupuestal.
    """
    # Solo las opciones consumidas por el lector y el cálculo: un perfil también
    # puede contener contactos u otros metadatos que no pertenecen a este recibo.
    configuracion = deepcopy({k: config[k] for k in ('hoja', 'fila_cabecera_contiene', 'columnas') if k in config})
    unidades = deepcopy({k: contexto_unidades[k] for k in ('moneda', 'escala_aplicada', 'escala_capex', 'tipo_cambio')
                         if k in contexto_unidades})
    with abrir_fuente_estable(ruta) as fuente:
        obras, avisos = pide_economia.leer_capex(fuente.stream, configuracion)
        recibo = {
            'schema_version': 1,
            'fuente': {'ruta': str(fuente.path), 'sha256': fuente.sha256,
                       'bytes': fuente.size, 'mtime_ns': fuente.stat.st_mtime_ns},
            'lectura_utc': datetime.now(timezone.utc).isoformat(),
            'hoja': configuracion.get('hoja'), 'config': configuracion,
            'lector': {'read_only': True, 'data_only': True},
            'unidades': sorted({o.unidad for o in obras if o.unidad}),
            'contexto_unidades': unidades,
            'unidades_no_declaradas': [k for k in ('moneda', 'escala_aplicada')
                                      if unidades.get(k) in (None, '') and
                                      not (k == 'escala_aplicada' and unidades.get('escala_capex') is not None)],
        }
    return obras, avisos, recibo
