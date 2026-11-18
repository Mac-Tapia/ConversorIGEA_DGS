# Hoja de seguridad y privacidad de ConverterSmartGrid

Para el responsable de sistemas o de datos de la distribuidora. Describe lo que hace la versión 1.0, tal como está en el código. No es una
opinión legal ni una certificación: no ha pasado una auditoría externa.

## Dónde corre

- Un puesto local, para un operador. **No hay usuarios ni multiusuario.**
- La web escucha solo en `127.0.0.1`. Pedir otra dirección se rechaza, y dice por qué: sin usuarios ni TLS, cualquiera en esa red podría
  usarla y leer los datos.
- Se rechaza un `Host` ajeno; lo que cambia algo y el WebSocket exigen un `Origin` propio; toda la API exige un token que el lanzador da en cada
  arranque y que se guarda en la carpeta de sesión del usuario.
- Las páginas se sirven con una política de contenido y con su propio Leaflet.
- **Marcos.** Ninguna página de la web se deja enmarcar por otra (`X-Frame-Options: DENY` y `frame-ancestors 'none'`), salvo dos
  que la propia interfaz muestra dentro de su pantalla: el mapa de «Ubicación de las cargas nuevas» y la vista previa del alimentador.
  Esas dos, y solo cuando se abren como página aislada (no como descarga ni como error), llevan `X-Frame-Options: SAMEORIGIN` y
  `frame-ancestors 'self'`: solo esta misma web las puede enmarcar. Lo decide la puerta de la web en toda respuesta, no cada ruta;
  la lista de las dos rutas está en el código, por su nombre, y una prueba recorre todas las demás rutas para que ninguna se deje
  enmarcar. Lo que rechaza la puerta (sin sesión, otro `Host` u `Origin`) y la entrada con el enlace del lanzador tampoco.
- **Las páginas de los mapas van aisladas** (`sandbox`, sin acceso a la API ni a las cookies) y no piden nada de fuera salvo el fondo
  del mapa, cuando su salida está encendida: imágenes de `https://a.tile.openstreetmap.org`, `https://b.tile.openstreetmap.org` y
  `https://c.tile.openstreetmap.org` (calles) y de `https://server.arcgisonline.com` (satélite). La política nombra esos servidores,
  sin comodín; con la salida apagada solo admite imágenes incrustadas. Si una de esas páginas llegara sin `sandbox`, no se deja
  enmarcar.
- **Por qué la vista previa abre más que un mapa.** La vista previa del alimentador se sirve por la ruta de los ficheros del
  espacio de trabajo, así que esa ruta deja enmarcar, por esta misma web, cualquier página HTML del espacio, no solo la vista previa.
  Se admite porque esas respuestas van con la política `sandbox allow-scripts` y `default-src 'none'`, sin `connect-src`: la página
  enmarcada no llega a la API ni a las cookies. Una descarga, un fichero que no es HTML, uno que no existe o un error siguen sin
  dejarse enmarcar.
- **Quien tenga sesión en el equipo con ese usuario puede usar el programa y leer sus datos.** Se apoya en la cuenta de Windows y en el cifrado de disco
  que tenga la organización: el programa no cifra los datos.

## Qué sale a la red

Nada por defecto. Cada salida se enciende por separado con su variable, y lo que necesitaría una apagada lo dice.

| Variable | Adónde | Para qué |
| --- | --- | --- |
| `CSG_SALIDA_VNR_OFICIAL` | Portal de Osinergmin | Buscar y descargar paquetes VNR-GIS |
| `CSG_SALIDA_ARCGIS` | El servidor ArcGIS que indique el usuario | Leer una capa |
| `CSG_SALIDA_VIAS` | El enrutador OSRM del perfil | Trazar una línea nueva por la vía pública |
| `CSG_SALIDA_TESELAS` | OpenStreetMap y Esri World Imagery, desde el navegador | Fondo de los mapas (calles y satélite) |
| `CSG_SALIDA_INTERNET` | GitHub, PyPI y arXiv | Búsquedas técnicas del asistente |
| `CSG_SALIDA_HUGGING_FACE` | Hugging Face | Descargar modelos del complemento de IA |
| `CSG_SALIDA_CODEX` | Servicio de Codex | Herramienta de desarrollo; no se entrega |
| `CSG_SALIDA_CORREO_GOOGLE` | La API de Gmail | Enviar un informe con la cuenta de Google del operador, solo con el permiso de enviar |
| `CSG_SALIDA_CORREO_MICROSOFT` | Microsoft Graph | Enviar un informe con la cuenta de Microsoft del operador, solo con el permiso de enviar |
| `CSG_SALIDA_NUBE` | Google Drive y OneDrive de la cuenta que conecte el operador | Importar fuentes y publicar o compartir expedientes (spec 109); la web la muestra, pero no la cambia |

Instalar no sale a internet y arrancar nunca instala nada. No hay telemetría ni comprobación de actualizaciones.

## Qué datos guarda

