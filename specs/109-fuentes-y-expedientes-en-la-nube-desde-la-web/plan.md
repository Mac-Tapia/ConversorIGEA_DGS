# Plan — Spec 109

Lee: `docs/constitution.md` (P9 con la enmienda del 2026-11-14) y `specs/109-fuentes-y-expedientes-en-la-nube-desde-la-web/spec.md`.
Contexto de G0, sin rehacerlo: `D:/csg/G0_PLAN_MAESTRO/E/MATRIZ_CLOUD_PERMISOS_Y_FORMATOS.md`, `E/THREAT_MODEL_AGENT.md`
(T1, T3, T9, T10, T12, T16), `E/E_FILAS_BP.md` (BP-23 a BP-25) y `A/G0_CONTRATOS_API_DATOS.md`. Base leída:
`trabajo/puerta-por-ramas@51895566`.

## Contexto técnico

Hoy no hay ninguna integración por API con Google ni con Microsoft. Drive solo entra como una carpeta local más. Esta
spec añade dos adaptadores HTTP, uno por proveedor, detrás de un contrato común, y una entrada y una salida que **llaman
a lo que ya existe**:

| Se reutiliza (código leído) | Para qué en la 109 |
| --- | --- |
| `web/app.py`: `_validar_entrada`, `_assign` y `_reemplazar_carpeta`, más las rutas de `demanda_subir` y de las entradas de estudios (`registrar_rutas_entradas(..., guardar_subida=_save_upload)`) | RF-4: la copia descargada entra por la misma validación y la misma asignación que una subida. Se inyectan en el router nuevo como funciones; no se copia su lógica (P5) |
| `web/workspace.py`: `Workspace.set_input`, `upload_target`, `lock`, `root` e `invalidate` | La copia queda en el espacio y la casilla apunta a ella. `_drop_upload` solo borra lo de `origin='upload'`, así que la copia de la nube nunca se borra al cambiar de casilla (RF-8, RF-14) |
| `web/source_runs.py`: `create_source_run`, `verify_source_files` y `SourceIntegrityError` | La conversión sigue custodiando la entrada con SHA-256 en `runs/<run_id>/originales`. La copia de la nube es una entrada más; la custodia no cambia |
| `web/jobs.py`: `JobManager.submit(..., lane='engine')`, `JobContext.progress` y `check_cancel`, y `EventLog.since` | Descargar, comprobar versiones, publicar y compartir son trabajos con progreso por WebSocket y cancelables (P7) |
| `web/operaciones_lentas.py`: `presupuesto()` y `preparar_zip()` | Topes de bytes (`CSG_NUBE_MAX_BYTES`) y paquete cerrado del expediente, con la misma exclusión de redirecciones y la misma cuota |
| `runtime_paths.staging_publicacion`, `util.publicar_duradero` | Copia, vínculo y recibo se escriben de forma atómica: nunca a medias (P6) |
| `adaptadores/fuentes_estables.abrir_fuente_estable` (vía `source_runs`) | La huella de la copia local se recalcula al reabrirla |
| `adaptadores/entrada/vnr/pipeline.safe_extract_package` y `discovery/download.safe_extract_zip` (**solo lectura, no se tocan**) | Un paquete VNR de la nube se valida con `validate_vnr_package_file` desde `_validar_entrada`; las rutas maliciosas las rechaza el mismo extractor que hoy |
| `identify.fuente_de` | RF-20: reconoce por su contenido un TXT, una base Access o un paquete VNR dentro del expediente |
| `salidas_red.py`: `SALIDAS`, `exigir_salida`, `motivo_apagada`, `CAMBIABLES_DESDE_LA_WEB` | Una salida nueva, `nube`, con su variable `CSG_SALIDA_NUBE`, apagada en la edición de producto (086:RF-22). `tests/test_seguridad_web.py` ya falla si un módulo abre la red sin figurar ahí |
| `web/seguridad.py` (086:RF-17 a RF-20) | Host local, `Origin` propio, token y cabeceras. La ruta de retorno de OAuth va fuera de `/api/` (ver Decisiones), así que el middleware no cambia |
| `asistente/equipo.py`: `autorizar_peticion` | RF-15: el asistente no puede pedir ninguna ruta de la nube, ni con un plan confirmado |
| `archivo_informes.py` | Patrón de configuración local por máquina (`config/archivo.json`) y de reintentos ante bloqueos; **no** se usa para publicar: archivar sigue siendo local |
| `web/copia_datos.py`: `raices_de_datos` | Se comprueba que los secretos quedan fuera de sus raíces y nunca viajan en una copia a Drive (RF-2) |

