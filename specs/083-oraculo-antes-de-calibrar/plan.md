# Plan — Spec 083

Lee: `docs/constitution.md` y `specs/083-oraculo-antes-de-calibrar/spec.md`.

| Parte nueva | Cubre | Encaje |
| --- | --- | --- |
| Búsqueda en el oráculo | RF-1, RF-2, RF-3, RF-4 | `oraculo_calibracion.py`, sobre `cuadrar_conjunto` y `Oraculo` |
| Enganche en DIgSILENT | RF-1, RF-4, RF-5, RF-6 | `tools/ajuste_cabecera_pf.py`, antes de `cuadrar_conjunto` y de `cuadrar` |
| Cuadre robusto | RF-7, RF-10, RF-11, RF-12, RF-13 | `ajuste_cabecera.py`: `cuadrar` y `cuadrar_conjunto` |
| Transformadores sin pedirlos | RF-8 | `tools/sistema_web.py` |
| Muestras en el oráculo | RF-20 | `oraculo_calibracion.FlujoOraculo`, usado por `_probabilistico_del_proyecto` y `probabilistico_de_un_alimentador` |
| Motores de flujo | RF-16, RF-17, RF-18, RF-19 | `digital_twin/motores_flujo.py`, sobre `SistemaMallado`; `requirements-motores.txt` |
| Arranque de la última calibración | RF-9 | `tools/ajuste_cabecera_pf.py` y lo que guarda `web/services.py` |
