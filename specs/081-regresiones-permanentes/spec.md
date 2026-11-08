# Spec 081 — Los fallos reales no se repiten: comprobaciones permanentes, solución con los oráculos y mejora continua

Estado: cumplida (2026-11-08: tareas cerradas por orden del usuario, sin corrida propia; su aceptación pasa a la spec 100) · Fecha: 2026-11-03 · Origen: fallos reales de la importación de un sistema, y orden del usuario

Cita: 015 (RF-38 a RF-40), 054 (RF-3, RF-9, RF-10), 057, 078 (RF-1 a RF-17), 026 (RF-25), 001 (RF-29, RF-31).

## Contexto y objetivo

Usuario, 2026-11-03: «debe hacerse cada vez más robusta e implementar mejoras, estos errores ya no deberían ocurrir, se supone
que estamos haciendo la mejora continua»; «debe hacer que converja, recuerda en caso llega convergido»; y, sobre una primera
versión de esta spec que bloqueaba la calibración: «nada debe bloquear, eso ya está definido, debes dar solución, el conversor,
para eso están los oráculos».

Siete fallos del mismo día, cada uno arreglado o pendiente caso a caso:

a. Acopladores de tres fases en barras monofásicas impedían todo el flujo.
b. Un banco trifásico en una barra de dos fases dio «Error in load flow data» en toda la calibración.
c. Una SED de una fase que no llega a su ramal: su barra de baja a 0 p.u. y su carga sin consumir, con el flujo «convergido».
d. «Calibración: done» con alimentadores `NO_CONVERGE`.
e. Tras esa calibración, el «Caso base» dejó de converger (causa sin confirmar).
f. La suite nocturna quedó «empezada» sin resultado al morir la web, y la web cayó sin causa conocida.
g. La web decía «OK» y «VERIFICADO» sin converger (corregido en 078).

Comprobado en el código: el DGS deduce las fases de cada barra de sus tramos y SED, sin mirar los bancos (`dgs.py`), así que (b)
también puede venir de la fuente; un trabajo termina `done` con solo no lanzar excepción (`jobs.py`), que es (d); y la suite corría
como hija de un hilo de la web, que es (f).

Dos ideas. Veracidad y solución van juntas: nunca un «OK» falso, y nunca sin solución si el oráculo o la física la tienen. Y cada
fallo real deja una comprobación permanente y una entrada en `docs/regresiones/`, con la prueba que lo cita. Nada se rechaza ni se
para: lo único que puede parar es la red vacía.

## Requisitos funcionales (EARS)

Comprobación previa de fases

- RF-1: ANTES de importar, EL SISTEMA comparará las fases de cada elemento (acoplador, banco, carga, transformador, tramo y regulador) con las de cada barra a la que se conecta.
- RF-2: EL SISTEMA dirá las fases de un elemento que no le llegan desde la cabecera.
- RF-3: EL SISTEMA dirá cada elemento que no cuadra con su clase, su barra y sus fases, con el conteo por clase.
- RF-4: SI un elemento no cuadra, ENTONCES EL SISTEMA seguirá con la importación.
- RF-5: SI un banco de la fuente tiene fases que su barra no lleva, ENTONCES EL SISTEMA le dará las de su barra, conservando su potencia, y lo anotará con `FASE_RECONSTRUIDA`.
- RF-6: EL SISTEMA hará la comprobación sobre el modelo común, igual para TXT, MDB y VNR-GIS.
- RF-7: CUANDO todo cuadra, EL SISTEMA dejará el modelo y el informe de reglas como estaban, y el DGS idéntico byte a byte.
- RF-8: ANTES de crear un elemento nuevo de una obra, SI su barra no lleva sus fases, ENTONCES EL SISTEMA lo llevará a la barra compatible más cercana.
- RF-9: SI no hay barra compatible para un elemento nuevo, ENTONCES EL SISTEMA lo dejará en su barra con las fases de esa barra y lo anotará.
- RF-10: EL SISTEMA leerá la misma comprobación de un proyecto de DIgSILENT, sin escribir en él.

Comprobación posterior al flujo

- RF-11: CUANDO el flujo converge, EL SISTEMA contará cada barra de baja tensión con carga a 0 p.u.
- RF-12: CUANDO el flujo converge, EL SISTEMA contará cada carga en servicio con demanda que no consume.
- RF-13: EL SISTEMA hará esa lectura sin escribir en DIgSILENT.
- RF-14: SI hay alguna de RF-11 o RF-12, ENTONCES la lectura única del flujo seguirá en `converge` y dirá que no está limpio, con el conteo.
- RF-15: SI el flujo no está limpio y lo físico pasa, ENTONCES EL SISTEMA dará el «Caso base» por `CONVERGE_SIN_SERVIR`, que calibra y no es `VERIFICADO`.
- RF-16: SI el flujo no está limpio, ENTONCES la importación dirá `IMPORTADO_CON_CARGAS_SIN_SERVIR` en vez de «OK».

