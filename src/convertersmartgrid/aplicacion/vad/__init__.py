"""Estudio de costos del VAD con la empresa modelo eficiente (spec 108).

Paquete aparte del PIDE (072) y del PIT (107): el VAD tiene otro grupo de empresas, otro periodo, otra norma
(los TdR de la RCD 174-2025-OS/CD, modificados por la 033-2026-OS/CD) y otros entregables (108:RF-1). Este
``__init__`` no importa ningún submódulo: cada uno tiene su capa (``pyproject.toml``) y el paquete se puede
importar sin pandapower ni openpyxl.
"""
from __future__ import annotations


class VadError(ValueError):
    """El estudio no se puede armar como se pide; el mensaje nombra la tabla, el campo o la regla que falla."""
