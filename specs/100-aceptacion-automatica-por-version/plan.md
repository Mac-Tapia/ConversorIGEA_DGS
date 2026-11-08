# Plan 100 — Aceptación automática por versión

## Dónde

- `config/aceptacion/matriz.json`: los casos, sin datos de la distribuidora (RF-1, RF-5).
- `tools/aceptacion_version.py`, nueva: recorre la matriz reutilizando `tools/sistema_web.py` y `tools/aceptacion_nativa.py`, sin repetir la API (RF-2, RF-3, RF-5, RF-7).
- Reutiliza el retomar de `sistema_web.py` y el diario de trabajos (086:RF-9) para relanzar (RF-5).

## Decisión

Una herramienta sobre lo que ya existe, y no pruebas de pytest con DIgSILENT, porque 084:RF-21 las separa.

## Pruebas

Sintéticas con una web falsa: orden de la matriz, relanzado, informe, veredicto y que ninguna fuente se mezcle.
