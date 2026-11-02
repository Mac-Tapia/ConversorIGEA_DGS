# Spec 064 — Arnés de DIgSILENT sin atajos: un turno para todos y estado restituido

Estado: cumplida · Fecha: 2026-11-01

La auditoría de arquitectura del 2026-11-01 encontró que la spec 019, cumplida, dejaba
caminos fuera del arnés. Siete guiones de `tools/` conectan con `GetApplication()` sin
pedir el turno del motor, y la web lanza dos de ellos («Red del sistema» y «Escenario
base») como un proceso cualquiera: sin cerrar huérfanos, sin límite de arranque y sin
pasar por el servidor. Es el camino por el que vuelve el «Exit with error code 4002» que
la 019 quitó. La prueba de 019:RF-5 solo buscaba `GetApplicationExt(` y no los veía.

Además, el servidor que mantiene DIgSILENT abierto ejecuta cada orden sin guardar nada:
si un guion falla a mitad, la orden siguiente hereda el caso, la hora de estudio, el
escenario y las variaciones que dejó. Cada guion restituye lo suyo al terminar bien
(011:RF-26 lo arregló para el optimizador), pero no si una excepción lo corta. Y
`set_nueva_operacion_pf.py` (063:RF-36) conecta con el arnés pero no está entre los
guiones que el servidor atiende, así que cada orden cierra el servidor y paga otra
conexión de 12 a 55 s.

Esta spec amplía la 019 sin cambiarla (está cumplida y no crece).

- RF-1: EL SISTEMA conectará con DIgSILENT, en todo guion de `tools/`, solo por medio de
  `pf_arnes.conectar`, salvo la aceptación nativa (`powerfactory_acceptance.py`), que toma el
  turno con `tomar_turno` porque puede engancharse a un DIgSILENT abierto a mano.
- RF-2: SI un guion de `tools/` o de `src/` llama a `GetApplication` o a `GetApplicationExt`
  fuera de `pf_arnes` y de la excepción de RF-1, ENTONCES la suite fallará nombrando el
  fichero y la línea.
- RF-3: CUANDO la web lance la red del sistema o el escenario base, EL SISTEMA los
  ejecutará con el intérprete y el entorno de DIgSILENT, como los demás guiones que lo
  usan. Los datos que faltan (`--solo-datos`) no tocan DIgSILENT y siguen sin él.
- RF-4: CUANDO el servidor de DIgSILENT empiece una orden, EL SISTEMA anotará el proyecto
  activo, el caso activo, su hora de estudio, el escenario activo y las variaciones de red
  activas.
- RF-5: SI una orden atendida por el servidor termina con un código distinto de 0 o con
  una excepción, y el proyecto activo sigue siendo el anotado, ENTONCES EL SISTEMA dejará
  el caso, su hora de estudio, el escenario y las variaciones activas como estaban al
  empezar.
- RF-6: CUANDO EL SISTEMA restituya el estado tras una orden fallida, escribirá en el
  registro de esa orden qué devolvió a su sitio.
- RF-7: SI la restitución de RF-5 falla, ENTONCES EL SISTEMA lo escribirá en el registro
  de la orden y seguirá atendiendo la cola.
- RF-8: EL SISTEMA atenderá `set_nueva_operacion_pf.py` en el servidor de DIgSILENT.

Ampliación tras la auditoría del 2026-11-02 (`AUDIT/auditoria_otra_sesion_20261102/informe.md`),
que reprodujo dos fallos con objetos en memoria: la restitución anunciaba un caso que no se había
activado y escribía su hora en otro caso (H1), y un fallo al fotografiar dejaba la orden sin
cerrar y podía tumbar el servidor (H2).

- RF-9: SI la lectura del estado falla antes de una orden, ENTONCES EL SISTEMA lo escribirá en
  el registro de esa orden, la atenderá igual, la cerrará con su código y seguirá con la
  siguiente de la cola; distinguirá ese fallo de no tener proyecto activo.
- RF-10: CUANDO EL SISTEMA restituya el estado, comprobará el retorno de cada activación,
  releerá lo activo, escribirá la hora solo en el caso de la foto y comparará la foto final;
  SI algo no quedó como al empezar, ENTONCES lo dirá como restitución fallida, sin anunciarlo
  como hecho.

## Fuera de alcance

- Restituir el estado tras una orden que termina bien: el proyecto y el caso que deja
  activos los usa la orden siguiente (019:RF-7), y cada guion restituye lo suyo.
- Cancelar sin cerrar DIgSILENT los guiones que no son cancelables: se cancelan con su
  fichero cuando lo admiten (019:RF-9); el resto se corta como hasta ahora.
- Revisado y descartado en la auditoría:
  - `etapas_al_dia` adelanta etapas de variaciones activas que pueden ser del operador.
    Es a propósito (063:RF-5: la recalibración considera todos los cambios hechos en la
    red) y el informe lo avisa.
  - `_limpiar_etapa_de_la_central` solo borra lo grabado en la variación propia de la
    central (021:RF-37), no objetos del operador.
  - Los borrados por nombre de `casos_pf` y `pide_pf` recaen sobre casos y escenarios
    que el sistema crea en carpetas y con nombres propios.
