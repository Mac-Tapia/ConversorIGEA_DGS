# Spec 084 — Seis reglas del operador pasan de notas a requisitos con prueba

Estado: cumplida (2026-11-08: tareas cerradas por orden del usuario, sin corrida propia; su aceptación pasa a la spec 100) · Fecha: 2026-11-03 · Origen: aprobación del usuario del 2026-11-02 («ok a todo»)

Cita: 016 (RF-81 a RF-87), 017 (RF-128 a RF-135), 042 (RF-9, RF-10), 054 (RF-7), 063 (RF-21, RF-22), 064 (RF-1), 073 (RF-17, RF-19, RF-39, RF-40), 081.

## Contexto y objetivo

Seis reglas dadas por el usuario estaban solo en notas de trabajo: nada en el conversor las comprobaba, y una nota no impide repetir
el fallo. Lo que ya se cumplía se cierra con su requisito y una prueba; lo que faltaba se implementa. Regla general (081): nada bloquea
salvo la red vacía, y lo que no se puede resolver se corrige o se dice, sin un «OK» falso. Las reglas 4 y 5 son la excepción, porque
protegen datos reales: una orden sobre otro proyecto o con datos inventados no se ejecuta.

## Usuarios / actores

Ingeniero de planificación de cualquier distribuidora, desde la web; el asistente, por las mismas rutas; quien prueba el conversor.

## Requisitos funcionales (EARS)

### Regla 1: SET nueva en área libre

Usuario, 2026-11-02, al revisar una SET nueva: «debe quedar en un área libre, ni dentro de la calle ni encima de los alimentadores». El
punto de Weber (042:RF-9) y el ajuste por tensiones (042:RF-10) solo miran la electricidad.

- RF-1: CUANDO se sitúe una SET nueva, EL SISTEMA medirá su distancia al trazado de alimentador más cercano y nombrará el tramo, y SI no hay trazado con GPS, ENTONCES lo dirá.
- RF-2: SI el punto queda a menos del retiro del perfil de la red o de las calles conocidas, ENTONCES EL SISTEMA lo llevará al punto más cercano que lo respete y lo dirá.
- RF-3: SI ningún punto al alcance respeta el retiro, ENTONCES EL SISTEMA conservará el punto y dirá que hay que elegirlo en el plano.
- RF-4: DONDE el perfil dé un fichero GeoJSON local de calles, EL SISTEMA medirá también la distancia a ellas.
- RF-5: SI no hay datos locales de calles o no se pueden leer, ENTONCES EL SISTEMA dejará el punto «sin verificar en plano», sin inventar calles ni consultar servicios externos.
- RF-6: SI el perfil no da el retiro, ENTONCES EL SISTEMA dará la distancia, no moverá el punto y dirá qué dato falta.
- RF-7: EL SISTEMA no afirmará que el área está libre: el predio, los accesos y las viviendas quedan por revisar en el plano.
- RF-8: CUANDO la SET quede en su punto final, EL SISTEMA medirá en él el flujo equilibrado y el desequilibrado, y dirá el que no converge y el modo que corrió.
- RF-9: EL SISTEMA apartará de la red cada punto que pruebe el ajuste por tensiones antes de medirlo, sin contar las salidas de la propia SET.
- RF-10: SI los flujos guardados no son del punto final de la SET, ENTONCES EL SISTEMA dirá «flujos sin repetir» y no la dará por cumplida.
- RF-11: EL SISTEMA creará la obra aunque el sitio o los flujos queden con avisos: dice el estado, no se para.

### Regla 2: dos o más ternas subterráneas

Usuario, 2026-11-02, al corregir la suposición de dos ternas juntas en una zanja: una terna por ducto, o configuración de enterrado
triangular o rectangular, con la capacidad del fabricante para esa configuración.

- RF-12: CUANDO una obra deje dos o más ternas en un tramo de cable, EL SISTEMA dirá su configuración: la de la obra o, sin ella, la del perfil.
- RF-13: SI no hay configuración válida, ENTONCES EL SISTEMA dirá que falta y nombrará las tres posibles, sin suponer ninguna.
- RF-14: DONDE el perfil dé la capacidad del fabricante para ese tipo y configuración, EL SISTEMA la llevará a la línea con su factor de reducción, sin cambiar el tipo.
- RF-15: SI no hay ese dato, ENTONCES EL SISTEMA dejará la capacidad del tipo, dirá que queda sin confirmar y no usará ningún factor propio.
- RF-16: EL SISTEMA usará en el oráculo la capacidad de esa configuración en vez de doblar la del tipo.
- RF-17: EL SISTEMA describirá la instalación en el informe sin citar artículos ni distancias de la norma.
- RF-18: EL SISTEMA no cambiará nada en una línea aérea ni en un tramo de una terna.

