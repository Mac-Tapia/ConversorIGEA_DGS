# Spec 018 - Vínculo de proyectos de DIgSILENT compartido entre espacios de trabajo

Estado: implementada (2026-10-15; RF-9 a RF-12 añadidos y hechos el mismo día) - Fecha:
2026-10-15 - Origen: PROJECT_BINDING_MISSING sobre CA101 en un espacio de trabajo que no
aceptó el proyecto (2026-10-15)

## Contexto y objetivo

El vínculo entre un proyecto de DIgSILENT y su fuente (spec 015) se guardaba solo en el
`workspace.json` del espacio que lo aceptó. La carpeta de DIgSILENT es común a todos los
espacios, así que cualquier espacio lista el proyecto, pero no puede usarlo: la web se
bloqueaba con `PROJECT_BINDING_MISSING` sin una causa visible.

Además, «Verificar el caso base» no comprobaba el vínculo en el servidor. La primera
verificación de un proyecto sin vínculo lo creaba con la fuente activa, sin demostrar que
el proyecto procedía de esa fuente. Era el hueco que la aceptación existe para cerrar.

La huella de la fuente (`source_fingerprint`) cubre los ficheros de entrada, no las
opciones de conversión. Dos espacios con la misma fuente pueden producir DGS distintos, así
que compartir el vínculo exige comprobar también el DGS que se aceptó.

## Requisitos

- RF-1: Cuando un proyecto de DIgSILENT tiene un vínculo aceptado en cualquier espacio de
  trabajo y la fuente activa del espacio tiene el mismo modo y la misma huella, el sistema
  deberá usar ese vínculo sin repetir la aceptación.
- RF-2: Mientras el registro compartido de vínculos sea ilegible, el sistema deberá bloquear
  el uso de los proyectos con `PROJECT_BINDING_REGISTRY_UNREADABLE`, sin caer a la copia del
  espacio y sin sobrescribir el registro.
- RF-3: Cuando el espacio de trabajo no tenga ejecución fuente activa, el sistema deberá
  informar `PROJECT_BINDING_NO_ACTIVE_SOURCE`, y no un desajuste de fuente.
- RF-4: Cuando la carpeta del vínculo y la carpeta actual de DIgSILENT sean distintas, el
  sistema deberá bloquear el proyecto con `PROJECT_BINDING_FOLDER_MISMATCH`.
- RF-5: Cuando se pida verificar el «Caso base», el servidor deberá exigir un vínculo válido
  para los alimentadores pedidos antes de tocar DIgSILENT, y la verificación no deberá crear
  vínculos nuevos.
- RF-6: Cuando el DGS de un alimentador con huella registrada no sea el que se aceptó, el
  sistema deberá bloquear la acción con `PROJECT_BINDING_DGS_MISMATCH`. Un alimentador sin
  huella registrada no se bloquea por esta causa.
- RF-7: El registro compartido deberá escribirse de forma atómica, conservar todos los
  proyectos y no dejar ficheros temporales.
- RF-8: Al arrancar el servidor, los vínculos que ya tienen los espacios de trabajo deberán
  pasar al registro compartido. Si un mismo proyecto tiene vínculos distintos, gana el
  aceptado más tarde; un vínculo cuya huella no cuadra se descarta; una segunda siembra no
  cambia nada.

### Usar la fuente con la que se aceptó (añadido el 2026-10-15)

El registro compartido no bastó para CA101: el navegador abrió un espacio nuevo, sin fuente
cargada, y el proyecto quedó bloqueado con `PROJECT_BINDING_NO_ACTIVE_SOURCE`, aunque su
ejecución fuente seguía en disco en el espacio que lo aceptó y su «Caso base» estaba
verificado. La pestaña de cargas promete trabajar «sin convertir nada»; pedir que se vuelva
a cargar y convertir la misma fuente para demostrar lo que el disco ya demuestra rompía el
flujo. Tras reiniciar la web pasaba algo parecido: verificar el «Caso base» exigía la red
cargada en memoria, que no hace falta para comparar el DGS y su sidecar.