**No se modifican** `web/services.py`, `pide_economia.py`, `adaptadores/entrada/vnr/**` ni `catalog_resolution.py`, que
son del integrador f9. El cableado en `web/app.py` es **mínimo y pactado con el integrador**: dos líneas al final de
`create_app`, como `registrar_rutas_copia`, más el valor `'nube'` en el `Literal` de `origin` de `api_contract.py`.

Carril de trabajos: `engine`. Importar cambia las entradas del espacio, y publicar lee las salidas: los dos se
bloquean con una conversión, como una subida. Datos: nada del dataset ni de sus índices; la 109 no toca el lector.

## Diseño por partes

| Parte | Ficheros (nuevos salvo que se diga) | Cubre |
| --- | --- | --- |
| Contrato de proveedor | `src/convertersmartgrid/adaptadores/nube/__init__.py`, `adaptadores/nube/proveedor.py`: `ProveedorNube` (Protocol: `metadatos`, `listar` paginado, `descargar` por rangos, `exportar`, `subir` reanudable, `conceder_lectura`, `revocar`) y errores tipados (`SinAcceso` 403, `NoEncontrado` 404, `PermisoCaducado` 401 o `invalid_grant`, `Limitado` 429 con `Retry-After`, `CambioAMitad`, `HostNoPermitido`) | RF-6, RF-16 |
| Transporte | `adaptadores/nube/http.py`: sesión de `requests` con `trust_env=False` y `allow_redirects=False`; cada URL, también `@odata.nextLink`, `@microsoft.graph.downloadUrl` y la URL de una sesión de subida, se compara con los hosts del proveedor antes de pedirla; reintentos con espera solo para 429 y 5xx; tope de bytes | RF-16, RF-6 |
| OAuth | `adaptadores/nube/oauth.py`: código de autorización con PKCE (S256) y `state` de un solo uso, ligado al espacio, que caduca a los 10 min; intercambio y refresco del token; revocación. `config/nube.json` local (en `.gitignore`), con ejemplo `config/nube.example.json` | RF-1, RF-14, RF-18, RF-19 |
| Google Drive | `adaptadores/nube/google_drive.py`: Drive API v3 por REST. `files.get` con `headRevisionId`, `version`, `md5Checksum`, `sha256Checksum` y `size`; `alt=media` con `Range`; `files.export` de las hojas nativas a XLSX; subida `uploadType=resumable`; `permissions.create` con `role=reader`, `type=user` | RF-3, RF-5, RF-7, RF-9, RF-10 |
| OneDrive | `adaptadores/nube/onedrive.py`: Microsoft Graph v1.0 por REST. `driveItem` con `eTag`, `cTag` y `file.hashes`; descarga por `@microsoft.graph.downloadUrl` validado; `createUploadSession` con `@microsoft.graph.conflictBehavior=fail`; `POST /items/{id}/invite` con `roles=["read"]`, `requireSignIn=true` | RF-3, RF-7, RF-9, RF-10 |
| Cofre de secretos | `src/convertersmartgrid/adaptadores/nube_cofre.py`: DPAPI de Windows por `ctypes` (`CryptProtectData` y `CryptUnprotectData`, ámbito del usuario), con la entropía del espacio y del proveedor. Fichero por espacio y cuenta en `raiz_local()/secretos/nube/<wid>/<proveedor>-<huella de la cuenta>.dpapi`. Solo guarda el token de refresco; el de acceso vive en memoria | RF-2, RF-14 |
| Entrada de la nube | `src/convertersmartgrid/adaptadores/entrada/nube.py`: `importar(proveedor, item, destino_local, ctx)` descarga en `staging_publicacion`, comprueba la revisión antes y después y la huella del proveedor si la da, y publica en `ws.root/nube/copias/<sha256>/<nombre>` con `copia.json` (proveedor, id, revisión, formato de origen y exportado, SHA-256, tamaño, hora). Nunca reescribe una copia | RF-3, RF-5, RF-6 |
| Vínculos y versiones | `src/convertersmartgrid/presentacion/web/nube.py`: `ws.root/nube/vinculos.json` (casilla o libro, proveedor, id, revisión importada y copia); `comprobar_versiones` como trabajo; comparar la copia vigente con la nueva (tamaño, huella, fecha y, para TXT y libros, el diff resumido que ya da su lector); aceptar la nueva solo con la confirmación | RF-7, RF-8, RF-17 |
| Salida de la nube | `src/convertersmartgrid/adaptadores/salida/__init__.py`, `adaptadores/salida/nube.py`: `cerrar_paquete` sobre `preparar_zip` con `manifiesto.json` (SHA-256 de cada fichero y del ZIP); `publicar` con clave de idempotencia `sha256(zip) + proveedor + carpeta`; comprobar por `appProperties` (Google) o por el 409 de `conflictBehavior=fail` (Graph) si la subida ya se hizo; recibos en `ws.root/nube/recibos/<clave>.json`; filtro de datos crudos con `identify.fuente_de` | RF-9, RF-11, RF-12, RF-13, RF-20 |
| Permisos | `adaptadores/salida/nube.py`: `previsualizar_permiso` devuelve quién tendrá acceso y una confirmación de un solo uso (5 min, ligada al espacio, al paquete y a la lista de destinatarios); `conceder` la exige, y rechaza `anyone` o un enlace anónimo salvo que el envío lleve `autorizo_enlace_publico=true` | RF-10, RF-11, RF-12, RF-15 |
| API web | `src/convertersmartgrid/presentacion/web/nube_api.py`: `registrar_rutas_nube(app, *, ws_or_404, submit, asignar_entrada, reemplazar_libros, rutas_locales)`. Rutas: `GET /api/nube/proveedores`, `POST /api/workspaces/{wid}/nube/{proveedor}/conectar` (devuelve la URL de autorización), `GET /nube/retorno` (fuera de `/api/`), `DELETE /api/workspaces/{wid}/nube/{proveedor}`, `POST …/nube/importar` (202), `POST …/nube/versiones` (202), `POST …/nube/vinculos/{id}/aceptar`, `POST …/nube/publicar/previa`, `POST …/nube/publicar` (202), `POST …/nube/compartir/previa`, `POST …/nube/compartir` (202), `GET …/nube/recibos`. Contratos en `web/api_contract.py`. Cableado en `web/app.py`: dos líneas, pactadas con f9 | RF-1, RF-4, RF-14, RF-15, RF-19 |
| Selector de ficheros | `GET /nube/selector/{proveedor}`: página propia con su `Content-Security-Policy` (el middleware respeta la que ya trae la respuesta), que solo admite el script del selector del proveedor (Google Picker, File Picker v8 de OneDrive). Devuelve a la web los ids elegidos por `postMessage` con el origen comprobado | RF-1, RF-3 |
| Salida declarada | `salidas_red.py` (se amplía): `'nube'` con `CSG_SALIDA_NUBE`, sus módulos y `CAMBIABLES_DESDE_LA_WEB` | RF-16, RF-17 |
| Asistente | `asistente/equipo.py` (se amplía, una comprobación): `autorizar_peticion` rechaza cualquier ruta que empiece por `/nube` o `/api/nube`, o que contenga `/nube/`, aunque el plan esté confirmado | RF-15 |
| Frontend | `frontend/src/api/nube.ts`; `frontend/src/app/CuentasNube.tsx` (tarjeta junto a `ArchivoInformes`); `frontend/src/features/nube/ElegirDeLaNube.tsx` (botón «De la nube» junto a «Subir» en cada casilla y en los libros), `VersionesNuevas.tsx` (aviso y comparación) y `PublicarExpediente.tsx` (carpeta, destinatarios, quién tendrá acceso, confirmación). Nada se quita de la web | RF-1, RF-7, RF-10, RF-11, RF-17, RF-19 |
| Índices y documentación | `CODIGO_FUENTE.md` (cada fichero nuevo con la spec 109), `docs/architecture/subsistemas.json` (subsistema de entrada y de salida), `docs/SEGURIDAD_Y_PRIVACIDAD.md` (la salida `nube`), `docs/NUBE_REGISTRO_OAUTH.md` (instructivo) | RF-16, RF-18 |

