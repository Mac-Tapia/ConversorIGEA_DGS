# Spec 019 — Arnés de DIgSILENT: acceso exclusivo, conexión única y obras enchufables

Estado: cumplida (2026-10-15; RF-14 a RF-16 el 2026-10-18) · Fecha: 2026-10-15

## Contexto y objetivo

Los guiones de DIgSILENT (`tools/*_pf.py`, 13 conectan con `GetApplicationExt`) repiten
cada uno la conexión, la activación del proyecto y la restitución del caso, y solo la web
los pone en fila (carril `powerfactory` de `web/jobs.py`). El 2026-10-15, con CA101, se
vieron los fallos que esto produce:

- Dos procesos a la vez: una sesión lanzaba guiones mientras otra tenía DIgSILENT, y los
  segundos morían con «Exit with error code 4002» sin esperar ni decir quién lo tenía.
- Cada guion activa el proyecto desde cero: unos 5 minutos por ejecución, también para una
  lectura de un segundo.
- Procesos colgados: sondas cortadas dejaban el intérprete con 4 GB abierto y había que
  cerrarlo a mano.
- Cada obra nueva exige tocar el núcleo de `obras_pf`: la consigna de tensión de la
  cabecera, necesaria en CA101, no existía como obra y se hizo con un guion suelto.

El objetivo es un arnés único, robusto y modular para hablar con DIgSILENT: un solo dueño
del motor a la vez en toda la máquina, una conexión y una activación comunes, procesos que
no quedan colgados, y obras que se añaden sin tocar el núcleo.

## Usuarios / actores

Ingeniero de planificación desde la web; CLI y guiones sueltos; otras sesiones o
herramientas que lanzan guiones en la misma máquina; DIgSILENT PowerFactory 2024.

## Historias de usuario

- H1: Como ingeniero quiero que, si DIgSILENT está ocupado, mi acción espere su turno y me
  diga quién lo tiene, en vez de fallar.
- H2: Como ingeniero quiero que varias acciones seguidas sobre el mismo proyecto no lo
  activen cada vez desde cero.
- H3: Como mantenedor quiero añadir una clase de obra (p. ej., consigna de cabecera) sin
  tocar la lógica común de variaciones, casos y flujos.

## Requisitos funcionales (EARS)

Acceso exclusivo al motor

- RF-1: EL SISTEMA dará el motor de DIgSILENT a un solo proceso a la vez en la máquina,
  sea de la web, del CLI o de un guion suelto.
- RF-2: MIENTRAS otro proceso tenga el motor, EL SISTEMA esperará su turno hasta un
  límite configurable y dirá quién lo tiene (proceso, guion y desde cuándo).
- RF-3: SI la conexión devuelve que el motor está ocupado, ENTONCES EL SISTEMA reintentará
  hasta el límite de RF-2 en vez de fallar a la primera.
- RF-4: SI el proceso que tenía el motor terminó sin soltarlo, ENTONCES EL SISTEMA lo
  detectará y lo liberará sin intervención.
- RF-13: SI el operador tiene DIgSILENT abierto a mano, ENTONCES EL SISTEMA no lanzará la
  acción y avisará de que lo cierre.

Conexión y activación comunes

- RF-5: EL SISTEMA conectará, activará el proyecto y restituirá el caso de estudio que
  había en un solo punto común, que usarán todos los guiones.
- RF-6: EL SISTEMA escribirá la primera línea en cuanto DIgSILENT responda (005:RF-21) y
  cada paso largo (activar, flujo, guardar) con su duración.
- RF-7: DONDE se ejecuten varias acciones seguidas sobre el mismo proyecto, EL SISTEMA las
  podrá servir con una sola activación, en un proceso de DIgSILENT que se mantiene abierto
  y atiende una cola de órdenes.
- RF-8: SI ese proceso no responde en el límite de RF-2 o muere, ENTONCES EL SISTEMA lo
  cerrará, avisará y la siguiente acción abrirá otro.
- RF-14: SI el motor lo tiene ese proceso sin ninguna orden en curso, ENTONCES EL SISTEMA le
  pedirá que se cierre y dará el turno al guion que espera, sin esperar los 2 min de
  inactividad (2026-10-18: cada sonda suelta esperaba al servidor ocioso).
- RF-15: EL SISTEMA escribirá la salida de cada guion de DIgSILENT línea a línea también
  cuando va a un fichero (2026-10-18: la limpieza de Chincha no mostró nada en 10 min).
- RF-16: SI un guion no encuentra la API de DIgSILENT en su ruta, ENTONCES EL SISTEMA la
  buscará en la instalación de DIgSILENT antes de decir que no está (2026-10-18: cada sonda
  pedía el ``PYTHONPATH`` a mano).

Procesos que no quedan colgados

- RF-9: CUANDO se cancela o se corta una acción, EL SISTEMA terminará su proceso de
  DIgSILENT y sus hijos, y lo dirá en el Registro.
- RF-10: EL SISTEMA no dejará al terminar ninguna copia de proyecto creada para sondear ni
  ningún caso distinto del que estaba activo.

Obras enchufables

- RF-11: EL SISTEMA definirá cada clase de obra en un módulo propio con su validación, su
  simulación y su construcción, registrado por nombre, sin cambiar la lógica común de
  variaciones, casos, flujos y comprobación de «Sin proyecto».
- RF-12: EL SISTEMA tendrá la obra «consigna de cabecera»: la tensión de la red externa en
  p.u., dentro de los límites del perfil, solo en «Con proyecto».

## Requisitos no funcionales

- Ningún guion de `tools/*_pf.py` llama a `GetApplicationExt` fuera del punto común (RF-5),
  comprobado por una prueba que recorre las fuentes.
- La suite sin DIgSILENT sigue en verde con el doble `fake_pf`; los guiones se validan en
  DIgSILENT real (P11).
- Universal: nada depende de una empresa ni de un alimentador (P13).

## Casos límite

- Dos guiones lanzados en el mismo segundo; el dueño muere a mitad de un flujo; DIgSILENT
  abierto a mano por el operador; proyecto que ya está activo; cancelación durante la
  activación.

## Fuera de alcance

- Repartir el trabajo entre máquinas.
- Cambiar los estudios o las reglas de calibración.

## Criterios de finalización

- Cada RF citado por al menos una prueba (`grep -rnoE "019:RF-[0-9]+" tests`) y suite en
  verde.
- Prueba en DIgSILENT real: dos acciones a la vez esperan su turno; tres acciones seguidas
  con una sola activación; la obra de consigna de cabecera en CA101.

## Dudas resueltas

1. El proceso que mantiene DIgSILENT abierto (RF-7) se cierra tras 2 minutos sin órdenes
   (usuario, 2026-10-15).
2. Espera máxima por el motor (RF-2): 10 minutos (usuario, 2026-10-15).
3. Si el operador tiene DIgSILENT abierto a mano, se avisa y no se lanza (usuario,
   2026-10-15): RF-13.
