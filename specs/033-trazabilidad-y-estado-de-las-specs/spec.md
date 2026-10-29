# Spec 033 — Trazabilidad y estado de las specs

Estado: cumplida (2026-10-29) · aprobada el mismo día, pedida por el usuario: «nada debe quedar suelto» · Fecha: 2026-10-29 · Origen: `docs/REVISION_SPECS_2026-10-29.md`

## Contexto y objetivo

La revisión del 2026-10-29 (`docs/REVISION_SPECS_2026-10-29.md`) cruzó las 30 specs con
sus tareas, sus pruebas, el índice del código y los commits, y encontró la suite en verde
con todo esto mal:

- RF definidos dos veces con textos distintos (nueve, en las secciones de cambios de las
  004, 006, 007, 011 y 014), saltos sin explicar (020: RF-33 a RF-59; 022: RF-35, RF-36 y
  RF-92; 017: RF-123) y 39 RF con letra que la 009 no veía.
- Tareas repetidas (014 T8c), fuera de orden (027 T14), 23 sin «Hecho cuando:» y 63 RF que
  ninguna tarea cubría.
- El estado escrito en tres sitios (la línea `Estado:` de la spec, la tabla de `CLAUDE.md`
  y las casillas) y los tres distintos: diez specs implementadas que decían «aprobada»,
  la 016 «cumplida» con una tarea abierta, la 013 en borrador con código y pruebas.
- 13 RF de specs implementadas sin prueba, porque 009:RF-11 se apagaba con una sola
  prueba de DIgSILENT abierta.
- Las specs 018, 030 y 032 sin un solo fichero en `CODIGO_FUENTE.md`; 60 ficheros de
  pruebas y 17 commits `feat` sin ninguna spec, sobre todo el motor anterior a las specs
  y el contrato universal de fuentes del 2026-10-13.

El usuario pide el mismo día corregirlo todo y que «nada quede suelto». Esta spec convierte
cada hallazgo en una comprobación de la suite, para que lo corregido no vuelva a
desfasarse, y crea la spec 034, que recoge el código que no tenía ninguna.

## Usuarios / actores

Quien escribe o cambia una spec, sus tareas o sus pruebas (el usuario o un agente), y la
suite, que lo comprueba.

## Historias de usuario

- H1: Como responsable del proyecto quiero que cada requisito tenga un número único, una
  tarea y una prueba, para saber qué está hecho sin abrir el código.
- H2: Como responsable quiero ver el estado de todas las specs en un sitio, y que ese sitio
  no pueda mentir.
- H3: Como responsable quiero que todo el código y todas las pruebas pertenezcan a una spec.

## Requisitos funcionales (EARS)

Numeración

- RF-1: EL SISTEMA aceptará en una spec una sola línea `- RF-n:` por cada requisito, con
  `n` un número y, opcionalmente, una letra (RF-36b); una aclaración o un cambio posterior
  de un RF se escribirá como `- Aclaración de RF-n …`.
- RF-2: SI falta un número entre RF-1 y el mayor RF de una spec, ENTONCES la spec lo
  declarará con una línea `- RF-a a RF-b: no se usan (motivo).` o `- RF-a: no se usa (motivo).`
- RF-3: EL SISTEMA aceptará cada número de spec entre 001 y el mayor solo si tiene su
  carpeta en `specs/`; un número que no se use tendrá una carpeta con la spec en estado
  «reservada» o «retirada» y su motivo.
- RF-4: EL SISTEMA aceptará cada tarea solo con la forma `Tn` o `Tn` más una letra, sin
  repetirse dentro de su `tasks.md`.

Tareas

- RF-5: EL SISTEMA exigirá a cada tarea su línea «Hecho cuando:».
- RF-6: EL SISTEMA exigirá que cada RF de una spec con `tasks.md` lo nombre al menos una
  tarea, por sí solo o dentro de un rango «RF-a a RF-b».
- RF-7: EL SISTEMA reconocerá una tarea que solo se puede hacer en DIgSILENT por la marca
  `[DIgSILENT]` tras su número.

Estado