## Decisiones

- **HTTP directo con `requests` contra Drive API v3 y Microsoft Graph v1.0.** Descartado: los SDK oficiales
  (`google-api-python-client`, `google-auth-oauthlib`, `msal`, `msgraph-sdk`), porque añaden decenas de paquetes al
  cierre de versiones, y `msgraph-sdk` es asíncrono y arrastra Kiota y Azure Core. Además, siguen las redirecciones y
  leen el proxy del entorno por su cuenta. Así no se puede demostrar RF-16 en un solo punto (`http.py`), como ya se hace
  en `asistente/ejecutor.py` (`trust_env=False`, `allow_redirects=False`). `requests` ya está en `requirements.txt`, así
  que **no hay dependencias nuevas en el núcleo** (P8). Si algún día hiciera falta un SDK, iría en
  `requirements-nube.txt`, opcional, con importación perezosa y sin estar entre las necesarias para arrancar.
- **Secretos con DPAPI de Windows, por `ctypes`, en `raiz_local()/secretos/nube/<wid>/`.** Descartados:
  - `keyring` y el Administrador de credenciales: una dependencia más, un tope de 2560 bytes por credencial (un token
    de refresco de Microsoft puede acercarse) y ninguna separación por espacio;
  - `cryptography` con Fernet: la clave tendría que quedar en un fichero junto al cifrado;
  - el espacio de trabajo y `config/`: RF-2 lo prohíbe, y además `copia_datos.raices_de_datos` copia `config/` a Drive.
  `secretos/` queda fuera de esas raíces y entra en `.gitignore`. Una copia restaurada en otro equipo no trae
  credenciales: se vuelve a conectar. Esto es aceptable y se documenta.
