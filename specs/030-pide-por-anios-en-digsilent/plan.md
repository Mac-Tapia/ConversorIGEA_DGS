# Plan — Spec 030

Estado: cumplida (2026-10-29) · Spec: [spec.md](spec.md)

Escrito el 2026-10-29 (revisión 033) a partir de lo implementado (T1) y probado en DIgSILENT
(T2).

| Parte | Ficheros | RF |
| --- | --- | --- |
| Carpeta «PIDE/Año NN» en los casos y en los escenarios de operación, con «Sin proyecto», «Cargas nuevas» y «Con proyecto» de cada año y la demanda del año en su escenario | `tools/pide_pf.py` | RF-1 a RF-9, RF-11, RF-12, RF-15 |
| Plan del PIDE por años desde la web y cargas del año | `src/igea_dgs/web/services.py`, `src/igea_dgs/cargas_pf.py` | RF-10, RF-13, RF-14 |

Pruebas: `tests/test_pide_pf.py` y `tests/test_cargas_pf.py` con `fake_pf`; Chincha con
«PIDE/Año 00…20» en DIgSILENT (T2).
