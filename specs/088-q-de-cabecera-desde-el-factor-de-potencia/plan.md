# Plan — Spec 088

Lee: `docs/constitution.md`, 006, 035.

| Parte | Cubre | Encaje |
| --- | --- | --- |
| `demanda_medida.q_negativa_con_fp` | RF-1 a RF-5, RF-7, RF-8 | Función pura sobre los registros de un medidor |
| `demanda_medida.Cabecera._medir` | RF-6, RF-9, RF-10 | Todos los caminos de lectura pasan por ella, antes de `maxima_de_registros` |

## Decisiones

- **En `Cabecera`.** Calibración, valle, crecimiento y pronóstico leen por ella. Se descartó una lista de medidores en el perfil: la regla es para cualquier alimentador (usuario, 2026-11-05).
- **El signo, respecto de P.** Se descartó forzar +Q con `lag`: da mal el balance de las centrales.
- **Sin `lead` ni `lag`, kW/kVA.** `PF sign tot us` no es un FP en estos libros (`fp_decimal`). El kVA es lo medido, y el signo queda el del kVAR porque no hay dato que lo cambie.

## Pruebas

`tests/test_q_desde_fp.py`: libros sintéticos con `openpyxl`, sin tamaños fijos de red, y la medición real con `CSG_DEMANDA_DIR`. No toca el lector de TXT, MDB ni VNR-GIS, ni las disposiciones de export.