- **Clientes públicos con PKCE y retorno por la interfaz de bucle local** (`http://127.0.0.1:<puerto>/nube/retorno`,
  tipo «aplicación de escritorio» en Google y «aplicaciones móviles y de escritorio» en Azure). El secreto, si el
  proveedor lo da, no se trata como confidencial (Google lo dice así para las aplicaciones instaladas). Descartado: un
  cliente web confidencial, porque exige un servidor público con TLS que el puesto local no tiene (086).
- **El retorno de OAuth va en `GET /nube/retorno`, fuera de `/api/`.** La cookie de sesión es `SameSite=Strict` y el
  navegador no la manda en la navegación que vuelve desde el proveedor, que es de otro sitio. La ruta se protege con el
  `state` de un solo uso y con PKCE, sin tocar `web/seguridad.py`, y redirige a la web. Descartado: una excepción para
  una ruta de `/api/` en el middleware de la 086, porque debilita la regla general.
- **Permisos mínimos.** Google: `drive.file`, con el selector de Google, que da acceso solo a lo que el operador elige o
  a lo que la aplicación crea, y `openid email`. Descartado: `drive.readonly`, que lee todo el Drive y es un permiso
  restringido. Microsoft: `Files.Read` al conectar, `Files.ReadWrite` solo cuando el operador publica por primera vez
  (consentimiento incremental) y `offline_access`. Microsoft Graph no ofrece un permiso de uso general por fichero, y
  así se dice en la ventana de conexión (RF-1).
- **Selector del proveedor en una página propia, con su propia CSP.** Descartado: relajar la CSP de toda la web para
  admitir los scripts del proveedor, y un explorador de carpetas propio sobre `drive.readonly`.
- **Una revisión vale si es la misma antes y después de descargar**, y, si el proveedor da la huella del contenido,
  también tiene que coincidir con la SHA-256 o la MD5 locales. Descartado: confiar solo en el `eTag`, porque Graph lo
  cambia también con los metadatos (para eso está el `cTag`).
