# Spec 091 — De la calibración al estudio, en su orden y sin avisos que engañen

Estado: aprobada · Fecha: 2026-11-05 · Origen: orden del usuario · Integrada en main: 2026-11-07

Sustituye a la reserva del número 091 (rama `fix/091-flujo-calibracion`). Al integrarla, el integrador de `main`
cambió tres cosas según las reglas del proyecto («Reconstruir, no bloquear» y «Cada fallo, una comprobación»): el
estudio sin recalibrar se avisa y no se rechaza (RF-20 a RF-22), la RF-33 se retira porque ya la cubre 086:RF-22, y
la RF-19 cambia 025:RF-10.

## Contexto y objetivo

El usuario, el 2026-11-05, tras una comprobación real de la web con TM102: «no puede hacer lo que tú quieres, debe
hacer lo correcto según el flujo correcto, trabajar con los archivos originales»; «verifica que siga el flujo:
calibración, después recalibración y [el] caso de estudio»; y «corrige los fallos, debe estar bien hecho, no debe haber
fallos para que puedan hacer estudios».

Lo que la comprobación encontró, reproducido en el navegador sobre TM102:

- Con DIgSILENT abierto a mano, la web decía «Ábralo y reintente» (el arnés exige lo contrario, 019:RF-13), y el aviso
  previo a importar lo pedía «preferiblemente abierto». El Registro solo decía «terminó al arrancar (código ?)».
- Al cambiar de pestaña se perdía el proyecto elegido y lo hecho en los pasos.
- 65 clientes del libro de febrero de 2026 no estaban en el libro de suministros (el de septiembre) y quedaban fuera de
  la tabla cruzada: su SED se escalaba en vez de quedar fija, aunque la hoja de cada uno dice su alimentador y su SED.
- En un proyecto recién importado, «Ajustar» estaba activo antes de buscar la máxima: tomaba la última del espacio, de
  otro proyecto.
- Con «Todo 2026» no se podía cruzar y el ajuste cruzaba por dentro: se calibraba sin ver la tabla.
- «Preparar los estudios» se activaba tras la calibración, sin la recalibración.
- El informe decía «cuadrado» y «el kVAR es informativo» en una recalibración cuya Q no cuadró.

## Requisitos

DIgSILENT abierto o sin conexión

- RF-1: SI una acción no puede usar DIgSILENT porque está abierto a mano, ENTONCES EL SISTEMA dirá que hay que cerrarlo, con su número de proceso.
- RF-2: SI una acción no puede usar DIgSILENT por otra causa, ENTONCES EL SISTEMA dirá la causa que registró el arnés.
- RF-3: EL SISTEMA no pedirá en ningún mensaje que se abra DIgSILENT para una acción de la web.
- RF-4: CUANDO el proceso de DIgSILENT termina al arrancar, EL SISTEMA escribirá en el Registro la última causa que dejó en su registro, sin un código desconocido.
- RF-5: EL SISTEMA avisará antes de importar que DIgSILENT debe estar cerrado.
- RF-6: EL SISTEMA retirará las marcas de conexión de los procesos que ya no viven.

Lo hecho en una pestaña

- RF-7: CUANDO el operador cambia de pestaña, EL SISTEMA conservará el proyecto elegido y lo hecho en la pestaña que deja.
- RF-8: CUANDO se abre otro espacio de trabajo, EL SISTEMA empezará las pestañas sin lo del espacio anterior.

Clientes que no están en el libro de suministros

- RF-9: SI un cliente del libro no está en el libro de suministros y una celda de la cabecera de su hoja es una SED de la red cargada, ENTONCES EL SISTEMA lo cruzará con esa SED.
- RF-10: EL SISTEMA dirá en la fila de ese cliente que su SED sale de su hoja y que no está en el libro de suministros.
- RF-11: SI la cabecera de la hoja nombra dos o más SED de la red, ENTONCES EL SISTEMA dejará al cliente aparte, con ese motivo, sin elegir una.
- RF-12: SI el cliente no tiene hoja, o su hoja no nombra ninguna SED de la red, ENTONCES EL SISTEMA lo dejará aparte y dirá cuál de las dos cosas le falta.
- RF-13: EL SISTEMA leerá la cabecera de las hojas de un libro una sola vez mientras el libro no cambie.

La máxima de cada proyecto

- RF-14: CUANDO la web busca una máxima, EL SISTEMA guardará con ella el proyecto para el que se buscó.
- RF-15: SI la máxima elegida para un plan de ajuste se buscó para otro proyecto, ENTONCES EL SISTEMA rechazará el plan y dirá de qué proyecto es.
- RF-16: EL SISTEMA solo ofrecerá en la web, para ajustar, una máxima del proyecto elegido y del año elegido.

