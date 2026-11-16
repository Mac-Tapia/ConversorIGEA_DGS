# Enviar informes por correo con Gmail o Outlook: el registro OAuth (spec 110)

Para enviar un informe desde la web con su cuenta de Gmail o de Outlook, el programa usa la **misma aplicación OAuth
que la nube** (spec 109, [NUBE_REGISTRO_OAUTH.md](NUBE_REGISTRO_OAUTH.md)). Si ya la registró para Google Drive o
OneDrive, solo hay que añadirle el permiso de enviar correo. El programa no trae ningún cliente: el identificador va en
`config\nube.json` de cada equipo, fuera de git (109:RF-18).

El programa pide **solo el permiso de enviar** (`https://www.googleapis.com/auth/gmail.send` en Google, `Mail.Send` en
Microsoft), y solo cuando el operador conecta la cuenta para enviar. Nunca pide leer el buzón: no ve sus correos, ni los
enviados ni los recibidos.

Sin `config\nube.json`, la ventana de envío dice «Sin cuenta conectada: configure config/nube.json» y no envía nada;
la web y todo lo local siguen igual.

## Versión de prueba: lo que basta para la 1.0

La 1.0 se valida con el proveedor simulado de las pruebas (`tests/correo_simulado.py`). La prueba real con una cuenta
es opcional y la hace el operador cuando registre su aplicación de prueba. No hace falta publicar ni verificar la
aplicación:

- **Google Cloud en modo «Testing»** (pantalla de consentimiento en «Prueba»): hasta 100 usuarios de prueba, que se
  añaden por su correo, sin la verificación de Google. Mientras siga en Testing, Google avisa de que la aplicación no
  está verificada, y el token de refresco caduca a los 7 días: pasado ese plazo, la web pide volver a conectar.
- **Azure con cuentas personales de Microsoft** (outlook.com, hotmail.com, live.com): el mismo registro de la 109, un
  cliente público con PKCE, sin secreto ni aprobación de un administrador.

Pasar a producción (Google verificado o una aplicación de empresa aprobada por su administrador) no cambia nada en el
programa: solo los datos de `config\nube.json`.

## Google Cloud (Gmail)

1. En <https://console.cloud.google.com/>, abra el proyecto de la 109 (o cree uno, por ejemplo «ConverterSmartGrid
   prueba», y siga antes los pasos de Google de [NUBE_REGISTRO_OAUTH.md](NUBE_REGISTRO_OAUTH.md)).
2. «APIs y servicios» → «Biblioteca»: habilite **Gmail API**.
3. «Pantalla de consentimiento de OAuth» (o «Google Auth Platform») → «Acceso a los datos»: añada el permiso
   `https://www.googleapis.com/auth/gmail.send`. No añada `gmail.readonly`, `gmail.modify`, `gmail.compose` ni
   `https://mail.google.com/`.
4. Deje la aplicación en **Testing** y, en «Usuarios de prueba», añada las cuentas que van a enviar.
5. El cliente es el mismo «Aplicación de escritorio» de la 109: no cree otro.

## Azure (Outlook)

1. En <https://portal.azure.com/> → «Microsoft Entra ID» → «Registros de aplicaciones», abra el registro de la 109 (o
   cree uno como dice [NUBE_REGISTRO_OAUTH.md](NUBE_REGISTRO_OAUTH.md), con **cuentas personales de Microsoft**).
2. «Permisos de API» → «Agregar un permiso» → Microsoft Graph → permisos **delegados**: marque **Mail.Send**. Nada más
   de correo: ni `Mail.Read` ni `Mail.ReadWrite`.
3. Con una cuenta de empresa, puede que el administrador tenga que conceder el consentimiento; con una cuenta personal,
   no.
4. No cree ningún secreto: es un cliente público con PKCE.

## Qué va en `config\nube.json`

Nada nuevo: el mismo `id_cliente`, `secreto` (Google), `inquilino` (Microsoft) y `uri_retorno` de la 109
(`http://127.0.0.1:<puerto>/nube/retorno` o `http://localhost:<puerto>/nube/retorno`). El permiso de enviar se pide al
conectar, no se escribe en el fichero.

- La salida a la red de la nube (`CSG_SALIDA_NUBE`) sirve para conectar la cuenta.
- Las salidas del correo, `CSG_SALIDA_CORREO_GOOGLE` y `CSG_SALIDA_CORREO_MICROSOFT`, sirven para enviar. En la
  edición de producto vienen apagadas: se encienden con su variable al arrancar (086:RF-22).

## Conectar y enviar

1. En la web, conecte la cuenta para enviar: el navegador abre la página de Google o de Microsoft, que dice qué permiso
   se da. La contraseña se escribe allí; el programa nunca la ve. El token de refresco lo guarda la 109 cifrado con
   DPAPI de Windows (109:RF-2); el navegador nunca lo ve.
2. En la ventana de envío, revise la vista previa y pulse «Confirmar y enviar». Queda un recibo con la clave, el
   identificador del proveedor, el estado, la hora, los destinatarios y la huella del informe.

## Cómo revocar el permiso

- **En Google**: <https://myaccount.google.com/permissions> → la aplicación → «Quitar acceso».
- **En Microsoft (cuenta personal)**: <https://account.live.com/consent/Manage> → la aplicación → «Quitar estos
  permisos». **Cuenta de empresa**: el administrador, desde «Aplicaciones empresariales» en Microsoft Entra ID.
- Desde la web, «Desconectar» la cuenta borra la credencial del equipo (spec 109). Los recibos de los envíos se
  conservan.

## Prueba real con una cuenta (opcional, la hace el operador)

La prueba con el proveedor simulado valida la 1.0, pero no acredita la integración real. Cuando el operador haya
registrado su aplicación de prueba:

1. Envíe un informe de prueba a una dirección suya, desde la web y con su cuenta.
2. Compruebe que el correo aparece en «Enviados» de esa cuenta.
3. Guarde como evidencia el recibo (`envios\<clave>.json` del espacio) y anótelo en la tarea T12 de
   `specs/110-envio-de-informes-por-correo-desde-la-web/tasks.md`.

## Lo que el correo no hace

- No lee el buzón ni confirma la lectura: el recibo solo prueba que el proveedor aceptó el correo.
- No reenvía nunca solo: si el resultado es desconocido, la web pide mirar «Enviados» de la cuenta y decir si llegó.
- No adjunta nunca los datos de la distribuidora (TXT, MDB ni el paquete VNR) ni credenciales.
