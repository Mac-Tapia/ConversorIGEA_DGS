# Spec 109 — Fuentes y expedientes en la nube (Google Drive y OneDrive) desde la web

Estado: aprobada · Fecha: 2026-11-14 · Origen: Plan Maestro v1.6, BP-23, BP-24 y BP-25, y orden del usuario del
2026-11-14: «haz nuevos spec»; autorización del Drive propio del usuario (constitución, principio 9, enmienda del
2026-11-14). G0: `D:/csg/G0_PLAN_MAESTRO/E/MATRIZ_CLOUD_PERMISOS_Y_FORMATOS.md`.

## Contexto y objetivo
Hoy Drive solo se usa como una carpeta local más (086:RF-78 a RF-85, 105:RF-28 a RF-33). G0 comprobó que no hay
ninguna integración por API con Google Drive ni con OneDrive. El operador quiere hacer tres cosas desde la web, sin
copiar ficheros a mano:
- elegir en su nube los libros de medición, los paquetes VNR, los planos y los costos;
- enterarse de que alguno cambió;
- subir los expedientes (corto plazo, PIDE, largo plazo, PIT y VAD) y compartirlos con destinatarios concretos.

Cada estudio se calcula siempre sobre una **copia fija con su huella**, nunca sobre el fichero remoto, que puede
cambiar.

## Usuarios / actores
El operador o ingeniero en la web, con su propia cuenta de Google o de Microsoft (personal o de la empresa).

## Historias de usuario
- H1: Como operador, quiero elegir uno o varios ficheros de mi Drive o de mi OneDrive y que entren como si los hubiera
  subido desde el equipo.
- H2: Como operador, quiero saber cuándo un fichero vinculado cambió, compararlo y decidir si lo vuelvo a importar.
- H3: Como operador, quiero publicar un expediente en una carpeta de mi nube y compartirlo en solo lectura con personas
  concretas.

## Requisitos funcionales (EARS)
- RF-1: CUANDO el operador conecte una cuenta de Google o de Microsoft, EL SISTEMA pedirá solo los permisos de la tarea
  (los ficheros elegidos para leer y la carpeta elegida para publicar), con el flujo de autorización del proveedor, y
  nunca pedirá ni guardará la contraseña.
- RF-2: EL SISTEMA guardará las credenciales del proveedor cifradas, por usuario y por espacio de trabajo, y nunca en
  el espacio de trabajo, en el navegador, en los registros ni en el repositorio.
- RF-3: CUANDO el operador elija ficheros de la nube, EL SISTEMA los descargará en un trabajo en cola y guardará una
  copia inmutable con su huella SHA-256, el proveedor, el identificador y la revisión.
- RF-4: EL SISTEMA dará a un fichero importado de la nube el mismo tratamiento que a uno subido desde el equipo: el
  mismo lector, la misma validación y el mismo registro de la fuente.
- RF-5: SI el fichero es una hoja de cálculo nativa del proveedor, ENTONCES EL SISTEMA la exportará a un formato
  explícito y anotará el formato de origen y el exportado.
- RF-6: SI la descarga se corta, el permiso caduca o el fichero cambia a mitad, ENTONCES EL SISTEMA no dará la copia
  por válida y dirá la causa.
- RF-7: CUANDO cambie la revisión de un fichero vinculado, EL SISTEMA avisará al operador y le dejará comparar la
  versión nueva con la anterior.
- RF-8: EL SISTEMA no cambiará ningún estudio, dataset ni calibración hechos con la versión anterior cuando llegue una
  nueva; la nueva entra solo con la confirmación del operador.
- RF-9: CUANDO el operador publique un expediente, EL SISTEMA subirá el paquete cerrado con su manifiesto de huellas
  a la carpeta elegida, sin sobrescribir lo que ya hay.
- RF-10: CUANDO el operador comparta un expediente, EL SISTEMA dará acceso de solo lectura a los destinatarios que
  nombre, después de mostrarle quién tendrá acceso.
- RF-11: SI una publicación o un permiso pidiera acceso de «cualquiera con el enlace», ENTONCES EL SISTEMA lo
  rechazará, salvo que el operador lo autorice de forma explícita en ese envío.
