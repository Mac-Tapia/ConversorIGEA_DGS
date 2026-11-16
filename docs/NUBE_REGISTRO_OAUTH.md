# Registrar la aplicación de Google Drive y de OneDrive (spec 109)

Para importar ficheros de la nube y publicar o compartir expedientes desde la web, la organización registra su propia
aplicación OAuth en Google Cloud, en Azure o en los dos, con su cuenta. El programa no trae ningún cliente: el
identificador va en `config\nube.json` de cada equipo, que no entra en el repositorio (109:RF-18). Sin ese fichero, la
web dice «Sin cuenta conectada: configure config/nube.json» y no ofrece conectar; todo lo local sigue igual (109:RF-19).

La contraseña de la cuenta se escribe siempre en la página de Google o de Microsoft. El programa nunca la ve ni la guarda.

## Versión de prueba: lo que basta para la 1.0

La 1.0 se valida con el proveedor simulado de las pruebas (`tests/nube_simulada.py`). La prueba real con una cuenta es
opcional y la hace el operador cuando registre su aplicación de prueba. Para eso no hace falta publicar ni verificar la
aplicación:

- **Google Cloud en modo «Testing»** (pantalla de consentimiento en «Prueba»): admite hasta 100 usuarios de prueba, que
  se añaden por su correo, y no pide la verificación de Google. El token de refresco de una aplicación en «Testing»
  caduca a los 7 días: pasado ese plazo, la web pide volver a conectar la cuenta.
- **Azure con cuentas personales**: un registro de aplicación que admite cuentas personales de Microsoft (outlook.com,
  hotmail.com, live.com) es un cliente público con PKCE; no necesita secreto ni la aprobación de un administrador.

Pasar a producción (Google verificado o una aplicación de empresa aprobada por su administrador) no cambia nada en el
programa: solo los datos de `config\nube.json`.

## Antes de empezar

- El puerto de la web. La URI de retorno es `http://127.0.0.1:<puerto>/nube/retorno` (Google) o
  `http://localhost:<puerto>/nube/retorno` (Microsoft), con el puerto donde escucha la web en este equipo (el que abre el
  lanzador; por ejemplo 8765). Se escribe en `config\nube.json` tal cual.
- Una carpeta de ensayo propia en la nube para la primera prueba, sin datos de la distribuidora.

## Google Cloud (Google Drive)

1. En <https://console.cloud.google.com/>, cree un proyecto, por ejemplo «ConverterSmartGrid prueba».
2. «APIs y servicios» → «Biblioteca»: habilite **Google Drive API** y **Google Picker API**.
3. «Pantalla de consentimiento de OAuth» (o «Google Auth Platform»):
   - tipo de usuario **Externo** (o **Interno** si la cuenta es de Google Workspace y solo la usa su organización);
   - deje la aplicación en **Testing** (modo de prueba) y, en «Usuarios de prueba», añada los correos de las cuentas que
     la van a usar (hasta 100 usuarios de prueba);
   - permisos: `openid`, `email` y `https://www.googleapis.com/auth/drive.file`. Nada más.

   Con `drive.file` el programa solo ve los ficheros que el operador elige en el selector y los que el propio programa
   publica. Mientras siga en Testing, Google avisa en la ventana de conexión de que la aplicación no está verificada:
   es lo esperado en la versión de prueba.
4. «Credenciales» → «Crear credenciales» → «ID de cliente de OAuth» → tipo **Aplicación de escritorio**. Google da un
   identificador (`…apps.googleusercontent.com`) y un secreto. En una aplicación de escritorio ese secreto no es
   confidencial, pero tampoco se sube al repositorio.

## Azure (OneDrive)

1. En <https://portal.azure.com/> → «Microsoft Entra ID» → «Registros de aplicaciones» → «Nuevo registro».
2. Cuentas admitidas: para la versión de prueba, **cuentas personales de Microsoft** («Solo cuentas personales de
   Microsoft», o «Cuentas de cualquier directorio organizativo y cuentas personales de Microsoft» si también se probará
   con una cuenta de empresa).
3. «Autenticación» → «Agregar una plataforma» → **Aplicaciones móviles y de escritorio**, con la URI de redirección
   `http://localhost`. Active «Permitir flujos de cliente público».
4. «Permisos de API» → Microsoft Graph → permisos **delegados**: `Files.Read`, `Files.ReadWrite`, `offline_access`,
   `openid` y `email`. El programa pide `Files.Read` al conectar y `Files.ReadWrite` solo cuando el operador conecta para
   publicar. Microsoft Graph no tiene un permiso por fichero: la ventana de conexión lo dice.
