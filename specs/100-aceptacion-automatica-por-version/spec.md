# Spec 100 — Aceptación automática por versión, sin tareas pendientes por proyecto

Estado: aprobada · Fecha: 2026-11-08 · Origen: usuario, 2026-11-08: «no debería quedar como pendiente cada que se ejecute
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
