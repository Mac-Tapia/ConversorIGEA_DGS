# Plan — Spec 029

Estado: cumplida (2026-10-29) · Spec: [spec.md](spec.md)

Escrito el 2026-10-29 (revisión 033) con el plan que estaba en el encabezado de `tasks.md`.

| Parte | Ficheros | RF |
| --- | --- | --- |
| Tasa por alimentador: máximas mensuales, tasa compuesta entre los meses comunes del primer y el último año, mediana para los demás | `src/igea_dgs/crecimiento.py` (lee los libros con `demanda_medida.maximas`) | RF-1 a RF-3, RF-5, RF-7 |
| La tasa en el PIDE: `pide_ejecutar` la calcula si el perfil no la trae y la pasa por alimentador; el guion escala el `scale0` de sus cargas y lo devuelve al terminar | `src/igea_dgs/web/services.py`, `tools/pide_pf.py` | RF-1, RF-4 a RF-6 |

Decisión: se lee en el proceso del trabajo (`JobContext.en_proceso`, 027:RF-25) y no en el de
la API, porque los libros de cabecera tardan. Alternativa descartada: calcularla al abrir el
espacio, que la recalcularía sin que nadie la pidiera.

Pruebas: `tests/test_crecimiento.py` con curvas sorteadas y `tests/test_pide_pf.py` con
`fake_pf`; Chincha en DIgSILENT (T3).
