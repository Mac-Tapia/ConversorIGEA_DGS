# Spec 090 — La arquitectura se cataloga sola: todos los módulos, el asistente y su equipo

Estado: cumplida (2026-11-25: RF-20 a RF-26 y T8, motores abiertos, VNR de la Guía, carriles y pseudocódigo en el C4; 2026-11-17: RF-19 y T7, el C4 profesional al día con el catálogo; antes RF-18 y T6, cada fichero con su subsistema, y 2026-11-16: RF-17 y T5) · Fecha: 2026-11-04 · Origen: petición del usuario

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
- RF-17: `docs/ARQUITECTURA.md` explicará cada paquete de `src/convertersmartgrid/`; SI aparece un paquete que no explica, ENTONCES la suite lo dirá por su nombre. Sus líneas citadas por la 076 y la 077 no se mueven al ampliarlo (RF-16).
- RF-18: Cada fichero del catálogo tendrá su subsistema en `docs/architecture/subsistemas.json`, y el mapa no nombrará ficheros que ya no existen; SI queda alguno «sin subsistema asignado», ENTONCES la suite lo dirá. La fila que añade un módulo lo asigna.
- RF-19: El C4 de `docs/architecture/` (`workspace.dsl` y su página interactiva) tendrá un componente por cada grupo de `docs/architecture/subsistemas.json`, nombrado en su propiedad «Subsistemas», y sus cifras (ficheros de cada componente, rutas de la API, carriles, tareas del asistente, módulos y subsistemas) serán las del catálogo generado y las pondrá `tools/generar_c4.py --escribir`, que la puerta corre tras el catálogo; SI un grupo queda sin componente, una cifra no coincide, un elemento sigue «en implementación» con su spec cumplida o un enlace no apunta a una sola revisión con rutas que existen, ENTONCES la suite lo dirá con la orden que lo arregla. Las cifras no se escriben a mano ni se fijan en la prueba.
- RF-20: El C4 tendrá un contenedor «Motores abiertos de flujo» que nombre cada motor de `MOTORES` en `adaptadores/digital_twin/motores_flujo.py` y pandapower, con una relación hacia cada contenedor que calcula con ellos (la calibración, el preflight, el PIT, el VAD, el plano y el gemelo); SI un motor de `MOTORES` falta en el DSL o en la página, ENTONCES `tools/generar_c4.py --comprobar` lo nombrará.
- RF-21: El C4 tendrá el VNR de la Guía 232-2017 en un contenedor propio, distinto del adaptador de entrada VNR-GIS y del VAD, cada uno con su grupo de `docs/architecture/subsistemas.json` y su vista de componentes.
- RF-22: El contenedor de colas del C4 tendrá una propiedad «Carril <nombre>» por cada carril de `LANES` en `presentacion/web/jobs.py`, con lo que corre en él, y la página una vista «Carriles» con un nodo por carril; SI un carril del código falta en el DSL o en la página, o sobra uno que el código ya no tiene, ENTONCES `tools/generar_c4.py --comprobar` lo nombrará.
- RF-23: `docs/architecture/pseudocodigo.md` dará el pseudocódigo de cada flujo principal: conversión, DIgSILENT, calibración, «Con proyecto», motores abiertos, PIT, VAD, VNR de la Guía, carriles y asistente; cada paso que nombre código lo hará como `ruta.py::función`, y SI una función citada ya no existe en su fichero, ENTONCES la suite la nombrará.
- RF-24: La página interactiva mostrará el mismo pseudocódigo, puesto por `tools/generar_c4.py --escribir`, con el bloque del flujo de la vista elegida abierto; SI la página difiere del fichero, ENTONCES `--comprobar` saldrá con 1 y dirá la orden que lo arregla.
- RF-25: `docs/ARQUITECTURA.md` dirá los carriles que tiene el código y explicará los motores abiertos, el PIT, el VAD y el VNR de la Guía con un enlace a su pseudocódigo, sin mover sus líneas citadas por la 076 y la 077 (RF-16).
- RF-26: Las PNG y el PDF del C4 saldrán de la página con una orden versionada, una página del PDF por vista y otra por bloque de pseudocódigo; SI falta la vista de una pestaña de la página, ENTONCES la orden fallará y la nombrará.

## Fuera de alcance

- Generar el C4 (`docs/architecture/workspace.dsl` y su página): sus contenedores no cambian con cada módulo.
- Los punteros de los modelos en uso: viven en `output/`, fuera de git, y darían un catálogo distinto en cada máquina. Siguen en `docs/ARQUITECTURA.md` con su fecha.
- Las skills y agentes de desarrollo: «el equipo» es el del asistente (`asistente/equipo.py`).
- Modificar los conjuntos sellados de la 076 y la 077, ni volver a medirlos.