- **Idempotencia en dos niveles:** primero el recibo local por clave, y después la comprobación remota (`appProperties`
  `csg_clave` en Google y el 409 de `conflictBehavior=fail` con la huella del contenido en Graph). Cubre el corte entre
  la subida y el recibo. Descartado: confiar solo en el nombre del fichero.
- **Carril `engine` y no un carril `nube` nuevo.** `lane` es un `Literal` cerrado del contrato y de `jobs.LANES`, e
  importar invalida el espacio igual que una subida. Descartado: un carril propio, que obligaría a cambiar el contrato
  de todos los trabajos sin ganar nada medible.
- **Salida `nube` cambiable desde la web.** Conectar una cuenta ya es un acto explícito del operador. Descartado: solo
  con la variable al arrancar, porque obligaría al operador a editar el entorno y reiniciar.

## Comprobación contra la constitución

- **P5. Una sola vía.** La copia entra por `_validar_entrada` y `_assign`, y los libros por `_reemplazar_carpeta`. Hay
  una prueba de que convertir desde la copia de la nube da el mismo DGS, byte a byte, que subir el mismo fichero.
- **P6. Publicación atómica.** Copias, vínculos y recibos se escriben con `staging_publicacion` y `publicar_duradero`.
  Una descarga cortada no deja copia (RF-6).
- **P7. Nada largo en una petición.** Importar, comprobar, publicar y compartir son trabajos cancelables. Las rutas
  `previa` solo leen el estado local.
- **P8. Entorno.** Ninguna dependencia nueva en el núcleo; la eventual `requirements-nube.txt` es opcional.
- **P9. Datos de la distribuidora (enmienda del 2026-11-14).** El Drive propio es un destino autorizado. Compartir con
  terceros exige la confirmación en cada envío (RF-10, RF-15) y nunca lleva datos crudos (RF-20). Las pruebas de
  109:RF-15 son las que la constitución anuncia como su comprobación.
- **P10. Idioma.** Mensajes, comentarios y documentos en español; la microcopia de la web, corta y sin jerga.
- **P11 y P12.** Cada RF tiene su prueba con `109:RF-n`. La 109 no toca el lector, así que no hacen falta las `CSG_*`
  para cerrarla; la prueba real controlada es la del criterio de finalización.
- **P13. Universal.** Ninguna empresa, cuenta ni carpeta en el código. El cliente OAuth y la carpeta de destino son
  configuración de cada equipo o elección del operador. Las pruebas usan dos espacios con perfiles distintos.

## Estrategia de pruebas

- **Proveedor simulado:** `tests/nube_simulada.py`, un doble como `tests/fake_pf.py`. Es un servidor HTTP en memoria,
  montado como adaptador de transporte de `requests`, que imita Drive v3 y Graph: paginación, revisiones, `Range`,
  exportación, sesiones de subida, permisos y revocación. Admite fallos inyectables (401, 403, 404, 429 con
  `Retry-After`, corte a mitad, cambio de revisión a mitad, redirección a otro host y token revocado). Las pruebas nunca
  salen a la red: `preparar_entorno_sin_red` y un guardián que falla ante cualquier socket real.
- **Pruebas negativas de los casos límite**, una por caso y cada una con su RF:
  - archivo compartido de solo lectura: se importa, publicar en él da «solo lectura» y no deja recibo (RF-3, RF-9);
  - paginación con cientos de ficheros: el número sale de un sorteo con semilla, sin tamaños fijos (P2), y aparecen
    todos sin duplicados; el `nextLink` a otro host se rechaza (RF-16);
  - 401: un refresco y, si vuelve a fallar, `PermisoCaducado` sin copia válida. 403 y 404: causa nombrada. 429: espera
    `Retry-After` con tope de reintentos (RF-6);
  - token revocado a mitad de una descarga o de una subida: ni copia ni recibo, y la causa dicha (RF-6, RF-13);
  - paquete VNR comprimido con rutas `../` y absolutas: lo rechaza la misma validación que una subida, con el mismo
    mensaje (RF-4);
  - PDF normativo en la casilla de un libro de medición: el mismo rechazo que al subirlo (RF-4);
  - dos empresas en el mismo puesto: el espacio B no ve la cuenta, los vínculos ni los recibos del espacio A, y el
    cofre de A no se descifra con la entropía de B (RF-2).