- RF-12: EL SISTEMA guardará un recibo por cada publicación y cada permiso concedido, con el paquete, el destino, los
  destinatarios, la hora y el identificador remoto.
- RF-13: SI un reintento encuentra una publicación con la misma clave ya hecha, ENTONCES EL SISTEMA devolverá su
  recibo en vez de subirla otra vez.
- RF-14: CUANDO el operador desconecte una cuenta, EL SISTEMA revocará el acceso y conservará las copias ya
  importadas y sus recibos.
- RF-15: EL SISTEMA nunca dejará que el asistente ni un documento importado publique, comparta ni conecte cuentas sin
  la confirmación del operador en la web.
- RF-16: EL SISTEMA solo contactará los hosts de los proveedores registrados y no seguirá redirecciones a otros
  hosts.
- RF-17: MIENTRAS no haya conexión, EL SISTEMA seguirá funcionando con las copias ya importadas y dirá que no pudo
  comprobar si hay versiones nuevas.
- RF-18: EL SISTEMA leerá el cliente OAuth de cada proveedor (identificador, secreto si lo hay y URI de retorno) de la
  configuración local del equipo, fuera del repositorio.
- RF-19: SI falta el cliente OAuth de un proveedor, ENTONCES EL SISTEMA dirá que falta registrar la aplicación y no
  ofrecerá conectar ese proveedor, sin afectar a lo local.
- RF-20: SI un expediente que se va a compartir con destinatarios contiene datos crudos de la distribuidora (TXT de
  CYMDIST, bases Access o paquetes VNR-GIS), ENTONCES EL SISTEMA no concederá el permiso y nombrará los ficheros que lo
  impiden.

## Requisitos no funcionales
- Lo local sigue funcionando sin cuenta y sin red: sin regresión en las entradas actuales.
- Ficheros grandes: la descarga y la subida se pueden reanudar, con un tope de bytes y de descompresión.
- Universal: cualquier cuenta, cualquier empresa. Ninguna carpeta fija en el código.

## Casos límite
- Un archivo compartido de solo lectura.
- Paginación con cientos de ficheros.
- Errores 401, 403, 404 y 429.
- Un token revocado a mitad.
- Un paquete VNR comprimido con rutas maliciosas.
- Un PDF normativo que no es medición.
- Dos empresas en el mismo puesto.

## Fuera de alcance
- La sincronización automática que reentrene o recalcule sin confirmación.
- Nextcloud y otros proveedores, que van en una iteración posterior si se piden.
- Subir los datos crudos de la distribuidora a destinatarios de terceros.

## Criterios de finalización
Cada RF citado por una prueba (`grep "109:RF-"`), con un proveedor simulado y con las pruebas negativas de la lista de
casos límite. Una prueba real controlada, en una carpeta de ensayo del usuario, importa y publica, con sus recibos.
La prueba con el proveedor simulado no acredita la integración real.

## Decisiones (2026-11-14)
Tomadas por el implementador por delegación del usuario (`D:/csg/G0_PLAN_MAESTRO/G1_DECISIONES_RECOMENDADAS.md`,
puntos 1 y 2).
- **Registro de la aplicación OAuth.** Lo hace el usuario, con su cuenta, en Google Cloud y en Azure. El cliente OAuth
  es configurable: identificador, secreto y URI de retorno van en la configuración local del equipo y nunca en el
  repositorio (RF-18); sin él, la web dice que falta el registro (RF-19). Las pruebas usan un proveedor simulado. La integración real queda bloqueada solo por ese
  registro, y se deja un instructivo paso a paso en `docs/`.
- **Compartir con terceros.** Sí entra en la enmienda del principio 9, pero solo con destinatarios nombrados, en solo
  lectura y con la confirmación del operador en cada envío (RF-10, RF-15). Nunca se comparte con «cualquiera con el
  enlace» salvo que el operador lo autorice en ese envío (RF-11). Nunca se comparten datos crudos: TXT, MDB ni paquetes
  VNR-GIS (RF-20).