Veracidad del trabajo

- RF-17: SI alguno de los alimentadores de una calibración no converge o no cumple y otro sí, ENTONCES EL SISTEMA terminará el trabajo en `parcial`.
- RF-18: SI ninguno de los alimentadores de una calibración queda bien y alguno no converge, ENTONCES EL SISTEMA terminará el trabajo en `no_converge`.
- RF-19: EL SISTEMA dará en el resultado la lista de esos alimentadores, con su estado y su motivo.
- RF-20: EL SISTEMA conservará en `parcial` y `no_converge` todo lo que guarda un trabajo terminado, sin detener nada de lo que sigue.
- RF-21: SI la recalibración de un sistema termina con fallos, ENTONCES EL SISTEMA terminará el trabajo en `parcial`, con la lista.
- RF-22: SI una importación deja proyectos sin aceptar o sin importar, ENTONCES EL SISTEMA terminará el trabajo en `parcial`, o en `no_converge` si ninguno quedó aceptado.
- RF-23: EL SISTEMA tratará `parcial` y `no_converge` como terminados con resultado en la API, la vigilancia, el asistente y la interfaz.
- RF-24: LA interfaz mostrará en el título del trabajo y en la calibración la lista de RF-19.

Solución: el «Caso base» llega convergido

- RF-25: SI el flujo del «Caso base» no converge o no tiene dato, ENTONCES EL SISTEMA buscará la causa con los mensajes de DIgSILENT, las fases de sus elementos y lo que halló el oráculo.
- RF-26: SI la causa es reconstruible, ENTONCES EL SISTEMA la corregirá en el «Caso base», antes de reducir la demanda.
- RF-27: EL SISTEMA anotará de cada corrección el elemento, el valor anterior, el nuevo, la regla y la evidencia.
- RF-28: EL SISTEMA volverá a medir tras cada corrección, hasta converger o hasta no tener corrección nueva.
- RF-29: SI aun así no converge, ENTONCES EL SISTEMA dirá por alimentador cada causa que queda, con su elemento y qué hacer.
- RF-30: EL SISTEMA no impedirá calibrar por el estado del flujo del «Caso base» (078:RF-17): calibra lo que se pueda y lo dice por alimentador.
- RF-31: MIENTRAS exista «Sin proyecto», EL SISTEMA no corregirá el «Caso base» (015:RF-39).
- RF-32: CUANDO el flujo converge tras reconstruir, la lectura dirá `converge` con sus correcciones, y la clasificación `CONVERGED_RECONSTRUCTED`.

«Caso base» inmutable

- RF-33: EL SISTEMA comparará la huella del «Caso base» (su flujo y sus cargas) de antes y de después de calibrar.
- RF-34: SI la huella cambió, ENTONCES EL SISTEMA lo dirá como fallo grave, con lo que cambió.
- RF-35: SI la huella cambió, ENTONCES EL SISTEMA ofrecerá el plan para volver a ella.
- RF-36: SI la huella cambió, ENTONCES EL SISTEMA terminará el trabajo en `parcial` sin parar lo demás.

Suite nocturna y cierre de la web

- RF-37: EL SISTEMA correrá la suite nocturna en un proceso separado que sobrevive al cierre de la web, también al de su árbol de procesos.
- RF-38: EL SISTEMA correrá la suite por tandas de ficheros, cada tanda en su proceso y una tras otra, con `OPENBLAS_NUM_THREADS=1`.
- RF-39: EL SISTEMA registrará el resultado de cada tanda y el total.
- RF-40: SI la suite se corta o revienta, ENTONCES EL SISTEMA registrará «interrumpida» con su motivo.
- RF-41: SI la última suite sigue «empezada» y su proceso ya no vive, ENTONCES EL SISTEMA registrará «interrumpida» y avisará.
- RF-42: EL SISTEMA registrará cada arranque de la web y cada cierre con su motivo y quién lo pidió.
- RF-43: SI una web arranca y la anterior no registró su cierre, ENTONCES EL SISTEMA avisará de que cayó sin motivo conocido.
- RF-44: SI un lanzador de otra carpeta encuentra una web abierta en el puerto, ENTONCES EL SISTEMA la dejará abierta y arrancará en el puerto siguiente.
- RF-45: SI un Conversor no responde, ENTONCES EL SISTEMA esperará un plazo antes de terminarlo.