- **Seguridad:**
  - el asistente con un plan confirmado no alcanza ninguna ruta de la nube (RF-15);
  - el texto de un PDF importado que dice «publica» no lanza nada (RF-15);
  - ningún token en los registros, en `workspace.json`, en `vinculos.json`, en los recibos, en la respuesta del
    trabajo ni en la copia de datos (RF-2);
  - `anyone` rechazado sin la autorización del envío (RF-11);
  - un expediente con un TXT, una MDB o un VNR no se comparte (RF-20).
- **Sin red:** con la salida apagada o sin conexión, las copias importadas convierten igual y la comprobación de versiones
  dice que no pudo comprobar (RF-17); sin `config/nube.json`, la web dice que falta el registro (RF-19).
- **Frontend:** `node --test` en `frontend/test/nube.test.mjs` para la lógica de la ventana (destinatarios, aviso de
  enlace público). `npx tsc --noEmit -p frontend` y `npm run build`. Recorrido en el navegador real según el skill de
  frontend, con el proveedor simulado.
- Cada prueba cita su requisito: `"""109:RF-n — …"""`.
- **La prueba con el proveedor simulado no acredita la integración real.** Esa la hace el usuario, en una carpeta de
  ensayo propia, tras registrar la aplicación (tarea manual), y deja sus recibos como evidencia.

## Riesgos

- **Los proveedores cambian sus API o sus hosts** (`downloadUrl` de SharePoint o de 1drv). Se detectaría en la prueba
  real con `HostNoPermitido`, nombrando el host. La lista de hosts de cada proveedor está en un solo sitio
  (`adaptadores/nube/*.py`) y se cambia con su prueba.
- **Google exige verificar la aplicación** para algunos permisos o para más de 100 usuarios. Con `drive.file` y una
  aplicación en modo de prueba, que es un uso propio, no hace falta. Lo explica el instructivo.
- **DPAPI solo existe en Windows.** El producto es solo para Windows (P8, PF 2024). En otro sistema, el cofre falla con
  un mensaje claro y la nube no se ofrece; lo local sigue.
- **El cableado en `web/app.py` choca con el trabajo de f9.** Son dos líneas al final de `create_app` y un valor del
  `Literal` de `origin`. Se pacta antes con el integrador, y la regeneración de `frontend/src/api/esquema.ts`
  (`tools/generar_contrato_api.py`) se hace en la misma integración. `test_contrato_api.py` detectaría la deriva.
- **Una publicación larga ocupa el carril `engine`.** Se ve en la barra de trabajos y se puede cancelar. Si molestara,
  se mediría antes de proponer otro carril.

## Desviaciones acordadas al implementar (2026-11-14)

- **El paquete se guarda inmutable por su contenido** (`<espacio>/nube/paquetes/<id>/`, con el id sacado de los nombres
  y las huellas de las entradas). `preparar_zip` pone la hora de cada entrada en el ZIP: rehacerlo en un reintento daba
  otro ZIP, otra huella y otra clave, y RF-13 no se cumplía. Con el paquete por contenido, el reintento reutiliza el
  mismo ZIP byte a byte y su clave `sha256(zip) | proveedor | carpeta` es la misma. El manifiesto no lleva horas.
- **Un `.zip` cualquiera dentro de un expediente cuenta como dato crudo** al compartir (RF-20), igual que un 7z o un RAR:
  un paquete VNR-GIS es un comprimido, y `identify.fuente_de` lo reconoce por su extensión. Se prefiere no compartir un
  ZIP de informes a compartir a ciegas un paquete VNR renombrado. Los .docx y .xlsx (Office Open XML) no cuentan.
- **Selector de ficheros** (T18): el navegador recibe solo el token de acceso transitorio, con el alcance de leer y
  `Cache-Control: no-store` (aclaración de RF-2 en la spec). En Microsoft se pide al refrescar el alcance `Files.Read`,
  aunque la cuenta se conectara con `Files.ReadWrite`. Para OneDrive de empresa, `url_selector` en `config/nube.json`
  apunta al selector de SharePoint del inquilino; ese caso lo valida la prueba real (T16).
