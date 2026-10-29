# Plan — Spec 033

Estado: aprobado (2026-10-29) · Spec: [spec.md](spec.md)

## Decisiones

- **Un solo lector de specs.** `tools/estado_specs.py` lee la numeración, las tareas, el
  estado y las citas de las pruebas; lo usan la suite (`tests/test_trazabilidad_specs.py`),
  la 009 (`tests/test_inventario.py`) y el `specs/README.md` que genera. Descartado: copiar
  las expresiones en cada prueba, que es como la 009 dejó de ver los RF de letra.
- **No se renumera nada.** Los huecos se declaran con «no se usa(n)»; las segundas
  definiciones pasan a «Aclaración de RF-n». Descartado: renumerar, que rompería las 1 636
  pruebas que citan `NNN:RF-n`.
- **Tareas de DIgSILENT marcadas.** `[DIgSILENT]` tras el número. Una tarea con código hecho
  y la prueba en DIgSILENT pendiente se parte en dos: el código se cierra con sus pruebas y la
  prueba en DIgSILENT queda como tarea nueva. Descartado: dejar la frase «a cargo del usuario»,
  que no usaban las specs desde la 011.
- **El código sin spec va a una spec retrospectiva (034)**, no a la 001 ni a «base».
- **Estado generado.** `specs/README.md` lo escribe la herramienta; `CLAUDE.md` deja una línea
  por spec con su estado, comprobada contra la spec.

## Partes

| Parte | Ficheros | RF |
| --- | --- | --- |
| Lector y tabla | `tools/estado_specs.py`, `specs/README.md` | RF-14 |
| Comprobaciones | `tests/test_trazabilidad_specs.py`; `tests/test_inventario.py` usa el mismo lector | RF-1 a RF-21 |
| Corrección de las specs | `specs/*/spec.md`, `tasks.md`, `plan.md`; carpetas reservadas 003 y 031 | RF-1 a RF-13 |
| Pruebas que faltaban | citas en las pruebas que ya lo verificaban; pruebas nuevas de 013:RF-7, RF-10, RF-15 y de 034:RF-33 | RF-16, RF-18 |
| Código sin spec | `specs/034-*`, `CODIGO_FUENTE.md` | RF-19, RF-20 |
| `CLAUDE.md` y skill | tabla reducida y reglas en `.claude/skills/igea-dgs-spec/SKILL.md` | RF-15, RF-22 |

## Pruebas

Solo leen ficheros del repositorio y `git log`: sin datos de la distribuidora ni DIgSILENT.