5. Copie el **Id. de aplicación (cliente)**. No cree ningún secreto: es un cliente público con PKCE.

## Qué va en `config\nube.json`

Copie `config\nube.example.json` como `config\nube.json` y ponga sus datos. Quite el bloque del proveedor que no use.

```json
{
  "google": {
    "id_cliente": "1234567890-abcdefg.apps.googleusercontent.com",
    "secreto": "el que dio Google al cliente de escritorio",
    "uri_retorno": "http://127.0.0.1:8765/nube/retorno"
  },
  "microsoft": {
    "id_cliente": "00000000-0000-0000-0000-000000000000",
    "inquilino": "consumers",
    "uri_retorno": "http://localhost:8765/nube/retorno"
  }
}
```

- `inquilino`: `consumers` para un registro solo de cuentas personales; `common` para cuentas personales y de empresa;
  `organizations` solo de empresa; o el identificador del directorio de su organización.
- `clave_api` e `id_aplicacion` (Google): la clave de API («Credenciales» → «Crear credenciales» → «Clave de API»,
  restringida a Google Picker API y a `http://127.0.0.1`) y el número del proyecto. Las usa el selector de ficheros y
  son públicas por diseño. El selector recibe además un token de acceso de menos de una hora y solo de lectura, que
  pide cada vez que se abre y no guarda; nunca el de refresco ni el secreto (aclaración de 109:RF-2).
- `url_selector` (Microsoft): vacío para OneDrive personal; para OneDrive de empresa, la dirección del selector de
  SharePoint del inquilino (`https://<empresa>-my.sharepoint.com/_layouts/15/FilePicker.aspx`).
- La URI de retorno tiene que ser de esta máquina (`127.0.0.1` o `localhost`) y terminar en `/nube/retorno`; si no, la web
  no ofrece conectar y dice por qué.
- Instalado, el fichero va en la carpeta de datos (`%LOCALAPPDATA%\ConverterSmartGrid\datos\config\nube.json`); en
  desarrollo, en `config\` del repositorio. `CSG_NUBE_CONFIG` permite otra ruta.
- La salida a la red `CSG_SALIDA_NUBE` tiene que estar encendida (en la edición de producto viene apagada); se enciende
  con la variable o desde la web.

## Dónde quedan las credenciales

Al conectar, el programa guarda solo el token de refresco, cifrado con DPAPI de Windows para este usuario, en
`secretos\nube\<espacio>\` (fuera de los espacios de trabajo y de las copias de los datos). Cada espacio de trabajo tiene
su propia cuenta conectada. Una copia de los datos restaurada en otro equipo no trae credenciales: se vuelve a conectar.

## Cómo revocar el acceso

- **Desde la web**: «Desconectar» en la cuenta. Con Google, el programa revoca el token en el proveedor y borra la
  credencial del equipo. Con Microsoft, borra la credencial del equipo (Microsoft no ofrece una revocación estándar
  para estas aplicaciones). En los dos casos, las copias ya importadas y los recibos se conservan.
- **En Google**: <https://myaccount.google.com/permissions> → la aplicación → «Quitar acceso».
- **En Microsoft (cuenta personal)**: <https://account.live.com/consent/Manage> → la aplicación → «Quitar estos permisos».
  **Cuenta de empresa**: <https://myapps.microsoft.com> → «Administrar aplicaciones», o el administrador desde
  «Aplicaciones empresariales» en Microsoft Entra ID.
- Para retirarlo del todo, borre el cliente en Google Cloud o el registro en Azure.

## Prueba real con una cuenta (opcional, la hace el operador)

La prueba con el proveedor simulado valida la 1.0, pero no acredita la integración real. Cuando el operador haya
registrado su aplicación de prueba:

1. Conecte la cuenta desde la web y elija un fichero de la carpeta de ensayo; compruebe que queda la copia con su huella
   en `nube\copias\<sha256>\copia.json` del espacio.
2. Publique un expediente de prueba en la carpeta de ensayo y compártalo en solo lectura con una cuenta propia.
3. Guarde como evidencia `nube\recibos\` (el de la publicación y el del permiso) y anote la carpeta en la tarea T16 de
   `specs/109-fuentes-y-expedientes-en-la-nube-desde-la-web/tasks.md`.