Mejora continua

- RF-46: EL SISTEMA tendrá en `docs/regresiones/` una entrada por fallo real, con su síntoma, causa, comprobación permanente y prueba.
- RF-47: LA suite fallará si una entrada no apunta a una prueba que exista o le falta un apartado.
- RF-48: `docs/regresiones/` tendrá una entrada por cada fallo de los de hoy.
- RF-49: LA suite fallará si una entrada nombra a un cliente, un alimentador o una empresa.

Una carpeta de DIgSILENT por empresa

Usuario, 2026-11-03: «en DIgSILENT crea su carpeta para cada empresa para evitar mezclar, y ahí debe importar cada vez que se haga de una empresa diferente». Completa 055:RF-7.

- RF-50: EL SISTEMA decidirá la carpeta de una fuente con una sola regla, por la empresa que dice la fuente o, si no la dice, la que indicó el operador en el espacio.
- RF-51: EL SISTEMA guardará en el espacio la empresa que indique el operador, aparte de la fuente.
- RF-52: SI la empresa coincide con la del perfil, ENTONCES EL SISTEMA usará la carpeta del perfil; SI difiere o no hay perfil, la de su nombre, que siempre es válida.
- RF-53: SI no se sabe la empresa, ENTONCES EL SISTEMA usará la carpeta del perfil como supuesto o, sin perfil, una neutra, y lo dirá en el plan, al importar y en el informe.
- RF-54: EL SISTEMA leerá la carpeta de un proyecto ya importado de su vínculo, sin volver a deducirla.
- RF-55: EL SISTEMA no ofrecerá entre las carpetas un proyecto de otra empresa.
- RF-56: EL SISTEMA creará la carpeta si no existe, sin mover ni borrar los proyectos que ya haya en ninguna.

Nada bloquea: el oráculo avisa y DIgSILENT dice la última palabra

Usuario, 2026-11-03: «nada debe bloquear, debes dar solución, para eso están los oráculos». Cambia 057:RF-5, 057:RF-6 y 005:RF-4, que siguen como están escritas en su spec.

- RF-57: SI el oráculo no converge o no se puede calcular, ENTONCES EL SISTEMA importará igual ese alimentador, con su aviso y su motivo (cambia 057:RF-5 y 057:RF-6).
- RF-58: CUANDO se importa así, EL SISTEMA dará el estado con el flujo de DIgSILENT: «OK» si converge, y si no, `IMPORTADO_SIN_CONVERGENCIA` o `IMPORTADO_SIN_DATO_DE_FLUJO` (078:RF-19 a RF-21).
- RF-59: SI la red no tiene ningún tramo, ENTONCES EL SISTEMA no la importará y lo dirá.
- RF-60: SI no se pudo fijar la copia del DGS de un trabajo, ENTONCES EL SISTEMA no importará ese alimentador y lo dirá, porque no hay fichero que importar, y seguirá con los demás.
- RF-61: SI el perfil trae una carpeta mal escrita y la empresa es desconocida, ENTONCES EL SISTEMA usará el nombre neutro y lo avisará, sin error (cambia 005:RF-4 en la web).
- RF-62: EL SISTEMA no nombrará a una empresa ni a su carpeta de datos en la lista negra de lectura: la lectura restringida ya rechaza lo que está fuera del árbol (072:RF-20).
- RF-63: LA ayuda de `tools/mcp_conversor.py` saldrá en UTF-8 con cualquier codificación de la consola.

Lo nuevo se adapta a las fases de su barra

Usuario, 2026-11-03: «nada debe bloquear, debes dar solución, para eso están los oráculos». 054:RF-10 (cumplida, sigue como está
escrita) no creaba la SED nueva ni los bancos que faltan si no había barra trifásica, y RF-9 de esta spec pide adaptarlos. Cambia
054:RF-10: la barra trifásica más cercana sigue siendo la primera opción (RF-8).

