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
- **Quien tenga sesión en el equipo con ese usuario puede usar el programa y leer sus datos.** Se apoya en la cuenta de Windows y en el cifrado de disco
  que tenga la organización: el programa no cifra los datos.

## Qué sale a la red

Nada por defecto. Cada salida se enciende por separado con su variable, y lo que necesitaría una apagada lo dice.

| Variable | Adónde | Para qué |
| --- | --- | --- |
| `CSG_SALIDA_VNR_OFICIAL` | Portal de Osinergmin | Buscar y descargar paquetes VNR-GIS |
| `CSG_SALIDA_ARCGIS` | El servidor ArcGIS que indique el usuario | Leer una capa |
| `CSG_SALIDA_VIAS` | El enrutador OSRM del perfil | Trazar una línea nueva por la vía pública |
| `CSG_SALIDA_TESELAS` | OpenStreetMap, desde el navegador | Fondo del mapa de la vista previa |
| `CSG_SALIDA_INTERNET` | GitHub, PyPI y arXiv | Búsquedas técnicas del asistente |
| `CSG_SALIDA_HUGGING_FACE` | Hugging Face | Descargar modelos del complemento de IA |
| `CSG_SALIDA_CODEX` | Servicio de Codex | Herramienta de desarrollo; no se entrega |

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
índice. **El instalador no está firmado**: Windows puede avisar al abrirlo. Compruebe que viene de quien se lo entrega.

## Lo que va con el paquete

`THIRD_PARTY_NOTICES.txt` lista cada componente de terceros y sus licencias, y `sbom.cdx.json` es el inventario en CycloneDX. Son inventarios técnicos
generados de los metadatos de cada librería. La licencia comercial del propio programa está pendiente de la asesoría legal.

## Vulnerabilidades conocidas

Cada candidato se comprueba con `pip-audit` contra su lock, antes de entregarlo. Es una foto de esa fecha: lo que se publique después hay que
volver a comprobarlo. El 2026-11-04, con el lock de esta versión: ninguna conocida.
