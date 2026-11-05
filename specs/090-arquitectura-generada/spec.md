# Spec 090 — La arquitectura se cataloga sola: todos los módulos, el asistente y su equipo

Estado: cumplida · Fecha: 2026-11-04 · Origen: petición del usuario

## Contexto y objetivo

El usuario, el 2026-11-04: la arquitectura debe catalogar todo, «con el asistente y todo el equipo», y «se debía actualizar
automáticamente». `docs/ARQUITECTURA.md` se escribía a mano y a los dos días decía 97 excepciones de capas cuando había 37, tres
carriles cuando había cuatro y «sin implementar» de lo que ya estaba conectado.

Lo que cambia en cada commit se genera desde el repositorio; lo que explica el porqué sigue escrito a mano.

## Requisitos

- RF-1: EL SISTEMA generará un catálogo que nombre cada fichero versionado de `src/convertersmartgrid/`, `src/vnr_etl/`, `tools/`, `frontend/src/`, `frontend/scripts/` y `frontend/test/`.
- RF-2: EL SISTEMA tomará el papel y las specs de cada fichero de `CODIGO_FUENTE.md`, y su capa de `pyproject.toml`, sin una segunda copia.
- RF-3: SI un fichero no tiene subsistema asignado, ENTONCES EL SISTEMA lo listará en un apartado «Sin subsistema asignado», sin fallar.
- RF-4: CUANDO un fichero deje de estar versionado, EL SISTEMA lo quitará del catálogo aunque siga en el mapa de subsistemas.
- RF-5: EL SISTEMA catalogará cada tarea del asistente con su modo, si escribe, su carril, si queda en la edición de producto, su función y sus datos.
- RF-6: EL SISTEMA catalogará cada rol del equipo del asistente con si puede ejecutar, si puede leer el proyecto y su encargo.
- RF-7: EL SISTEMA catalogará las etapas del proyecto entero, las de una carga nueva, las familias de modelos y los umbrales del intérprete.
- RF-8: EL SISTEMA dará las cifras de paquetes, capas, excepciones de capas, carriles, rutas de la API y specs por estado.
- RF-9: EL SISTEMA producirá el mismo catálogo para el mismo contenido, sin fechas ni revisiones.
- RF-10: SI el catálogo no coincide con lo que se generaría, ENTONCES la comprobación terminará con error y dirá la orden que lo arregla.
- RF-11: CUANDO se haga un commit, EL SISTEMA regenerará el catálogo y lo incluirá en ese commit.
- RF-12: CUANDO un commit lleve rutas explícitas, EL SISTEMA generará el catálogo con lo que entra en ese commit, sin los cambios sin confirmar de otra sesión, y sin dejar el catálogo a medio preparar.
- RF-13: CUANDO se fusionen dos ramas que cambian el catálogo, EL SISTEMA completará la fusión sin conflicto en él y lo regenerará.
- RF-14: SI el generador falla durante un commit, ENTONCES EL SISTEMA avisará y dejará pasar el commit, y será la suite quien lo detenga.
- RF-15: `docs/ARQUITECTURA.md` enlazará el catálogo y dejará en él las cifras que cambian con el código.
- RF-16: EL SISTEMA conservará en `docs/ARQUITECTURA.md` las frases que citan las preguntas de la 076 y los conjuntos de la 077, en una tabla de correcciones cuando ya no sean ciertas.

## Fuera de alcance

- Generar el C4 (`docs/architecture/workspace.dsl` y su página): sus contenedores no cambian con cada módulo.
- Los punteros de los modelos en uso: viven en `output/`, fuera de git, y darían un catálogo distinto en cada máquina. Siguen en `docs/ARQUITECTURA.md` con su fecha.
- Las skills y agentes de desarrollo: «el equipo» es el del asistente (`asistente/equipo.py`).
- Modificar los conjuntos sellados de la 076 y la 077, ni volver a medirlos.