- RF-64: SI no hay barra trifásica para una carga nueva, ENTONCES EL SISTEMA la creará con las fases del punto donde se engancha y la anotará (cambia 054:RF-10).
- RF-65: CUANDO una carga nueva se adapta, EL SISTEMA dará esas fases a sus barras, su interruptor, su transformador y su línea de enlace, con un tipo de línea propio si el de la red tiene otras.
- RF-66: CUANDO una carga nueva se adapta, EL SISTEMA dirá su potencia y su corriente por fase frente a la trifásica.
- RF-67: SI la carga nueva parte un tramo, ENTONCES EL SISTEMA tomará como fases del punto las de ese tramo, no las de su extremo.
- RF-68: SI faltan barras trifásicas para los bancos de la calibración o de una obra, ENTONCES EL SISTEMA los pondrá con las fases de su barra, con su potencia y su corriente por fase en el aviso (cambia 054:RF-10).
- RF-69: EL SISTEMA reutilizará para una SED nueva solo un tipo de transformador con sus mismas fases; con menos de tres, alta y baja en D (054:RF-4).
- RF-71: CUANDO DIgSILENT termina una orden, EL SISTEMA añadirá a `ordenes.jsonl` de la cola su fecha, guion, modo, código, duración y causa del fallo normalizada, también si DIgSILENT murió a mitad. Pisco (2026-11-02 y 03): dos días y dos noches con solo 6,9 h de DIgSILENT calculando, 62 de 316 órdenes fallidas, dos caídas y 71 arranques; sin registro no se veía dónde se perdía el tiempo.
- RF-72: EL SISTEMA dará por guion y por día el número de órdenes, los fallos y su tasa, las horas, la media, la mediana con su intervalo de confianza del 95 % (remuestreo con semilla fija), el p90 y el máximo (`tools/estadistica_ordenes.py`).
- RF-73: DADO un corte entre dos versiones, EL SISTEMA contrastará H1 «la nueva tarda menos» con Mann-Whitney de una cola y «la nueva falla menos» con la exacta de Fisher, a un α que dice, y dirá si se demuestra; con menos de 5 órdenes en un grupo dirá que no hay contraste de duración. Usuario (2026-11-03): «esto debería entrar en estadística descriptiva e inferencia para demostración de hipótesis».
- RF-74: EL SISTEMA listará los fallos con la misma causa en el mismo guion más de una vez: un fallo que vuelve es una regresión y pide su comprobación permanente (RF-46). Usuario: «que cada vez mejore y no vuelva a fallar en lo mismo».

Avisos que prometen lo que el código no hace

La revisión de la 076 (2026-11-03, filas `operacion_web-031` y `catalogo_parametros-003`) halló que la web, al subir el catálogo
corregido, decía «Reconvierta para llevarlo al DGS». 032:RF-2 (cumplida) hace que el DGS escriba los parámetros de la entrada y
032:RF-14 lleva las fichas a «Sin proyecto»: el operador reconvertía y el DGS seguía igual.

- RF-70: CUANDO el operador sube el catálogo corregido, EL SISTEMA dirá que sus fichas se aplicarán al calibrar «Sin proyecto» y que
  el DGS del «Caso base» conserva los parámetros de la entrada, con una sola frase que dan el Registro y la pantalla.

Relectura de proyectos anterior a la importación

En la prueba real de la 005 T12 (2026-11-05), el operador leyó los proyectos de DIgSILENT y luego reimportó PRUEBA_005; la
verificación del «Caso base» falló con `PROJECT_BINDING_PROJECT_MISMATCH` porque comparaba el proyecto nuevo con la lista
leída antes de importarlo.

- RF-75: SI la última relectura de proyectos del espacio es anterior a la aceptación del vínculo, ENTONCES EL SISTEMA no tomará la
  ausencia del proyecto en esa lista como otro proyecto, y lo comprobará como si no hubiera relectura.
- RF-76: MIENTRAS DIgSILENT no haya entregado el usuario tras conectar, EL SISTEMA mantendrá la vigilancia de la conexión, de
  modo que un guion parado en esa llamada se termine en el mismo plazo que uno parado al conectar. En la misma prueba, la
  importación de PRUEBA_005 conectó y quedó 30 min en `GetCurrentUser` sin gastar CPU, ya fuera de la vigilancia de 019:RF-23.
- RF-77: CUANDO «Sin proyecto» cambia las unidades en paralelo de un transformador respecto del «Caso base» y «Con proyecto» no,
  EL SISTEMA las escribirá en el escenario de «Con proyecto», como los demás datos de operación de 014:RF-32. En PRUEBA_007
  (2026-11-05), la calibración dejó SE20497 con 4 × 630 kVA en «Sin proyecto» y «Con proyecto» seguía con 1 × 630 kVA para
  1 429 kW: no convergía ni sin cargas nuevas.