- RF-8: EL SISTEMA aceptará como estado de una spec solo una de estas palabras, la primera
  de su línea `Estado:`: borrador, aprobada, implementada, cumplida, reservada o retirada.
- RF-9: SI una spec dice «cumplida», ENTONCES no tendrá ninguna tarea abierta.
- RF-10: SI una spec dice «implementada», ENTONCES sus únicas tareas abiertas serán
  `[DIgSILENT]` y tendrá al menos una.
- RF-11: SI una spec dice «aprobada» y tiene tareas, ENTONCES tendrá al menos una tarea
  abierta que no sea `[DIgSILENT]`.
- RF-12: SI una spec dice «borrador», «reservada» o «retirada», ENTONCES no tendrá ninguna
  tarea marcada.
- RF-13: SI una spec está aprobada, implementada o cumplida, ENTONCES tendrá `plan.md` y
  `tasks.md`.
- RF-14: EL SISTEMA generará `specs/README.md`, con una fila por spec (número, nombre,
  estado, RF, RF con prueba y tareas abiertas), con `tools/estado_specs.py`, y la suite
  fallará si el fichero no coincide con lo que generaría.
- RF-15: EL SISTEMA exigirá que la tabla de specs de `CLAUDE.md` dé a cada spec el mismo
  estado que su línea `Estado:`.

Pruebas

- RF-16: CUANDO todas las tareas que no son `[DIgSILENT]` de una spec estén marcadas,
  EL SISTEMA exigirá una prueba que cite cada uno de sus RF, también los de letra.
- RF-17: EL SISTEMA rechazará una cita `NNN:RF-n` a un RF que su spec no define, también
  los de letra.
- RF-18: EL SISTEMA exigirá que cada fichero de pruebas cite al menos un RF de alguna spec,
  en su docstring o en el de una de sus pruebas.

Código

- RF-19: SI una spec está implementada o cumplida, ENTONCES `CODIGO_FUENTE.md` le atribuirá
  al menos un fichero.
- RF-20: EL SISTEMA tendrá una spec, la 034, con los requisitos del código anterior a las
  specs y del que entró sin ninguna, para que ningún fichero de `src/` quede solo con
  «base».
- RF-21: EL SISTEMA exigirá que cada commit `feat` posterior al 2026-10-29 nombre su spec en
  el mensaje (`NNN:RF-n`, «spec NNN» o «NNN Tn»).

Reglas del flujo

- RF-22: El skill `igea-dgs-spec` dirá que una spec cumplida no crece (un cambio sobre ella
  abre una spec nueva que la cita), que un RF nuevo entra con su tarea, que las tareas de
  DIgSILENT llevan la marca `[DIgSILENT]` y que el estado se escribe solo con el
  vocabulario de RF-8.

## Requisitos no funcionales

- No se renumera ningún RF ni ninguna spec existente: 1 636 pruebas citan `NNN:RF-n` y
  la trazabilidad depende de esos números. Los huecos se declaran (RF-2).
- Las comprobaciones leen solo ficheros del repositorio y `git log`, sin datos de la
  distribuidora ni DIgSILENT, y tardan menos de 10 s.

## Casos límite

- Un RF de letra (RF-36b) sin el número base: vale, el base existe.
- Un rango «RF-a a RF-b» en una tarea cubre todos los de en medio; un rango citado como
  `NNN:RF-a a RF-b` en una prueba, también.
- Una spec sin `tasks.md` y en borrador: no se le exige nada de tareas.
- Una línea `- Aclaración de RF-n` no cuenta como definición.

## Fuera de alcance

- Hacer las pruebas pendientes en DIgSILENT: quedan como tareas `[DIgSILENT]` de cada spec.
- Implementar las funcionalidades aún no hechas de las specs 002, 012, 013 y 017: quedan
  como tareas abiertas de su spec, con su estado.
- Reescribir el historial de git: los 17 commits sin spec se atribuyen en la 034.

## Criterios de finalización

Cada RF citado por al menos una prueba (`grep -rnoE "033:RF-[0-9]+" tests | sort -u`);
`tests/test_trazabilidad_specs.py` y `tests/test_inventario.py` en verde sobre el
repositorio corregido; la suite completa en verde.