- RF-9: Cuando un proyecto esté bloqueado por `PROJECT_BINDING_NO_ACTIVE_SOURCE` o
  `PROJECT_BINDING_SOURCE_MISMATCH` y la ejecución fuente de su vínculo exista en disco, en
  este espacio o en otro, con el mismo modo y la misma huella que el vínculo, el listado de
  proyectos deberá decirlo (`binding_fuente_disponible`).
- RF-10: Cuando el operador pida usar la fuente del vínculo, el sistema deberá copiar esa
  ejecución al espacio si no la tiene, hacerla la ejecución activa, traer del espacio de
  origen la última calibración del proyecto y los DGS unidos de esa ejecución si el espacio
  no los tiene, y los libros de demanda medida que sigan en disco si el espacio no tiene
  ninguno, y devolver el estado del vínculo de los proyectos ya leídos sin volver a
  abrir DIgSILENT. Las entradas del espacio no se tocan. Si la ejecución no está, o su
  manifiesto no tiene el modo y la huella del vínculo, deberá informar
  `PROJECT_BINDING_SOURCE_UNAVAILABLE` y no cambiar nada.
- RF-11: Cuando el proyecto elegido esté bloqueado por `PROJECT_BINDING_NO_ACTIVE_SOURCE` con
  la fuente del vínculo disponible, la interfaz deberá usarla sin pedir confirmación, porque
  el espacio no tiene nada que perder; con otra fuente activa, deberá ofrecer un botón que
  diga qué ejecución se usará.
- RF-12: La verificación del «Caso base» no deberá exigir la red cargada en memoria: le
  bastan el manifiesto de la ejecución activa y el DGS con su sidecar en disco. Un DGS de una
  reconstrucción sí la exige, porque su informe se valida con lo cargado, y entonces el
  mensaje deberá decir que se cargue la red.
- RF-13: Cuando se abra la pestaña de cargas sin una lectura de proyectos en la sesión (por
  ejemplo, tras reiniciar la web), el sistema deberá mostrar la última lista leída en el
  espacio o, si el espacio no tiene ninguna, la más reciente de la misma carpeta de DIgSILENT
  en otro espacio, con el vínculo recalculado, sin abrir DIgSILENT; «Volver a leer
  proyectos» la actualiza.
- RF-14: Cuando una acción sobre un proyecto de DIgSILENT (verificar el «Caso base» y toda
  acción nativa) reciba el nombre de una red unida o por sistema del espacio (`SISTEMA_NASCA`),
  el sistema deberá tomarlo como sus alimentadores antes de comprobar el vínculo. (Nasca,
  2026-10-24: verificar el «Caso base» con `['SISTEMA_NASCA']` falló con
  `PROJECT_BINDING_FEEDER_MISMATCH`, aunque el vínculo tenía todos sus alimentadores.)
- RF-15: Cuando la verificación del «Caso base», que lee el DGS, encuentre la ejecución activa
  con la misma fuente (modo y huella) que la del vínculo pero sin el DGS aceptado, el sistema
  deberá usar sola la ejecución del vínculo, como con
  «Usar la fuente del vínculo» (RF-10), y decirlo, en vez de pedir DGS que nunca se
  importaron. (Nasca, 2026-10-24: tras importar `SISTEMA_NASCA` se volvió a cargar la misma
  fuente; la verificación pedía `CH101.dgs` y los demás de la ejecución nueva.) Las demás
  acciones nativas trabajan sobre el proyecto ya importado y no cambian la ejecución activa
  (Chincha, 2026-10-24: puesto también en ellas, la escalera cambió sola de ejecución y falló).

## Fuera de alcance

- Bloqueo entre procesos: si varios procesos de la web escribieran el mismo registro, haría
  falta un bloqueo de fichero. Hoy hay un único proceso.
- Comprobación del DGS en el listado de proyectos: solo se aplica en las acciones.

## Decisiones

- El registro compartido prevalece sobre la copia del espacio. La copia solo responde cuando
  el registro no tiene el proyecto (espacios anteriores a esta spec).
- La huella de la fuente y la huella del DGS se comprueban juntas. La primera dice que la
  entrada es la misma; la segunda, que la conversión también.
