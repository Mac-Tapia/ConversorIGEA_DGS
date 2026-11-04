# Auditoría de las carpetas de la raíz — 2026-11-03

Spec 036, tarea T4. El plan citaba un informe del 2026-10-29 con 22 carpetas y un manifiesto de
limpieza: ninguno de los dos llegó a confirmarse ni se encuentra en disco, de modo que este informe
no lo continúa, lo rehace.

## Alcance y límites

- Revisado el checkout principal del repositorio en solo lectura, en esta fecha y este equipo. Otras
  sesiones escriben a la vez, así que el estado de una carpeta no versionada es el de ese momento.
- Tamaños: bytes lógicos de la auditoría externa de almacenamiento del 2026-11-02
  (`almacenamiento.md` de la carpeta de auditorías del 2026-11-02, fuera del repositorio). No se han vuelto a medir,
  y después de esa fecha se retiró parte de `output/` (`output/ml_dependencies`) y la carpeta de datos
  salió del proyecto. Las carpetas comparten enlaces duros: no se pueden sumar.
- «Quién la usa» sale de buscar la ruta en `src/`, `tools/`, `tests/` y `pyproject.toml`. Una
  herramienta invocada por ruta, una reexportación o una custodia no siempre dejan esa huella: la
  falta de consumidor no basta para borrar.

## Inventario

| Carpeta | En git | Tamaño | Qué es | Quién la usa |
| --- | --- | --- | --- | --- |
| `.agents/` | no, y tampoco ignorada | sin medir | Registro de coordinación entre sesiones (`coordination/ACTIVE.md`) | Las sesiones de agentes |
| `.claude/` | sí | 25 kB | Skills del proyecto | Agentes; `tests/test_trazabilidad_specs.py` |
| `.cursor/` | sí | 2 kB | Punteros a los skills de `.claude/` | Cursor |
| `.git/` | no | 0,64 GiB | Repositorio | Git |
| `.playwright-mcp/` | ignorada | 1 MB | Capturas del navegador; parte es evidencia | Sesiones de prueba de la web |
| `.pytest_cache/` | ignorada | 0,3 MB | Caché de pytest | pytest; se regenera |
| `.ruff_cache/` | ignorada | 3 kB | Caché de ruff | ruff; se regenera |
| `.superpowers/` | excluida en local | 56 kB | Notas de sesiones de agentes | Sin consumidor en el código |
| `.venv/` | ignorada | 5,31 GiB | Entorno de Python 3.12 | Todo el proyecto |
| `.vscode/` | ignorada | 0,3 kB | Configuración local del editor | VS Code |
| `.worktrees/` | ignorada | 5,39 GiB | Worktrees de las ramas activas | Sesiones concurrentes |
| `AUDIT/` | ignorada | 0,48 GiB | Evidencia de aceptación y de limpieza | Personas y agentes; custodia |
| `config/` | sí | 37 kB | Perfiles, contratos y parámetros | `src/`, pruebas |
| `docs/` | sí | 1 MB | Manuales, arquitectura, regresiones e informes | `src/convertersmartgrid/asistente/`, pruebas |
| `external/` | ignorada por dentro | 0,65 GiB | Revisiones fijadas de terceros y solucionadores | `upstream_ia.py`, `asistente/llm_runtime.py`, `tools/preparar_upstream_ia.py` |
| `frontend/` | sí | 63 MB con `node_modules` y `dist` | Interfaz web | `web/app.py` sirve `dist`; `run_gui.bat` la compila |
| `instalador/` | sí | 4 kB | Guion de Inno Setup de la versión de producto (086:RF-36) | `tools/construir_candidato.py` |
| `input/` | sí, solo `README.md` | 43 kB | Catálogo de parámetros local | `catalog.py`, `reglas.py`, `cli.py` |
| `output/` | ignorada | 98,2 GiB lógicos, 36,3 GiB reales | Espacios web, modelos, corpus, informes y evidencia | Web, gemelo, asistente, informes; no es carpeta de temporales |
| `specs/` | sí | 1,4 MB | Especificaciones | `tools/estado_specs.py`, pruebas |
| `src/` | sí | 7 MB | Motor, API web, asistente, ETL de VNR-GIS | Todo el proyecto |
| `tests/` | sí | 17 MB con cachés | Suite principal (`testpaths` de `pyproject.toml`) | pytest |
| `tests_ml/` | sí | 0,1 MB | Pruebas de modelos con GPU, fuera de la suite | Se lanzan a mano; `test_benchmark_pinn.py` y `asistente/lectura_proyecto.py` la nombran |
| `tmp/` | no, y tampoco ignorada | vacía | Temporales locales | Git no guarda una carpeta vacía |
| `tools/` | sí | 3 MB | Herramientas y guiones de DIgSILENT | `web/`, manual, `tests/test_inventario.py` |

La carpeta `referencia/` ya no está: sus datos se movieron sin borrar fuera del proyecto el 2026-11-02
(ruta en `CLAUDE.md`).

## Documentos corregidos

- `docs/MANUAL_COMANDOS.md`: 21 líneas apuntaban a la carpeta de datos retirada; ahora usan una ruta
  de ejemplo con su nota. Se añade `verify_interactive_architecture.mjs` a la tabla de herramientas,
  donde ya estaban `tools/arquitectura.py` y `verify_architecture_links.py`.
- `.claude/skills/convertersmartgrid-backend/SKILL.md` y `docs/constitution.md`: la misma ruta. El
  principio 9 no cambia de sentido.
- `CODIGO_FUENTE.md`: `web/runtime.py` cita la spec 036.

## Limpieza: por qué no se borra nada

La tarea T5 se retiró sin hacer. Sus «cachés seleccionadas» estaban en el manifiesto que no existe.
Además, lo regenerable vuelve con la siguiente prueba: la auditoría del 2026-11-02 contó 3 591 carpetas
de caché y 0,47 GiB, de los que 0,31 GiB son de `.venv/`, que no es de este proyecto limpiarlos.

Esa misma auditoría encontró `.bak` de bases reales y bloqueos de Office entre lo que un filtro por
nombre tomaría por temporal, y por eso nada se borra por nombre ni por antigüedad. La causa se ataca en
dos sitios: la spec 062 retira ejecuciones y temporales de la web, y 065 T6 (065:RF-10, abierta) saca
las cachés del checkout.

## Pendientes conservados

- `.agents/` y `tmp/` aparecen o pueden aparecer sin ignorar en `git status`. Decidir si `.agents/` se
  versiona o se ignora es del integrador.
- `tools/arquitectura.py` da 97 violaciones aceptadas y 0 errores: deuda declarada, no conformidad.
- `docs/AUDITORIA_ALUMNOS_2026-11-01.md` y `docs/CORRECCIONES_ALUMNOS_2026-11-01.md` enlazan evidencia
  de `output/`, que existe en el checkout principal y no en un worktree. No es un enlace roto.
- No se ha probado una instalación limpia ni un arranque nativo del lanzador con su servidor real:
  las pruebas de `run_gui.bat` lo ejecutan en una carpeta aislada con dobles del servidor y de npm.
