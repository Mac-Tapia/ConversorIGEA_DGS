# Spec 009 — Inventario del repositorio: cada fichero con su módulo y su spec

Estado: cumplida (2026-10-14, verificación RF por RF); aprobada el 2026-10-10 · Fecha: 2026-10-10 · Origen: revisión pedida por el usuario el 2026-10-10

## Contexto y objetivo

El usuario pide el 2026-10-10 que todas las specs estén al día y completas, que cada
fichero del proyecto pertenezca a un módulo y a una spec, que no haya ficheros
duplicados ni sueltos, y que la documentación esté actualizada. La revisión de ese día
encontró:

- 16 herramientas de `tools/` que nada llama, sin pruebas ni documentación. De ellas,
  10 eran de campañas pasadas: la «production readiness» del 2026-09-21, tres auditorías
  de ternas del 2026-09-11 que solo arrancaban con `tests/` en el `PYTHONPATH`, y un
  guion que subía el árbol por la API REST de GitHub.
- `CODIGO_FUENTE.md`, el índice del código, nombraba 12 de los más de 100 módulos.
- Ningún documento de uso explicaba la calibración a la máxima, la verificación de la
  convergencia ni el perfil de empresa.
- La spec 004 tenía su validación sin marcar, con todos sus RF ya cubiertos.
- `config/line_type_aliases.json`, con alias de códigos de Electro Dunas, estaba en git.
- 17 funciones y clases de `src/` que nada usaba, y dos herramientas con un alimentador o
  rutas de Electro Dunas fijados.

Nada impedía que volviera a pasar: un fichero nuevo sin índice ni prueba no rompía nada.

## Usuarios / actores

- Desarrollador del proyecto, que necesita saber qué hace cada fichero y qué lo rige.
- Ingeniero de planificación, que lee el README y el manual de órdenes.

## Historias de usuario

- H1: Como desarrollador quiero un índice completo del código, con la spec de cada
  módulo, para saber dónde tocar y qué requisito respeto.
- H2: Como desarrollador quiero que la suite falle si aparece un fichero suelto, para
  que el repositorio no vuelva a acumularlos.

## Requisitos funcionales (EARS)

Índice

- RF-1: EL SISTEMA tendrá en `CODIGO_FUENTE.md` un índice que liste cada módulo Python
  versionado de `src/` y cada herramienta de `tools/`, con lo que hace y la spec que lo
  rige.
- RF-2: SI un módulo de `src/` o una herramienta de `tools/` versionados no figuran en el
  índice, ENTONCES la suite fallará nombrándolos.
- RF-3: SI el índice nombra un fichero que no existe, ENTONCES la suite fallará
  nombrándolo.

Herramientas

- RF-4: EL SISTEMA retirará las herramientas de campañas pasadas que nada usa:
  `_enrich_production_readiness_retry.py`, `_publish_to_github.py`, `_retry_pf_gaps.py`,
  `_retry_pf_timeouts.py`, `_run_production_pf_batch.py`, `_write_production_readiness.py`,
  `prod_readiness_sample.py`, `audit_ternas_backbone.py`, `audit_ternas_classify.py` y
  `audit_ternas_ug.py`.
- RF-5: SI una herramienta de `tools/` importa de `tests/`, ENTONCES la suite fallará.
- RF-6: EL SISTEMA dará a cada herramienta de `tools/` un docstring que diga, en español,
  para qué sirve y cómo se invoca.
- RF-7: CUANDO se ejecuta una herramienta de `tools/` con `--help`, EL SISTEMA terminará
  con el código 0 sin necesitar DIgSILENT ni datos de la distribuidora.
- RF-8: EL SISTEMA no fijará en una herramienta las rutas de los datos de la
  distribuidora: las recibirá por argumentos.

Specs

- RF-9: SI una spec dice «cumplida» y tiene tareas sin marcar, ENTONCES la suite fallará.
- RF-10: SI una prueba cita un `NNN:RF-n` que la spec `NNN` no define, ENTONCES la suite
  fallará.
- RF-11: SI una spec tiene marcadas todas sus tareas, salvo las que hace el usuario en
  DIgSILENT, y un RF suyo no lo cita ninguna prueba, ENTONCES la suite fallará
  nombrándolo.

Documentación

- RF-12: EL SISTEMA describirá en `docs/MANUAL_COMANDOS.md` cada orden del CLI
  `igea-dgs` y cada herramienta de `tools/`.
- RF-13: EL SISTEMA describirá en el README la pestaña «Cargas en DIgSILENT» con sus tres
  pasos y el perfil de empresa.

Configuración

- RF-14: EL SISTEMA no versionará en `config/` ficheros con datos de una distribuidora:
  se versionan los `*.example.*`, los perfiles genéricos y los perfiles de empresa de
  `config/perfiles/`, que solo llevan convenciones (spec 002, RF-35); el resto queda en local.

Código

- RF-15: SI una función o clase de nivel superior de `src/` no la usa nada (ni su
  módulo, ni otro módulo, ni `tools/`, ni las pruebas, ni el front), ENTONCES la suite
  fallará nombrándola. Las rutas de FastAPI cuentan como usadas.

## Casos límite

- Un `__init__.py` vacío: cuenta como el paquete, se lista por su carpeta.
- Un `.bat` de `tools/`: se lista, pero no se ejecuta con `--help`.
- Una spec sin `tasks.md` (la 002 hasta tener plan): no se le aplica RF-11.
- Documentos históricos (`docs/superpowers/`, `docs/DIAGNOSTICO_*`): se listan como
  históricos y no se actualizan.

## Fuera de alcance

- Mover los módulos a capas: es la spec 002.
- Los skills de terceros de `.claude/skills/`, que no son del proyecto.
- Reescribir los documentos históricos.

## Criterios de finalización

- `grep -rnoE "009:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-15.
- Suite completa en verde con las tres variables `IGEA_*`.
