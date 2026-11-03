# Spec 078 — Las señales de convergencia dicen lo que devolvió DIgSILENT, y el asistente importa un grupo ya convertido

Estado: implementada · Fecha: 2026-11-02 · Origen: hallazgos de otra sesión tras importar un sistema real, comprobados en el código

Cita: 015 (RF-8, RF-10, RF-13, RF-14, RF-38 a RF-40), 032 (RF-26), 057 (RF-5, RF-6), 026 (RF-6), 069 (RF-13), 070 (RF-72).

## Contexto y objetivo

Tres señales hablaban del mismo flujo y ninguna decía la verdad. Se comprobó leyendo la vía de la web
(`--import-dgs --run-load-flow` con geografía, sin `--fix-until-converge`):

1. La línea del trabajo decía «OK … convergencia / aceptación» con el código de salida 0 del guion, y ese código
   solo mira `errors`. Un flujo que no converge va a `warnings` (015:RF-40), así que un proyecto que no calculó salía «OK».
2. El «Caso base» decía `VERIFICADO` con `convergence_pass: False`: el estado no miraba el flujo (015:RF-10) y la
   comprobación ✗ quedaba escondida en una columna.
3. `classify_convergence` leía solo `load_flow_loop`, que en esa vía es `null`. Con `return_code` 0 daba `NOT_CONVERGED`;
   y un flujo que no se ejecutó, también. Confundía un dato ausente con «no convergió».

Hay además una cuarta, hallada al seguir a los consumidores: al volver a verificar un proyecto ya importado no se corre
el flujo (015:RF-39), y el resultado sustituía al de la importación. Un proyecto que no convergió volvía a salir
`VERIFICADO`, y el episodio del gemelo se grababa con `converged: True`, sin que nada lo hubiera medido.

La causa común es que cada consumidor interpretaba el flujo a su manera. Esta spec deja una sola lectura y hace que todos
la usen. No cambia lo que se bloquea: el flujo sigue sin impedir importar ni calibrar (015:RF-38 a RF-40). Solo se dice
la verdad. Lo que el operador lee ya no puede parecer aceptado si DIgSILENT no calculó, y por eso «no converge» deja de ser
un detalle y pasa a decir qué falló, para aislarlo y corregirlo.

Y una orden al asistente: «importa SISTEMA_ZONA en digsilent» pedía `alimentadores`, porque el plan solo contrastaba con los
alimentadores de la fuente. La web ya importa un grupo por su nombre.

## Requisitos funcionales (EARS)

Una sola lectura del flujo

- RF-1: EL SISTEMA leerá el resultado de un flujo en un solo sitio, con el `return_code` y la validez que devuelve DIgSILENT
  en el último flujo ejecutado, y dará uno de tres estados: `converge`, `no_converge` o `sin_dato`.
- RF-2: SI el `return_code` es distinto de 0 o el resultado no es válido, ENTONCES EL SISTEMA dirá `no_converge`.
- RF-3: CUANDO el resultado es válido y el `return_code` es 0 o no consta, EL SISTEMA dirá `converge`.
- RF-4: SI no consta ni el fallo ni un resultado válido, ENTONCES EL SISTEMA dirá `sin_dato`, sin tomarlo por `converge` ni por
  `no_converge`.
- RF-5: CUANDO el flujo converge después de reducir la demanda (015:RF-38), EL SISTEMA dirá `converge` con el factor aplicado.
- RF-6: CUANDO el estado no es `converge`, EL SISTEMA dirá qué falló: el código, su significado, los errores y el diagnóstico
  que haya.
- RF-7: DONDE exista un historial de intentos, EL SISTEMA lo incluirá en la lectura.
- RF-8: EL SISTEMA escribirá `convergence_pass` como `true`, `false` o `null` según esa lectura.

Clasificación

- RF-9: SI la lectura es `sin_dato`, ENTONCES `classify_convergence` devolverá `SIN_DATO`.
- RF-10: SI la lectura es `no_converge`, ENTONCES `classify_convergence` devolverá `NOT_CONVERGED`.
- RF-11: CUANDO un flujo bueno no trae `load_flow_loop`, `classify_convergence` lo clasificará igual que uno que lo trae.
- RF-12: CUANDO se redujo la demanda para converger, `classify_convergence` devolverá `NEEDS_OPERATOR_REVIEW`.

«Caso base»

- RF-13: EL SISTEMA dará el «Caso base» por `VERIFICADO` solo si pasan las comprobaciones físicas de 015:RF-10 y la lectura
  del flujo es `converge`.
