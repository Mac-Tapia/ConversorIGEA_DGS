# Plan — Spec 072

Lee: `docs/constitution.md` y `specs/072-pide-y-planeamiento-de-largo-plazo/spec.md`.

Se reutilizan `pide.py`, `pide_economia.py`, `tools/pide_pf.py`, `crecimiento.py`, 042/052, 046, 048, `informe_docx.py`,
`asistente/ejemplos_pide.py`, `pide_dataset.py`, `vnr_etl` y el perfil de empresa.

| Parte nueva | Cubre | Encaje |
| --- | --- | --- |
| Estudio de planeamiento: año de presentación, año 00, años | RF-1 a RF-4 | Contenedor sobre 030 |
| Contrato de fuentes de costos y adaptadores | RF-5 a RF-9 | Dentro de `pide_economia` |
| Metrados desde la red | RF-7, RF-15 | Alimenta F02, F08 y F13 |
| Proyección de mercado | RF-10, RF-11 | 031/046, puerta de entrada al escalado |
| Obras acumuladas por año | RF-12 | `tools/pide_pf.py`, en «Con proyecto» |
| Evaluación con y sin proyecto, F01 a F15 | RF-13, RF-14 | Amplía `pide_economia` |
| Generadores 4.1 y 4.2 | RF-13, RF-14, RF-16 | `informe_docx.py`, perfil de empresa |
| Herramientas y entrenamiento del asistente | RF-18, RF-19 | Coordinado con la spec 070 |

Fuentes públicas ubicadas el 2026-11-02, en Procesos Regulatorios de Osinergmin: SICODI y VNR al 31-12-2025 (Res. 184-2026-OS/CD);
VNR de Electro Oriente, fijación 2022 (Res. 186-2023-OS/CD). Falta el fichero de módulos estándar (Res. 152-2026-OS/CD).

Coordinación: `pide_economia` y `escalera_optima` también los toca la 073; se avisa la zona antes de escribir.