### Regla 3: bancos limitados por el valle

La spec 073 ya lo cubre: RF-17, RF-18, RF-19, RF-20, RF-39 y RF-40. Aquí solo la decisión del 2026-11-02 y su comprobación conjunta.

- RF-19: EL SISTEMA tratará el número de módulos que admite el valle como un tope y elegirá la variante de menor costo que cumple, aunque queden módulos por usar.
- RF-20: EL SISTEMA no dará por factible ninguna variante, de ningún escalón, que no cumpla en valle, y dirá «no comprobado en valle» si no hay medición.

### Regla 4: no probar DIgSILENT con datos inventados

Usuario, 2026-10-01, al cortar una prueba con una SED inventada: «no hagas la prueba con datos no reales».

- RF-21: SI una prueba automática pide conectar con la API real de DIgSILENT, ENTONCES EL SISTEMA no conectará, con un error que dice por qué.
- RF-22: EL SISTEMA aplicará la misma guarda en la aceptación nativa, el otro sitio que conecta (064:RF-1).
- RF-23: SI el proyecto o el alimentador de una orden del asistente no están en lo que conoce la web, ENTONCES EL SISTEMA no ejecutará el plan.

Límite: el código no puede saber si una cifra de un libro del operador es inventada, ni qué hace a mano una sonda fuera de las pruebas.
Eso sigue siendo **regla de proceso**, en `CLAUDE.md` («Probar en DIgSILENT»), y aquí no se finge una comprobación.

### Regla 5: una orden de borrar vale solo en su proyecto

Caso real del 2026-11-01: una orden de limpiar un proyecto se aplicó también a otro, y se borró una SET nueva que era su obra planificada; borrar
en DIgSILENT no se deshace por la API.

- RF-24: SI se pide borrar un objeto que no es del proyecto de la orden, ENTONCES EL SISTEMA no lo borrará y lo dirá con los dos proyectos.
- RF-25: SI una orden al asistente pide borrar y su tarea escribe, ENTONCES EL SISTEMA no ejecutará el plan y dirá que el asistente no borra en DIgSILENT.
- RF-26: EL SISTEMA aplicará la guarda de RF-24 a lo que el operador ordena deshacer en un proyecto: las variaciones, los símbolos y los tipos de sus cargas.
- RF-27: EL SISTEMA tendrá justificado cada `Delete` de su código, en una lista que una prueba compara con el código.

Límite: una sonda escrita a mano puede llamar a `Delete` sin pasar por aquí. `pf_arnes.borrar_en_su_proyecto` está para eso, pero usarla
es **regla de proceso**.

### Regla 6: orden de las alternativas del informe

La spec 017 ya lo implementa (RF-128, RF-129, RF-132, RF-133); aquí, la comprobación conjunta y el caso sin datos.

- RF-28: EL SISTEMA numerará primero la alternativa de bancos y después la de cambio de sección, cada una sumada a la anterior, en cualquier orden de aplicación.
- RF-29: EL SISTEMA dará en la alternativa de sección su trecho desde–hasta y su plano, y anotará como hueco del informe el plano que falte.
- RF-30: SI no hay geografía para el trecho, ENTONCES EL SISTEMA dirá que el trecho está sin datos.

## Casos límite

- Una red muy densa puede no dejar sitio: RF-3. Una salida de la SET no cuenta como red de la que apartarse: RF-9.
- Una red con líneas de menos de tres fases solo admite el flujo desequilibrado (054:RF-7): RF-8 dice el modo que corrió.
- Mover la SET a mano en DIgSILENT no se detecta hasta repetir su obra o sus flujos: RF-10 solo compara lo que guardó la ejecución.

## Fuera de alcance

Comprobar viviendas, predios y accesos. Consultar mapas o datos abiertos. Escribir distancias o factores de agrupamiento de una norma. Un
campo en la web para la configuración (hoy va en el perfil o en la obra). Los cambios de `nlnum` en la operación de una SET existente.

## Criterios de finalización

Cada RF con su prueba, y la comprobación en DIgSILENT de `fline` y de los dos flujos sobre un proyecto de prueba ya importado.
