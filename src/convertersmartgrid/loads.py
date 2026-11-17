"""Compatibilidad (002 T7, a): el cuerpo de este módulo pasó entero, sin cambios, a
``convertersmartgrid.dominio.cargas_plantilla``: solo lee y valida filas, sin E/S, así que es dominio. Esta ruta
vieja se retira con la T9 (RF-21); hasta entonces reexporta sus nombres."""
from __future__ import annotations

from .dominio.cargas_plantilla import (  # noqa: F401 (reexportación temporal de 002:RF-21)
    SHEET_COLUMNS as SHEET_COLUMNS,
    EXTRA_COLUMNS as EXTRA_COLUMNS,
    ENTRY_COLUMNS as ENTRY_COLUMNS,
    CONFLICT_REL_TOL as CONFLICT_REL_TOL,
    CONFLICT_FP_TOL as CONFLICT_FP_TOL,
    COLUMN_ALIASES as COLUMN_ALIASES,
    ACTION_UPDATE as ACTION_UPDATE,
    ACTION_SKIP as ACTION_SKIP,
    VALID_ACTIONS as VALID_ACTIONS,
    SUPPORTED_SUFFIXES as SUPPORTED_SUFFIXES,
    LoadTemplateError as LoadTemplateError,
    normalise_header as normalise_header,
    canonical_columns as canonical_columns,
    SedLoad as SedLoad,
    SheetRead as SheetRead,
    parse_number as parse_number,
    resolve_power as resolve_power,
    power_conflict as power_conflict,
    read_sheet as read_sheet,
)
