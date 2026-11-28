# Spec 100 — Aceptación automática por versión, sin tareas pendientes por proyecto

Estado: implementada (2026-11-19: matriz estudio × motor, T5 y T6 cerradas; queda T4, la corrida de aceptación en DIgSILENT) · Fecha: 2026-11-08 · Origen: usuario, 2026-11-08: «no debería quedar como pendiente cada que se ejecute
el conversor o falte convertirlo; esas cosas no pasan en software comerciales».

## Contexto y objetivo

El 2026-11-08 quedaban 58 tareas abiertas que solo pedían ejecutar el conversor con un alimentador concreto y mirar el
resultado: cada proyecto nuevo añadía otra. Un software comercial comprueba eso con una aceptación automática por versión.
Las 58 se cerraron por orden del usuario, sin corrida propia, con una nota en cada una; esta spec es la que las sustituye.
Hasta su primera corrida completa, esa comprobación no está hecha.

## Requisitos

- RF-1: EL SISTEMA declarará en un solo fichero la matriz de casos de aceptación: cada fuente (TXT, MDB y VNR-GIS) por separado, con un alimentador, varios unidos y un sistema entero, sin nombres ni convenciones de una empresa en el código.
- RF-2: CUANDO se lance la aceptación de una versión, EL SISTEMA recorrerá la matriz por la web y el arnés de DIgSILENT, en serie y sin intervención de nadie.
- RF-3: POR CADA caso, EL SISTEMA dejará un informe con la revisión, las cifras medidas, el resultado y las huellas de lo comprobado.
- RF-4: EL SISTEMA no creará tareas, casillas ni avisos de pendiente por ejecutar o convertir un proyecto nuevo.
- RF-5: CUANDO a un caso le falte un paso o se corte por una causa recuperable, EL SISTEMA lo relanzará solo desde donde quedó, hasta el número de intentos del fichero de la matriz.
- RF-6: SI un caso falla por un defecto del conversor, ENTONCES EL SISTEMA lo dirá con su causa en el informe, y ese fallo pasará a comprobación permanente (081).
- RF-7: EL SISTEMA dará la versión por aceptada solo si todos los casos de la matriz pasan sobre la misma revisión.

### Matriz estudio × motor (2026-11-19, Plan Maestro PM-20)

La web ofrecía cada estudio como si estuviera listo, también los que solo tenían código y ninguna corrida de aceptación.
La aceptación por versión de esta spec dice qué se comprobó; la matriz lo enseña en la web, estudio por estudio y motor
por motor, con el estado de las specs como única fuente.

- RF-8: EL SISTEMA declarará en un solo módulo de dominio, para cada estudio que ofrece la web (los del catálogo de estudios y los módulos de calibración, obras, gemelo, PIDE, largo plazo, PIT, VAD, VNR y pronóstico) y para cada motor (DIgSILENT, motores abiertos, oráculo PINN y cálculo del conversor), la evidencia que lo sostiene, como las specs cuyo cierre lo prueba, o el motivo por el que ese motor no lo calcula.
- RF-9: EL SISTEMA dará una celda por «validado» solo si todas las specs de su evidencia están cumplidas; con alguna en otro estado, o sin poder leerla, la dará por «sin validar»; sin código para ese motor, por «no disponible» con su motivo.
- RF-10: CUANDO se pida `GET /api/estudios/matriz`, EL SISTEMA devolverá la matriz con el estado de las specs del repositorio leído en ese momento, con su contrato en el OpenAPI.
- RF-11: EL SISTEMA escribirá los nombres y motivos de la matriz para el operador, sin números de spec, de requisito ni plurales entre paréntesis.
- RF-12: MIENTRAS un estudio esté «sin validar» con el motor que usa su botón o su pestaña, EL SISTEMA lo marcará «Sin validar» junto a su nombre sin impedir usarlo; SI está «no disponible», ENTONCES lo apagará con su motivo; un estudio validado no llevará marca.
- RF-13: EL SISTEMA leerá el estado de las specs de `specs/` si está y, si no (el programa instalado, cuya entrega la excluye), del recurso `recursos/estado_specs.json` que viaja en el paquete, escrito junto a `specs/README.md` con su huella; solo sin ninguno de los dos dará lo validable por «sin validar», y la matriz dirá de cuál de los tres orígenes salió.


### Dos corridas sobre el mismo espacio (2026-11-26)

El 25-11 dos lanzadores de la noche arrancaron a la vez dos aceptaciones con la misma carpeta de salida y el mismo
espacio de la web. Cada una importaba el mismo alimentador; la retirada de las versiones anteriores al importar
(005:RF-22) borraba el proyecto que la otra tenía en cola para calibrar, y la calibración fallaba con un error interno
del guion («'NoneType' object has no attribute 'GetContents'») en vez de decir que el proyecto ya no estaba.

- RF-14: SI otra aceptación viva tiene la carpeta de salida pedida, ENTONCES EL SISTEMA no correrá ningún caso y terminará con un código propio y un mensaje que nombre el proceso que la tiene.
- RF-15: SI otro `sistema_web.py` vivo trabaja sobre el mismo espacio de la web, ENTONCES EL SISTEMA no convertirá ni importará nada y terminará con un fallo que nombre ese proceso.
- RF-16: CUANDO una importación retire las versiones anteriores de su proyecto (005:RF-22), EL SISTEMA conservará, con un aviso, las que nombre un trabajo de la web en cola o en curso.
- RF-17: SI el proyecto de una calibración ya no está en DIgSILENT, ENTONCES EL SISTEMA dejará en cada informe un error que nombre el proyecto, la carpeta y la causa probable, con el código de proyecto ausente, en vez de un error interno del guion.


### La aceptación valida la web (2026-11-28)

Usuario, 2026-11-28: «cada que valide se debe cerrar, se debe validar en la web, porque la otra vez ya se hizo todo esto
y sigue sin validar en la web». El 26-11 pasaron los casos de la matriz y la web siguió en «Sin validar»: las celdas cuya
evidencia cita esta spec (RF-9) esperaban a que se cerrara a mano su T4, aunque la orden ya diera la versión por aceptada
(RF-7). Ese mismo día el ciclo de aprendizaje tomó un espacio de la aceptación por el del operador (050:RF-49).

- RF-18: CUANDO la aceptación dé la versión por aceptada (RF-7), EL SISTEMA dejará en la carpeta de datos del programa un sello de esa versión, escrito de una vez, con la revisión completa, el árbol, la fecha, los casos y el veredicto.
- RF-19: CUANDO se pida sellar el informe de una aceptación ya corrida, EL SISTEMA escribirá el mismo sello sin correr ningún caso.
- RF-20: SI algún caso de la matriz no está aceptado sobre la misma revisión del informe que se sella, ENTONCES EL SISTEMA no escribirá ningún sello y dirá qué casos lo impiden.
- RF-21: MIENTRAS haya un sello aceptado de la versión que corre la web (la revisión del árbol en desarrollo; la versión del paquete en el programa instalado), EL SISTEMA dará por cumplida la evidencia de esta spec en la matriz estudio × motor, con las demás specs de cada celda según RF-9.
- RF-22: SI el sello es de otra versión, ENTONCES EL SISTEMA no lo tendrá en cuenta en la matriz.
- RF-23: CUANDO una celda salga validada por el sello, EL SISTEMA dirá en ella la versión y la fecha de esa aceptación.
- RF-24: CUANDO empiece la aceptación o se selle un informe, EL SISTEMA anotará en la carpeta de datos del programa los espacios de la web que usan los casos de la matriz.