- RF-14: SI pasan las físicas y la lectura es `no_converge`, ENTONCES EL SISTEMA dará `NO_CONVERGE`, con lo que falló.
- RF-15: SI pasan las físicas y la lectura es `sin_dato`, ENTONCES EL SISTEMA dará `SIN_DATO_DE_FLUJO` y lo avisará.
- RF-16: CUANDO se vuelve a verificar sin flujo (015:RF-39), EL SISTEMA conservará el último resultado del flujo registrado
  en el vínculo de la misma fuente, y dirá que es el registrado.
- RF-17: MIENTRAS el «Caso base» esté en `NO_CONVERGE` o `SIN_DATO_DE_FLUJO`, EL SISTEMA permitirá calibrar, como ordenan
  015:RF-10 y RF-38 a RF-40.
- RF-18: EL SISTEMA guardará el episodio del gemelo de una verificación solo con el «Caso base» en `VERIFICADO`.

Importar desde la web

- RF-19: EL SISTEMA dirá «OK» de una importación solo si el guion termina con 0 y la lectura es `converge`.
- RF-20: SI el guion termina con 0 y la lectura es `no_converge`, ENTONCES EL SISTEMA dirá que quedó importado sin aceptar y qué falló.
- RF-21: SI el guion termina con 0 y la lectura es `sin_dato`, ENTONCES EL SISTEMA dirá que quedó importado sin aceptar y sin dato de flujo.
- RF-22: EL SISTEMA contará esos proyectos aparte, ni como aceptados ni como fallidos.
- RF-23: CUANDO un proyecto queda importado sin aceptar, EL SISTEMA guardará su proyecto y su vínculo igual, sin bloquear (015:RF-14).
- RF-24: DONDE la lectura traiga historial, EL SISTEMA lo escribirá en el Registro del trabajo.

Interfaz e informe

- RF-25: EL SISTEMA mostrará en la tabla del «Caso base» el estado de RF-13 a RF-15, con su motivo.
- RF-26: SI un vínculo anterior a esta spec guarda `VERIFICADO` con la comprobación de flujo en falso, ENTONCES la interfaz
  lo mostrará como «No converge».
- RF-27: EL SISTEMA mostrará en el resultado de la importación cuántos quedaron sin aceptar.
- RF-28: EL SISTEMA escribirá la lectura del flujo y su historial en el informe de texto de la aceptación.

El asistente al importar

- RF-29: CUANDO una orden de importar nombra un grupo o sistema ya convertido en el espacio, EL SISTEMA lo tomará como destino
  y no pedirá alimentadores.
- RF-30: EL SISTEMA reconocerá el grupo sin distinguir mayúsculas ni separadores, también dicho «sistema eléctrico X».
- RF-31: CUANDO la orden nombra un grupo convertido, EL SISTEMA no dirá que no es un alimentador ni pedirá la fuente cargada.
- RF-32: SI la orden nombra un sistema o una SET sin DGS convertido, ENTONCES EL SISTEMA dirá que hay que convertirlo antes, sin pedir alimentadores.
- RF-33: CUANDO el valor marcado por el modelo contiene un nombre que existe, EL SISTEMA tomará ese nombre sin añadir una duda.
- RF-34: SI el valor marcado no es ni contiene un nombre que exista, ENTONCES EL SISTEMA conservará la duda.
- RF-35: EL SISTEMA reconocerá los grupos en el contraste del plan, sin cambiar el catálogo de tareas hasta la 069 ni el
  vocabulario con que se entrena.

## Fuera de alcance

- Cambiar lo que bloquea: importar y calibrar siguen igual (015:RF-38 a RF-40, 057:RF-5, 057:RF-6).
- Actualizar el estado guardado con «Verificar la convergencia» (008:RF-18): corre con lo activo, que puede no ser el «Caso base».
- Las señales `converge` de los informes (`informes.py`): se leen de la medida de cada caso guardado, no de estas señales.
- El intérprete: la tarea que elige para cada orden no cambia. Una tarea nueva tampoco hace falta.

## Relación con otras specs

- 015 está cumplida y no crece: esta spec cambia el nombre del estado de 015:RF-10 cuando el flujo no converge, y mantiene
  que no bloquea. Quién calibra no cambia.
- 057 sigue igual: el oráculo corrige antes de importar. Esta spec trata lo que pase después en DIgSILENT.

## Criterios de finalización

- `grep -rnoE "078:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-35.
- Un proyecto importado con un flujo que no calcula sale de la web sin «OK» ni «Verificado», con el `return_code` y lo que dice DIgSILENT.
