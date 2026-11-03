# Plan — Auditoría y arranque fiable

Estado: cumplida (2026-11-03) · Spec: [spec.md](spec.md)

| Parte | Implementación | Verificación |
| --- | --- | --- |
| Vigilancia RAM reproducible | `requirements.txt`, extra `all` de `pyproject.toml`, comprobador `web/runtime.py` | Declaraciones concordantes y detección de ausencia de `psutil` (RF-1) |
| Extractor PDF instalable | `requirements.txt`, extras `pide` y `all` | Declaraciones y extractor real del corpus (RF-2) |
| Arranque interrumpido si npm falla | `run_gui.bat`: comprobar los dos códigos de salida y restaurar el directorio | Ejecutar el batch real en directorio aislado, con npm que devuelve un fallo controlado; no abrir navegador ni servidor real (RF-3) |
| Inventario y documentación | `docs/AUDITORIA_RAIZ_2026-11-03.md`, README, arquitectura, manual e índice | Evidencia de consumidores, inventario de todas las carpetas de la raíz, relaciones y pendientes conservados |
| Limpieza | Retirada el 2026-11-03: ver T5 en `tasks.md` | Nada se borra |

Decisión: corregir las declaraciones y el límite del lanzador sin sustituir la instalación
editable ni introducir un empaquetado wheel nuevo. La falta de import directo no basta para
borrar herramientas invocadas por ruta, reexportaciones de compatibilidad o datos de custodia.
