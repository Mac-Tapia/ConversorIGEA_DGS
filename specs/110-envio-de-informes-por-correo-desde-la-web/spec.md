# Spec 110 — Envío de informes por correo (Gmail y Outlook) desde la web

Estado: aprobada · Fecha: 2026-11-14 · Origen: Plan Maestro v1.6, BP-26, y orden del usuario del 2026-11-14:
«haz nuevos spec». G0: `D:/csg/G0_PLAN_MAESTRO/E/E_FILAS_BP.md` (BP-26: no existe).

## Contexto y objetivo
Los informes de factibilidad y de estudio eléctrico se descargan y se envían a mano fuera del conversor, así que no
queda constancia de qué versión salió ni a quién. Esta spec deja enviar desde la web, con la cuenta Gmail u Outlook
del propio operador, el informe cerrado y con huella, o un enlace privado a su expediente (spec 109). Siempre hay
vista previa y confirmación, y queda un recibo.

## Usuarios / actores
- El operador en la web, con su cuenta de Google o de Microsoft (personal, Hotmail o de la empresa).
- El asistente, que solo redacta y propone.

## Historias de usuario
- H1: Como operador, quiero enviar el informe de factibilidad de un cliente desde la web y que quede constancia de qué
  versión se envió y a quién.

## Requisitos funcionales (EARS)
- RF-1: CUANDO el operador elija enviar un informe, EL SISTEMA abrirá una ventana con la cuenta, los destinatarios,
  las copias, el asunto, el cuerpo editable y los adjuntos o el enlace.
- RF-2: EL SISTEMA pedirá al proveedor solo el permiso de enviar correo (`gmail.send` o `Mail.Send`), sin acceso de
  lectura al buzón.
- RF-3: EL SISTEMA adjuntará solo informes cerrados, con su huella, del mismo proyecto y escenario que muestra la
  ventana.
- RF-4: SI el informe o un adjunto cambia entre la vista previa y la confirmación, ENTONCES EL SISTEMA anulará la
  confirmación y pedirá revisarlo otra vez.
- RF-5: EL SISTEMA no enviará ningún correo sin la confirmación del operador, unida a ese contenido y a esos
  destinatarios exactos.
- RF-6: SI el asistente o un documento pide enviar un correo, ENTONCES EL SISTEMA solo preparará el borrador y
  esperará la confirmación en la web.
- RF-7: CUANDO el envío se confirme, EL SISTEMA reservará una clave única del envío antes de llamar al proveedor.
- RF-8: EL SISTEMA guardará el recibo con la clave, el identificador que devuelve el proveedor, el estado, la hora,
  los destinatarios y la huella del informe.
- RF-9: SI el proveedor no responde a tiempo, ENTONCES EL SISTEMA marcará el resultado como desconocido y no
  reenviará el correo solo.
- RF-10: SI se elige enviar un enlace, ENTONCES EL SISTEMA dará primero el acceso a esos destinatarios (109:RF-10) y
  solo después enviará el correo, con un recibo por cada paso.
- RF-11: EL SISTEMA no adjuntará nunca los datos crudos de la distribuidora (TXT, MDB ni el paquete VNR) ni
  credenciales.
- RF-12: SI el informe sale de un estudio bloqueado o fuera de dominio, ENTONCES EL SISTEMA lo dirá en la ventana y
  no lo presentará como un estudio válido.
- RF-13: EL SISTEMA mostrará en la web el historial de envíos de cada informe.
- RF-14: SI una dirección de destino no está entre los contactos habituales del espacio de trabajo, ENTONCES EL
  SISTEMA lo avisará en la ventana junto a esa dirección, sin impedir el envío.

## Requisitos no funcionales
- Las credenciales se guardan como en 109:RF-2.
- Ningún correo ni token aparece en los registros.
- El envío es un trabajo en cola (P7).

## Casos límite
- Doble clic en «Enviar».
- Un timeout después de que el proveedor aceptó el correo.
- Un destinatario mal escrito.
- Un adjunto que supera el límite del proveedor.
- Una cuenta revocada.

## Fuera de alcance
- Leer el buzón.
- Respuestas automáticas.
- Envíos masivos.
- SMTP con contraseña.
- Confirmar la lectura: el recibo del proveedor solo prueba que lo aceptó.

## Criterios de finalización
Cada RF citado por una prueba (`grep "110:RF-"`), con un proveedor simulado y con las pruebas negativas (timeout, doble
envío, cambio del adjunto, orden del asistente). Un envío real controlado a una dirección del usuario, con su recibo.

## Decisiones (2026-11-14)
Tomadas por delegación del usuario (`D:/csg/G0_PLAN_MAESTRO/G1_DECISIONES_RECOMENDADAS.md`, decisiones 1 y 2).
- Destinatarios: no hay una libreta cerrada; vale cualquier dirección. La ventana avisa cuando una dirección no está
  entre los contactos habituales del espacio (RF-14), y el envío sigue necesitando la confirmación de RF-5.
- OAuth: el cliente OAuth es configurable (identificador, secreto y URI de retorno en la configuración local, nunca en
  el repositorio), el mismo de la spec 109. Las pruebas usan un proveedor simulado. La integración real queda
  bloqueada solo por el registro de la aplicación en Google Cloud y en Azure, que hace el usuario con su cuenta,
  con un instructivo paso a paso.
