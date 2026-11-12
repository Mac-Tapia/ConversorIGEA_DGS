# Spec 096 — Tras suspender el equipo, la web vuelve sola al último trabajo pendiente

Estado: cumplida (2026-11-08: tareas cerradas por orden del usuario, sin corrida propia; su aceptación pasa a la spec 100) · Fecha: 2026-11-05 · Origen: usuario, 2026-11-05, Pisco, con la recalibración de AL209 y PA217 en
curso: «¿si lo suspendo, mi equipo seguiría corriendo?», y después «implementa que cada vez que se suspende regrese al
último trabajo pendiente», «solo y sin preguntar».

Numeración (2026-11-06, 033:RF-4): se escribió como 093 en la rama `feat/093-retomar-tras-suspender`, sin
fundir, mientras la 093 de `main` pasaba a ser «La sigla de la carga…»; entra en `main` como 096.

## Contexto y objetivo

Una recalibración de un sistema tarda de 20 minutos a horas en DIgSILENT. Al suspender el equipo se congela todo: la
web, el guion y DIgSILENT. Al despertar, los procesos siguen donde estaban, pero la orden de DIgSILENT puede fallar
(licencia de red caducada, conexión perdida) y el trabajo queda fallido; y si la web se cerró, el trabajo queda
«interrumpido» (086:RF-9) y nadie lo retoma. El operador tenía que volver a lanzarlo a mano, o no suspender.

## Requisitos funcionales (EARS)

- RF-1: MIENTRAS un trabajo de la web está en curso, EL SISTEMA pedirá a Windows que no suspenda el equipo por
  inactividad, y dejará de pedirlo al terminar el trabajo.
- RF-2: SI un trabajo falla y el equipo estuvo suspendido durante él, ENTONCES EL SISTEMA lo repetirá una vez, solo y
  sin pedir confirmación, y lo dirá en su registro con el tiempo que estuvo suspendido.
- RF-3: SI el trabajo repetido vuelve a fallar, ENTONCES EL SISTEMA lo dejará fallido con su error, sin repetirlo más.
- RF-4: EL SISTEMA no repetirá un trabajo cancelado por el operador, ni uno que falló sin que el equipo se suspendiera.
- RF-5: CUANDO la web arranca y el último trabajo de un espacio quedó interrumpido, EL SISTEMA lo relanzará solo, con
  la misma petición, DONDE ese trabajo se pueda repetir desde su petición (hoy, «Recalibrar», que retoma lo hecho).
- RF-6: EL SISTEMA relanzará cada trabajo interrumpido una sola vez, y no lo relanzará mientras siga vivo el guion que
  lanzó en la ejecución anterior de la web.
- RF-7: EL SISTEMA dirá en el registro del trabajo relanzado de qué trabajo interrumpido viene.
- RF-8: CUANDO el navegador no recuerde ningún espacio, o el que recuerda ya no exista, LA WEB abrirá el último modificado
  de los espacios con datos cargados que se abren, y creará uno nuevo solo si no hay ninguno. (2026-11-12: con el 8765
  ocupado por el programa instalado, la web abrió en el 8766 y creó un espacio vacío; los 42 del operador no se veían.)

## Relación con otras specs

- Cambia 067:RF-14 y 070:RF-38 y RF-56 para la suspensión y la caída de la web: la escritura que el operador ya lanzó
  se repite o se relanza sola (usuario, 2026-11-05: «solo y sin preguntar»). Una tarea nueva del asistente sigue
  pidiendo confirmación.
- Amplía 086:RF-9: el interrumpido que se puede repetir no se queda solo en el registro.

## Fuera de alcance

- Impedir que el operador suspenda el equipo a mano o que cierre la tapa: Windows lo permite siempre.
- Repetir trabajos que no se pueden rehacer desde su petición (los que guardan su estado solo en memoria).

## Criterios de finalización

- `grep -rnoE "096:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-7, y `grep -rnoE "096:RF-[0-9]+" frontend/test` lista RF-8.
- Con una recalibración en curso, el equipo suspendido y despertado: el trabajo termina, repetido si su orden falló.