La tabla cruzada antes de ajustar

- RF-17: MIENTRAS haya libros de suministros y de clientes y la tabla cruzada de la máxima no esté a la vista, EL SISTEMA no ofrecerá simular ni ajustar, y dirá que falta cruzar.
- RF-18: CUANDO se busca otra máxima, EL SISTEMA dejará de dar por vista la tabla cruzada anterior.
- RF-19: MIENTRAS esté elegido el año entero y haya máxima, EL SISTEMA permitirá cruzar, cada alimentador con el libro del mes de su máxima.
- Aclaración de RF-19: cambia 025:RF-10. Ese requisito cruzaba con el año entero solo dentro del ajuste (2.4), y el
  paso 2.3 pedía elegir un mes para ver la tabla; con la RF-17 el ajuste escribe lo que la tabla muestra, así que el
  cruce por el mes de cada máxima se hace y se ve en el paso 2.3.

El estudio, después de la recalibración

- RF-20: SI un alimentador pedido para un estudio solo tiene la calibración, ENTONCES EL SISTEMA preparará el plan del estudio con un aviso que nombre el alimentador y diga que falta recalibrar.
- RF-21: MIENTRAS el ajuste base del proyecto no sea una recalibración, EL SISTEMA dirá en la web, junto a «Preparar los estudios» y sin apagarlo, que falta recalibrar.
- RF-22: SI un ajuste anterior a esta spec no dice su tipo, ENTONCES EL SISTEMA preparará el estudio con un aviso de que no consta su recalibración.
- Aclaración de RF-20 a RF-22: la rama original rechazaba el plan y apagaba el botón. Nada bloquea salvo la red
  vacía (memoria «Reconstruir, no bloquear»): el estudio se prepara, el aviso llega al plan y a la pantalla, y el
  operador decide.
- RF-23: EL SISTEMA solo mostrará como último ajuste y como último estudio los del proyecto elegido.

Lo que se informa

- RF-24: CUANDO termina una recalibración, EL SISTEMA dirá en su informe si la Q quedó cuadrada.
- RF-25: SI la Q de una recalibración no quedó cuadrada, ENTONCES EL SISTEMA dirá en pantalla que solo cuadró la P y por qué, sin llamar informativo al kVAR.
- RF-26: SI otro registro del periodo da el mismo kW máximo que el elegido, ENTONCES EL SISTEMA avisará junto a la máxima de qué registro es y cuál eligió.
- RF-27: EL SISTEMA describirá en el paso 2.4 el reparto de las escaladas por potencia instalada, sin decir que conservan la P y Q del archivo.
- RF-28: EL SISTEMA dirá en el informe que el FP de una fija es el de su registro del instante cuando lo tiene, y que el mínimo se aplica al cociente EA/ERI del mes.
- RF-29: EL SISTEMA dirá en el resumen de la carga cuántos alimentadores tienen tramos y cuántos no, sin llamar convertibles a los que no los tienen.
- RF-30: EL SISTEMA redactará el rechazo de un fichero de demanda con el nombre de su casilla, sin artículo fijo.
- RF-31: CUANDO se pulsa Intro en una ruta de los libros de medición, EL SISTEMA la aplicará igual que «Usar ruta».
- RF-32: EL SISTEMA dirá en el diagnóstico que Tesseract está disponible si lo encuentra en las rutas que usa para leer documentos.
- RF-33: no se usa (lo superó 086:RF-22: preparar_entorno_sin_red decide HF_HUB_OFFLINE).
- RF-34: SI la foto del gemelo tras una acción no se puede hacer, ENTONCES EL SISTEMA dirá su motivo en el Registro de esa acción.

## Fuera de alcance

- Botones para `digital-twin/entrenar`, `evaluar` y `temporal` y para `asistente/mejoras`: entrenar sigue con su propia
  puerta (spec 071).
- Avisar de la recalibración en las cargas nuevas y en las obras: solo se avisa en los estudios, que es lo que ordenó el usuario.
- Rechazar o apagar el estudio sin recalibrar: se avisa (RF-20 a RF-22).
- `HF_HUB_OFFLINE` en el arranque de la web: lo decide `preparar_entorno_sin_red` (086:RF-22).
- Explicar la Q de cabecera de un medidor concreto: se dice que no cuadra y por qué, sin cambiar la medición.
- Cambiar el libro de suministros de cada empresa o pedir uno por mes.

## Criterio de aceptación

Por la web, sobre un proyecto de prueba importado de los TXT originales: calibración, recalibración y estudio, en ese
orden, con el ajuste apagado y explicado hasta que hay máxima del proyecto y tabla cruzada, y el estudio avisado hasta
la recalibración; y con DIgSILENT abierto a mano, el mensaje que pide cerrarlo.