- RF-78: CUANDO se sincroniza «Con proyecto» con «Sin proyecto», EL SISTEMA adelantará a la hora de «Con proyecto» las etapas de
  sus variaciones activas fechadas justo después de ella, para que vea los transformadores nuevos y las fichas de la base. Era la
  causa de fondo del caso de RF-77: «Con proyecto» tenía su hora a las 15:01:13 y las etapas de `Fichas_` y `SED_NTP_` eran de
  las 15:01:14 y 15:01:15; tenía SE20497 con 1 × 160 kVA y no convergía ni sin cargas nuevas.
- RF-79: CUANDO la aceptación nativa (importar, verificar el «Caso base») conecta con el motor de DIgSILENT de la máquina, EL
  SISTEMA lo hará con la conexión del arnés y su vigía (019:RF-23), y no por su cuenta. En PRUEBA_007 (2026-11-06) la verificación
  del «Caso base» quedó 10 min en `pf.GetApplication()` sin CPU (pila leída con py-spy), como la importación de la noche anterior.
  Aclaración de RF-76: aquel cuelgue era este; la vigilancia de `GetCurrentUser` sigue siendo correcta.

Tramos que una variante cortada deja abiertos en «Con proyecto»

En Pisco de prueba (`20261107-043049_CSG_TXT_SISTEMA_PISCO`, 2026-11-07) la web se reinició mientras la escalera medía una
transferencia de rama (087:RF-31). El escenario de «Con proyecto» se quedó con `SEC_1091_1055499` y `SEC_1091_957116` fuera de
servicio, en servicio en «Sin proyecto» y sin ninguna variación que lo explicase: 724 barras de media sin tensión, la
confirmación conjunta (087:RF-45) dio «740 barras aisladas» y RF-47 rehízo obras sobre una red rota. Abrir es dato de operación:
con el escenario activo, DIgSILENT lo guarda en él y no en la etapa de la variación (042:RF-19), y borrar la variante no lo
deshace. La migración a la misma tensión, además, abría su entrada sin anotarla.

- RF-80: CUANDO una obra abre un tramo, un acoplador o una llave que ya existían, EL SISTEMA anotará antes de abrirlo, en la fila
  de la obra y en un registro en disco por proyecto que sobrevive a la orden, el elemento, su caso y la variación de la obra.
- RF-81: CUANDO se borra la variante evaluada de la escalera (025:RF-54) o una obra queda inactiva, EL SISTEMA volverá a cerrar en
  su caso lo que abrió, también lo que está fuera de servicio, y lo sacará del registro.
- RF-82: SI al empezar una orden de obras el registro trae aperturas de una orden que no terminó, ENTONCES EL SISTEMA las cerrará
  en su caso, guardará su escenario y lo dirá en el informe con su lista, salvo las de una obra aplicada cuya variación sigue
  activa en ese caso; de una evaluación, avisará también de la variación que quedó en el proyecto.
- RF-83: CUANDO empieza la escalera de «Con proyecto», EL SISTEMA buscará los tramos, transformadores, acopladores y llaves fuera
  de servicio o abiertos en «Con proyecto» y en servicio o cerrados en «Sin proyecto»; los que no graba, ni en ellos ni en sus
  barras, ninguna variación activa de «Con proyecto» y que figuran en el registro o dejan sin tensión barras que en «Sin
  proyecto» la tienen, los devolverá al estado de «Sin proyecto» en el escenario de «Con proyecto» y el informe los listará.
- RF-84: SI uno de los de RF-83 no lo explica ninguna variación, no figura en el registro y no deja ninguna barra sin tensión,
  ENTONCES EL SISTEMA no lo tocará, porque puede ser un cambio del operador, y lo avisará con su lista.
- RF-85: SI «Con proyecto» no tiene escenario de operación, ENTONCES EL SISTEMA no restituirá nada de RF-83, porque escribir el
  servicio cambiaría la red de todos los casos, y lo avisará con su lista.

## Fuera de alcance

- Cambiar `CASO_BASE_CALIBRABLE` para impedir calibrar: el flujo no bloquea (RF-30).
- Corregir las fases de tramos y SED en el modelo (054:RF-9, RF-10): las trae la rama de fases; esta spec las comprueba.
- Probar en DIgSILENT, en el navegador o correr una suite real: van en sus tareas.
- Averiguar la causa de (e): se dice «sin confirmar» y queda la huella para medirlo.

## Criterios de finalización

- `grep -rnoE "081:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-69.
- Un «Caso base» que no converge por una causa reconstruible llega convergido, con su anotación, en la prueba con doble y en DIgSILENT.