Todo en la carpeta de datos del usuario (`%LOCALAPPDATA%\ConverterSmartGrid\datos`, o la de `CSG_DATOS_HOME`):

| Qué | Contenido |
| --- | --- |
| Espacios de trabajo | Rutas de las entradas, resultados, DGS e informes |
| `config\` | Perfil y alias de la empresa |
| `input\` | Catálogos de parámetros, con las fichas del operador |
| `runtime\registros\` | Registro del programa, en ficheros rotativos |
| `copias_actualizacion\` | La copia previa de cada actualización |
| `secretos\nube\` | Credenciales cifradas de la nube (DPAPI), por espacio; fuera de las copias de los datos |

### La nube del operador (spec 109)

- Solo sale a `www.googleapis.com`, `oauth2.googleapis.com`, `graph.microsoft.com`, `login.microsoftonline.com`,
  `api.onedrive.com`, `*.sharepoint.com` y `*.1drv.com`, por un único módulo (`adaptadores/nube/http.py`), sin proxy del
  entorno y sin seguir redirecciones.
- El cliente OAuth lo registra la organización (`docs/NUBE_REGISTRO_OAUTH.md`) y va en `config\nube.json`, fuera del
  repositorio. Sin él la nube no se ofrece. La contraseña se escribe en la página del proveedor; el programa nunca la ve.
- Permisos mínimos: en Google, `drive.file` (solo lo que el operador elige o lo que el programa publica); en Microsoft,
  `Files.Read` y `Files.ReadWrite` solo para publicar.
- El token de refresco va cifrado con DPAPI de Windows (ámbito del usuario, con la entropía del espacio y del proveedor) en
  `secretos\nube\<espacio>\`. No entra en el espacio de trabajo, en `config\`, en el navegador, en los registros ni en las
  copias de los datos. Una copia restaurada en otro equipo no trae credenciales: se vuelve a conectar.
- Cada estudio usa una copia fija de lo importado, con su huella (`nube\copias\<sha256>\copia.json`).
- Compartir exige la previa de quién tendrá acceso y la confirmación del operador en cada envío; solo lectura, a correos
  concretos; «cualquiera con el enlace» solo con su autorización expresa; y nunca un expediente con TXT, bases
  Access o paquetes VNR-GIS, que se reconocen por su contenido. El asistente no puede conectar, publicar ni compartir.
- Desconectar revoca en Google y borra la credencial del equipo; en Microsoft se retira el consentimiento desde la cuenta.

Las redes, las demandas y los informes son datos de la distribuidora. El programa los lee donde se indiquen y no los envía a ningún sitio. Una ejecución de
retención diaria limpia temporales; no borra informes ni espacios. Desinstalar no borra los datos: es decisión de la organización.

## Paquete de soporte

`csg.cmd soporte` lo arma en local y **no lo envía**. Se construye con una lista cerrada: diagnóstico, versiones, claves del perfil sin sus
valores, y registros con las rutas, correos, IP, usuario y equipo, textos del perfil, textos entre comillas y códigos de red sustituidos. La
sustitución es automática y por patrones: **revíselo antes de enviarlo**, porque un nombre sin comillas ni forma de código podría quedar.

## Procesos, licencias y permisos

- Sin administrador, salvo los drivers externos.
- Los guiones de DIgSILENT corren con el Python del programa, en procesos hijos, con la licencia y los permisos del usuario. Las tareas del asistente que usan licencia o
  salen a la red piden confirmación, igual que ejecutar un guion guardado en un proyecto.
- Un módulo externo solo se carga si figura en `config\modulos_permitidos.json`.

## Integridad

Cada fichero del paquete lleva su huella SHA-256 en el manifiesto y se comprueba antes de instalar. Las librerías se instalan con `--require-hashes`, sin
índice. El instalador va firmado con el certificado del editor, y `SHA256SUMS`, que llega por otro canal que el instalador, da la
huella de cada fichero de la entrega: compruebe las dos antes de instalar. No ejecute un instalador sin firma.

## Lo que va con el paquete

`THIRD_PARTY_NOTICES.txt` lista cada componente de terceros y sus licencias, y `sbom.cdx.json` es el inventario en CycloneDX. Son inventarios técnicos
generados de los metadatos de cada librería. El programa se distribuye bajo la licencia MIT, `LICENSE.txt`; el acuerdo comercial de soporte y garantía,
`LICENCIA_COMERCIAL.txt`, es opcional.

## Vulnerabilidades conocidas

Cada candidato final se comprueba con `pip-audit` contra su lock al armarlo, y no se arma con una vulnerabilidad sin justificar por
escrito; el resultado, con su fecha, va en `auditoria_dependencias.json` junto a este documento. Es una foto de esa fecha: lo que se publique
después hay que volver a comprobarlo. El 2026-11-14, con el lock de esta versión: 58 librerías, ninguna vulnerabilidad conocida. El
intérprete es el Python 3.12.10 oficial de python.org, firmado por la Python Software Foundation.
