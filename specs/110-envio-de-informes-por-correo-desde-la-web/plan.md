# Plan — Spec 110

Lee: `docs/constitution.md` (P7, P8, P9 con su enmienda del 2026-11-14, P12 y P13) y
`specs/110-envio-de-informes-por-correo-desde-la-web/spec.md`. Depende de `specs/109-…/spec.md` (credenciales,
consentimiento OAuth y permisos de lectura de un expediente), que esta spec no cambia.

## Contexto técnico

Base leída: `trabajo/plan-maestro-specs@51895566`. Lo que ya existe y se reutiliza, sin copiarlo (P5):

| Pieza existente | Qué aporta a la 110 |
| --- | --- |
| `src/convertersmartgrid/adaptadores/informe_docx.py` (`escribir_informe_estudio`, `escribir_informe_factibilidad`, `escribir_resumen_estudios`, `_guardar`) | Los informes Word y su resumen `.json`, publicados a la vez y de forma atómica. Ese par publicado es lo que esta spec llama **informe cerrado**. La 110 no escribe informes: los lee |
| `src/convertersmartgrid/adaptadores/libro_informe.py` (`generar_libro`) e `informe_docx.exportar_pdf` | El libro `.xlsx` y el PDF del mismo informe, que la ventana ofrece como adjuntos (los campos `informe`, `pdf`, `libro_xlsx` y `json` del resultado que ya pinta `InformesPF.tsx`) |
| `src/convertersmartgrid/adaptadores/informes.py` (`asunto_propuesto`) | El asunto inicial de la ventana, editable |
| `src/convertersmartgrid/adaptadores/archivo_informes.py` (`_huella`) | La huella SHA-256 por bloques de un fichero. Se reutiliza la misma función (se hace pública como `huella_fichero` en ese módulo, sin cambiar su comportamiento) |
| `src/convertersmartgrid/adaptadores/identify.py` (`identificar`, `es_base_access`, `fuente_de`) | Reconoce por su contenido un TXT de CYMDIST, una base MDB o una fuente VNR: es la lista negra de adjuntos de RF-11 |
| `src/convertersmartgrid/aplicacion/asistente/equipo.py` (`GobiernoEquipo`, `_huella`, `PermisoDenegado`) y `asistente/tareas.py` | La forma de sellar lo que el operador vio (firma del plan, alcance y huellas de entrada, `confirmar` que vuelve a comprobarlo) y la frontera HTTP del ejecutor (`autorizar_peticion`). La 110 copia el patrón en su borrador, no el código, y añade una prueba de que ningún paso de ningún plan puede alcanzar la ruta de confirmación del envío |
| `src/convertersmartgrid/aplicacion/asistente/almacen.py` (`anotar`) | Bitácora de solo añadir, con `fsync`. Se usa para la fila de auditoría `correo_envios` del asistente cuando un borrador nace de una orden |
| `src/convertersmartgrid/presentacion/web/jobs.py` (`JobManager.submit`, `LANES`, `DiarioTrabajos`) | El envío es un trabajo en cola (P7). Se encola **sin** `reanudar`, para que la 096 nunca lo relance solo tras un reinicio |
| `src/convertersmartgrid/presentacion/web/seguridad.py` | `Origin` propio, token de sesión y `_SinTokenEnElRegistro`. Se añade un filtro hermano que enmascara direcciones y tokens del correo |
| `src/convertersmartgrid/dominio/salidas_red.py` (`SALIDAS`, `exigir_salida`) | Cada salida a la red declarada con su interruptor; `tests/test_seguridad_web.py` falla si un módulo abre la red sin estar ahí |
| `src/convertersmartgrid/presentacion/web/*_api.py` (`copia_datos_api.registrar_rutas_copia` como modelo) y `web/api_contract.py` | Patrón de rutas en su propio módulo, registradas desde `create_app` con una llamada, y modelos de respuesta tipados |
| `frontend/src/features/powerfactory/InformesPF.tsx` (`Resultado`) y `frontend/src/app/ArchivoInformes.tsx` | Donde hoy se descarga cada informe: allí aparece «Enviar por correo» y el historial. No se quita ningún botón |
| Spec 109 (credenciales cifradas 109:RF-2, consentimiento 109:RF-1, permiso de lectura 109:RF-10, recibos 109:RF-12) | Token del proveedor y concesión del acceso de un enlace. La 110 lo consume por la interfaz que fije el plan de 109 |

Módulos nuevos, con su ruta propuesta (todos entran en `CODIGO_FUENTE.md` y en el catálogo de la 090 en el mismo cambio):

| Fichero nuevo | Responsabilidad |
| --- | --- |
| `src/convertersmartgrid/puertos/correo/__init__.py` | Paquete del envío de informes; sin dependencias fuera de la biblioteca estándar y `requests` |
| `src/convertersmartgrid/adaptadores/correo/borrador.py` | `Borrador` (cuenta, para, cc, cco, asunto, cuerpo, adjuntos con ruta, tamaño y SHA-256, o enlace), su **firma**, la comprobación de adjuntos (cerrado, mismo proyecto y escenario, lista negra), la validez del estudio y el aviso de contactos habituales |
| `src/convertersmartgrid/adaptadores/correo/envios.py` | Diario durable de envíos por espacio: reserva de la clave, estados, recibos, historial por informe y reconciliación al arrancar |
| `src/convertersmartgrid/adaptadores/correo/mensaje.py` | El mensaje MIME con `email.message.EmailMessage` (biblioteca estándar), con `Message-ID` derivado de la clave |
| `src/convertersmartgrid/adaptadores/correo/proveedores.py` | `ProveedorCorreo` (Protocol) y sus dos adaptadores, `EnvioGmail` (`gmail.send`) y `EnvioOutlook` (`Mail.Send`), con `requests`, sin redirecciones y con plazo; la tabla de errores a estados |
| `src/convertersmartgrid/presentacion/web/correo_api.py` | `registrar_rutas_correo(app, *, ws_or_404, submit, credenciales, compartir)`: vista previa, confirmación, estado e historial |
| `frontend/src/api/correo.ts` | Cliente tipado de esas rutas |
| `frontend/src/features/powerfactory/EnviarInforme.tsx` | La ventana de envío y el historial de envíos de un informe |
| `tests/correo_simulado.py` | Proveedor simulado (como `tests/fake_pf.py`): acepta, rechaza, tarda más que el plazo, acepta y luego no responde, revoca el token |
| `tests/test_correo_borrador.py`, `tests/test_correo_envios.py`, `tests/test_correo_proveedores.py`, `tests/test_correo_web.py` | Pruebas citando `110:RF-n` |
| `docs/CORREO_OAUTH.md` | Instructivo paso a paso para que el usuario registre la aplicación en Google Cloud y en Azure (decisión 1), complementario al de 109 |

Ficheros existentes que se tocan, y cuánto:

- `src/convertersmartgrid/presentacion/web/jobs.py`: un carril más en `LANES` (`'correo'`), y nada más.
- `src/convertersmartgrid/dominio/salidas_red.py`: dos entradas, `correo_google` (`CSG_SALIDA_CORREO_GOOGLE`, host
  `gmail.googleapis.com`) y `correo_microsoft` (`CSG_SALIDA_CORREO_MICROSOFT`, host `graph.microsoft.com`), apagadas en
  la edición de producto como las demás. **Punto de coordinación con 109**, que también añade las suyas: un solo
  escritor por vez sobre ese fichero.
- `src/convertersmartgrid/presentacion/web/seguridad.py`: el filtro `_SinCorreoEnElRegistro`.
- `src/convertersmartgrid/presentacion/web/api_contract.py`: los modelos `CorreoVistaPrevia`, `CorreoConfirmacion`, `CorreoEnvio`,
  `CorreoHistorial`.
- `src/convertersmartgrid/adaptadores/archivo_informes.py`: `_huella` pasa a llamarse `huella_fichero` (con alias `_huella`), sin
  cambiar lo que hace.
- `src/convertersmartgrid/presentacion/web/app.py`: **mínimo, pactado con el integrador f9**: dos líneas en el bloque de módulos
  (`from .correo_api import registrar_rutas_correo` y su llamada), igual que `registrar_rutas_copia`, y la llamada a
  `envios.reconciliar_al_arrancar` dentro de esa misma función de registro, no en el arranque de `app.py`.
- `frontend/src/features/powerfactory/InformesPF.tsx` y `frontend/src/app/ArchivoInformes.tsx`: un botón «Enviar por
  correo» junto a «Descargar Word» y el historial bajo el resultado. Nada se quita.

**No se tocan** `src/convertersmartgrid/presentacion/web/services.py`, `pide_economia.py` ni el adaptador VNR
(`adaptadores/entrada/vnr/`), que corrige f9 (H1–H14). La 110 no necesita nada de `services.py`: el resumen JSON del
informe está en disco, en la salida del espacio, y se lee desde allí. Tampoco se toca `asistente/tareas.py`, que tiene
cambios sin integrar en `wt_asistente_plazos` (ver RF-6 en Decisiones).

Carril de trabajos: `correo`, nuevo, en serie. Índices del dataset: ninguno; la 110 no lee la red.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| A. Borrador y firma: cuenta, destinatarios, asunto, cuerpo, adjuntos o enlace; firma SHA-256 sobre todo ello, con la huella de cada adjunto leída del disco | `correo/borrador.py` | RF-1, RF-4, RF-5 |
| B. Adjuntos admitidos: solo los ficheros que nombra el resumen `.json` de un informe publicado en `ws.out_dir`, con su huella; proyecto y escenario del resumen iguales a los de la ventana; ningún trabajo de informes en curso en el espacio | `correo/borrador.py`, `archivo_informes.huella_fichero` | RF-3 |
| C. Lista negra de adjuntos: extensiones permitidas `.docx`, `.pdf`, `.xlsx`; además, por contenido, se rechaza lo que `identify.identificar`/`es_base_access`/`fuente_de` reconozca como TXT, MDB o VNR, cualquier comprimido, y lo que parezca una credencial (`.env`, JSON con `refresh_token`, `client_secret`) | `correo/borrador.py` | RF-11 |
| D. Validez del estudio: se lee el resumen `.json` del informe; un estudio con `error`, `no_terminado`, una marca de bloqueo o de fuera de dominio, o sin dictamen legible, se presenta como «no válido como estudio» en la ventana y en el cuerpo propuesto | `correo/borrador.py` | RF-12 |
| E. Contactos habituales: las direcciones con algún envío **aceptado** desde ese espacio, más la cuenta del propio operador; una dirección fuera de esa lista lleva un aviso, y si se parece a una habitual (distancia de edición ≤ 2 en la parte local o en el dominio) se sugiere la habitual. El aviso no bloquea | `correo/borrador.py`, `correo/envios.py` | RF-14 |
| F. Diario de envíos: `<ws.root>/envios/<clave>.json` creado con `os.open(O_CREAT \| O_EXCL)` antes de llamar al proveedor; estados `reservado → enviando → aceptado \| rechazado \| desconocido`; escritura atómica con `util.publicar_duradero`; historial por huella del informe | `correo/envios.py` | RF-7, RF-8, RF-9, RF-13 |
| G. Mensaje MIME con `Message-ID: <clave@csg.invalid>` y los adjuntos firmados, leídos otra vez y comparados con su huella justo antes de construirlo | `correo/mensaje.py` | RF-4, RF-8 |
| H. Proveedores: `EnvioGmail` (`POST https://gmail.googleapis.com/upload/gmail/v1/users/me/messages/send?uploadType=media`, `message/rfc822`) y `EnvioOutlook` (`POST https://graph.microsoft.com/v1.0/me/sendMail` con el MIME en base64); solo el alcance de envío; `allow_redirects=False`, `trust_env=False`; plazo `(10 s, 60 s)`; `exigir_salida` antes de abrir la red; límites de tamaño por proveedor declarados en el adaptador | `correo/proveedores.py`, `salidas_red.py` | RF-2, RF-9 |
| I. Enlace en vez de adjuntos: primero `compartir` de 109 (109:RF-10) a esos destinatarios exactos, con su recibo; solo si queda concedido, el correo con el enlace, con el suyo. Si el permiso falla, no sale el correo | `correo/envios.py`, interfaz de 109 | RF-10 |
| J. Rutas: `POST …/correo/vista-previa` (crea el borrador y devuelve firma, avisos y adjuntos), `POST …/correo/{borrador}/confirmar` (con la firma que vio el operador; encola el trabajo), `GET …/correo/envios/{clave}`, `GET …/correo/historial?informe=…`, `POST …/correo/envios/{clave}/resolver` (el operador dice si el desconocido llegó o no) | `web/correo_api.py`, `web/api_contract.py`, `web/app.py` (mínimo) | RF-1, RF-5, RF-7, RF-9, RF-13 |
| K. Frontera con el asistente y los documentos: el asistente no tiene tarea de envío; si una orden o un texto pide enviar, la respuesta es un borrador sin confirmar y un enlace a la ventana. La ruta de confirmación rechaza cualquier petición que no venga de la sesión del navegador (sin `Origin` propio, o con las cabeceras de `cabeceras_locales` del ejecutor) | `web/correo_api.py`, prueba sobre `GobiernoEquipo.autorizar_peticion` | RF-6, RF-5 |
| L. Registros sin direcciones ni tokens: `_SinCorreoEnElRegistro` en el registro de la web, títulos de trabajo sin direcciones («Envío de correo de <informe>»), eventos del trabajo con direcciones enmascaradas (`j…@dominio`) | `web/seguridad.py`, `web/correo_api.py` | RNF |
| M. Ventana e historial en la web: cuenta, para, cc, cco, asunto, cuerpo editable, adjuntos o enlace, avisos de RF-12 y RF-14, «Confirmar y enviar» desactivado mientras el trabajo corre, y el historial de envíos del informe | `frontend/src/features/powerfactory/EnviarInforme.tsx`, `frontend/src/api/correo.ts`, `InformesPF.tsx`, `ArchivoInformes.tsx` | RF-1, RF-12, RF-13, RF-14 |
| N. Instructivo de registro OAuth y prueba real controlada | `docs/CORREO_OAUTH.md` | RF-2 (real) |

## Decisiones

- **Un borrador firmado en el servidor, y la confirmación lleva la firma.** La vista previa guarda el borrador y
  devuelve su firma; «Confirmar» manda esa firma; el trabajo vuelve a leer cada adjunto, recalcula la firma y, si no
  coincide, el envío no sale y la ventana pide revisarlo (RF-4, RF-5). Es el mismo principio de `GobiernoEquipo.confirmar`
  (firma del plan más huellas de entrada). Descartado: confirmar con un simple `POST …/enviar` con los campos en el
  cuerpo, porque nada probaría que lo enviado es lo que el operador vio, y un adjunto regenerado entre la vista y el clic
  saldría sin revisar.
- **Idempotencia por clave reservada en disco, no en memoria.** `clave = sha256(espacio, borrador, firma, intento)`. La
  reserva es la creación exclusiva de `<ws.root>/envios/<clave>.json` **antes** de llamar al proveedor (RF-7). Un doble
  clic o un segundo `POST …/confirmar` con la misma firma encuentra la clave y devuelve su recibo sin encolar otro
  trabajo. El `Message-ID` del correo sale de la clave, para que el operador lo encuentre en «Enviados». Descartado:
  confiar en `guardado['en_curso']` como hace hoy el asistente, que G0 marcó como no verificado ante una carrera entre
  dos POST (`AGENT_ACTION_MAP.md`, sección 1); y descartado depender de una clave de idempotencia del proveedor, porque
  ni `messages.send` de Gmail ni `sendMail` de Graph la admiten.
- **Estado desconocido, y nunca un reenvío solo.** Tabla de resultados del adaptador:
  - aceptado: Gmail 200 con `id`; Graph 202 (sin `id`: se guarda el `Message-ID` propio y el `request-id` de la respuesta);
  - rechazado (no salió): error de conexión antes de enviar el cuerpo (`ConnectTimeout`, DNS), 400, 401, 403, 413 y 429;
  - desconocido: `ReadTimeout`, conexión cortada tras enviar el cuerpo, cualquier 5xx, o un trabajo interrumpido por un
    reinicio con la reserva en `enviando`.

  Un desconocido no se reintenta nunca solo (RF-9): el historial lo muestra con «Compruebe en Enviados de su cuenta»,
  y el operador lo resuelve con «Llegó» o «No llegó». Solo «No llegó» habilita un nuevo intento, con otra clave
  (`intento + 1`) y una confirmación nueva. Un rechazado admite reintentar con confirmación nueva. Descartado: consultar
  la carpeta «Enviados» para resolverlo solo, porque exige `gmail.readonly` o `Mail.Read`, y RF-2 y «Fuera de alcance»
  prohíben leer el buzón.
- **Reconciliación al arrancar.** `envios.reconciliar_al_arrancar` pasa a `desconocido` toda reserva en `reservado` o
  `enviando` sin resultado, y el trabajo se encola sin `reanudar`, para que la 096 no lo relance. Descartado: relanzar
  como los demás trabajos interrumpidos, porque un correo ya aceptado saldría dos veces.
- **El asistente solo prepara (RF-6).** El asistente no tiene tarea de envío. Si una orden pide enviar, la web le
  responde con un borrador sin confirmar y el enlace a la ventana; la confirmación solo existe en la ruta de la web, que
  ningún paso de `asistente/ejecutor.pasos` produce y que rechaza las peticiones del ejecutor. Descartado: una tarea
  `enviar_informe` en `asistente/tareas.py` con `requiere_confirmacion`, porque un clic sobre el plan del asistente
  confirmaría el envío sin ver la ventana, y porque `tareas.py` tiene cambios sin integrar en `wt_asistente_plazos`. Si
  más adelante se quiere la tarea `preparar_envio`, entra en esa rama y solo crea el borrador.
- **Credenciales y consentimiento son de la 109.** La 110 pide a la interfaz de 109 un token con el alcance
  `https://www.googleapis.com/auth/gmail.send` o `Mail.Send`, con consentimiento incremental la primera vez. Nunca
  guarda tokens propios ni los ve el navegador. Descartado: un token con Drive y correo a la vez, porque 109:RF-1 pide
  solo los permisos de cada tarea; y descartado SMTP con contraseña («Fuera de alcance»). Hasta que el plan de 109 fije
  su interfaz, la 110 la consume a través de un `Protocol` local (`FuenteDeCredenciales.token(proveedor, cuenta,
  alcance)` y `Compartidor.conceder_lectura(expediente, destinatarios)`) que las pruebas simulan; si 109 la nombra
  distinto, se adapta el `Protocol` sin cambiar ningún RF.
- **Un carril `correo` propio.** El envío espera a la red, no al motor ni a PowerFactory. Descartado: el carril
  `engine`, porque el correo esperaría detrás de una conversión de minutos y bloquearía las entradas (`locked =
  Boolean(active.engine)`); y descartado `control`, que es para cancelar y no puede quedar detrás de un plazo de red.
- **Límites de tamaño por proveedor, en el adaptador.** Gmail: 25 MB de adjuntos; Outlook con solo `Mail.Send`: 3 MB
  en total (`sendMail` no admite la sesión de subida, que pide `Mail.ReadWrite`). Si se pasa, la vista previa lo dice y
  ofrece enviar el enlace (RF-10). Los valores se comprueban contra la documentación vigente del proveedor en T5 y se
  anotan con su fuente. Descartado: pedir `Mail.ReadWrite` para subir borradores grandes, porque da acceso al buzón.
- **Contactos habituales sin libreta (decisión 2).** Se deducen de los recibos aceptados del propio espacio, sin lista
  de empresa en el código ni en el perfil (P13). El aviso no bloquea. Descartado: una libreta autorizada por la empresa,
  que el usuario descartó el 2026-11-14.
- **Recibos fuera de la salida del espacio.** `<ws.root>/envios/`, no `ws.out_dir`: llevan direcciones personales y no
  deben aparecer en `GET …/outputs` ni viajar con una copia de la salida. T3 comprueba que la copia de datos de la 086
  los incluya y que la retención de la 062 no los borre.
  Descartado: `almacen` del asistente, que es global y no por espacio (T17 de G0).
- **Dependencias.** `requests` y `email` ya están en el núcleo: la 110 no añade ninguna a `requirements.txt` (P8). Si
  la 109 necesitara una biblioteca OAuth, es opcional y suya; sin ella, la 110 dice «Conecte una cuenta» y el resto de la
  web funciona igual. Descartado: los SDK `google-api-python-client` y `msgraph-sdk`, que pesan y no hacen falta para una
  sola llamada REST.

## Comprobación contra la constitución

- **P5 (una vía).** Los informes se leen, no se rehacen; la huella es la de `archivo_informes`; el reconocimiento de
  TXT, MDB y VNR es el de `identify.py`.
- **P7 (nada largo en HTTP).** La vista previa solo lee resúmenes y calcula huellas de ficheros de la salida; el envío
  es un trabajo en el carril `correo`, con progreso por WebSocket. Cancelar antes de llamar al proveedor libera la
  reserva como `cancelado`; durante la llamada no se puede cancelar a medias y se dice así.
- **P8 (entorno).** Ninguna dependencia nueva en el núcleo; la integración real depende del registro OAuth del usuario
  y de la 109, y su ausencia no impide instalar ni arrancar.
- **P9 (con la enmienda del 2026-11-14).** Ningún envío sin la confirmación del operador ligada a la firma (RF-5);
  ningún adjunto con TXT, MDB ni VNR, ni credenciales (RF-11); el asistente no envía (RF-6). Son las pruebas que la
  enmienda anuncia para 110:RF-5 y 110:RF-11.
- **P10 (idioma).** Textos de la ventana, errores y comentarios en español; los nombres de los proveedores, tal cual.
- **P12 (la spec manda).** RF-14 entró primero en la spec; cada RF tiene una tarea y una prueba que lo cita.
- **P13 (universal).** Cualquier cuenta de Google o de Microsoft, personal o de empresa; ningún dominio, empresa ni
  dirección fija en el código; los contactos habituales salen de cada espacio.
- **La web no pierde nada.** Los botones de descarga, el JSON y el plan de cada informe siguen; «Enviar por correo» se
  añade a su lado. Sin cuenta conectada, el botón dice por qué está desactivado (frontend, principio 7).

## Estrategia de pruebas

- **Proveedor simulado** (`tests/correo_simulado.py`), inyectado en lugar de `EnvioGmail`/`EnvioOutlook`, con modos:
  acepta; rechaza con 400, 401 (cuenta revocada), 403, 413 y 429; `ConnectTimeout`; acepta y luego no responde
  (`ReadTimeout` tras recibir el cuerpo); 5xx. Cuenta las llamadas: «una sola llamada» es la afirmación de cada prueba
  de idempotencia. Las credenciales y el compartidor de 109 también son simulados.
- **Adaptadores reales sin red:** `requests` sustituido por un transporte de prueba que comprueba la URL, el alcance
  pedido, `allow_redirects=False`, el plazo y el cuerpo MIME; ninguna prueba abre la red ni inicia OAuth.
- **Pruebas negativas obligatorias** (criterios de finalización): doble clic y doble POST con la misma firma (una sola
  llamada al proveedor, el mismo recibo); timeout tras aceptar (estado desconocido, cero reenvíos, también tras
  reiniciar el diario); adjunto cambiado entre la vista previa y la confirmación (409 y ninguna llamada); orden del
  asistente y texto de un PDF importado que piden enviar (solo borrador; la ruta de confirmar rechaza al ejecutor);
  adjunto TXT, MDB, VNR, `.zip` y `.env` renombrados a `.pdf` (rechazados por contenido); dirección mal escrita
  (aviso de RF-14 con la sugerencia, sin bloquear); adjunto por encima del límite (la vista previa lo dice y ofrece el
  enlace); cuenta revocada (rechazado, «vuelva a conectar la cuenta»); enlace con el permiso de 109 fallido (no sale el
  correo).
- **Informes de prueba:** se generan con las funciones reales de `informe_docx.py` sobre datos sintéticos (como ya hacen
  sus pruebas), con dos perfiles de empresa distintos (P13); no hace falta DIgSILENT ni los TXT reales, porque la 110 no
  toca el lector ni el modelo (P11: no aplican las `CSG_*`).
- **Registros:** una prueba captura el registro de la web y los eventos del trabajo durante un envío simulado y exige
  que no aparezca ninguna dirección completa ni ningún token.
- **Web:** `tests/test_correo_web.py` con `TestClient`, como `tests/test_web_api.py`; contrato de la API regenerado
  (`docs/asistente/openapi.json`, `tests/test_contrato_api.py`); `npx tsc --noEmit -p frontend` y `npm run build` en la
  tarea del frontend, y revisión en un navegador real (densidad y microcopia, sin «RF» visibles).
- Cada prueba cita su requisito: `"""110:RF-n — …"""`.
- **Prueba real controlada** (criterio de finalización): tras el registro OAuth del usuario, un envío a una dirección
  del propio usuario, con su recibo. La prueba con el simulado no acredita la integración real, y se dice así en la
  validación.

## Riesgos

- **La interfaz de 109 aún no existe.** Si su plan fija otra forma, se adapta el `Protocol` de la 110 (T2). Se detecta
  al integrar: las pruebas de la 110 usan el `Protocol`, y una prueba de contrato contra la implementación de 109 se
  añade cuando esta exista.
- **`salidas_red.py` lo tocan 109 y 110.** Dos escritores sobre el mismo fichero: se serializa (primero 109, por el
  orden de la decisión 6) y `tests/test_seguridad_web.py` detecta una salida sin declarar.
- **`web/app.py` es del integrador f9 mientras corrige H1–H14.** El cableado son dos líneas pactadas; hasta entonces las
  rutas se prueban montándolas en una `FastAPI()` de prueba con `registrar_rutas_correo`.
- **Un informe sin resumen `.json` o con otro formato** (informes antiguos): no se puede adjuntar como cerrado; la
  ventana lo dice y la descarga sigue igual. Se detecta con una prueba sobre un informe sin su `.json`.
- **Graph `sendMail` no devuelve identificador.** El recibo de Outlook guarda el `Message-ID` propio y el `request-id`;
  la validación lo dice para no confundirlo con una prueba de entrega (spec, «Fuera de alcance»).
- **Límites del proveedor que cambian.** Están en el adaptador, con su fuente; un 413 del proveedor se traduce a
  «rechazado: demasiado grande» y no a un desconocido.
- **Datos personales en los recibos.** Viven en `<ws.root>/envios/`, fuera de la salida. Si la retención de la 062 o la
  copia de la 086 los tratan de otro modo, T3 lo detecta; si el usuario pide otra política, entra en esta spec antes que
  en el código.

## Trazabilidad (T13)

Cada RF con hasta tres de las pruebas que lo citan (`110:RF-n` en su docstring); `tests/test_correo_trazabilidad.py`
comprueba que cada una existe y lo cita. Son pruebas con el proveedor simulado: la integración real con una cuenta la
acredita la prueba opcional de T12.

| RF | Pruebas |
| --- | --- |
| RF-1 | `tests/test_correo_borrador.py::test_la_firma_cubre_todo_lo_que_ve_el_operador`, `tests/test_correo_borrador.py::test_la_firma_cubre_ruta_tamano_y_huella_de_cada_adjunto`, `tests/test_correo_borrador.py::test_direcciones_imposibles_se_rechazan` |
| RF-2 | `tests/test_correo_de_la_109.py::test_la_interfaz_de_la_109_es_la_que_usa_la_110`, `tests/test_correo_de_la_109.py::test_el_permiso_de_enviar_es_el_de_la_109`, `tests/test_correo_de_la_109.py::test_token_de_la_cuenta_conectada` |
| RF-3 | `tests/test_correo_borrador.py::test_un_informe_cerrado_da_sus_adjuntos_con_huella`, `tests/test_correo_borrador.py::test_un_informe_sin_su_resumen_no_esta_cerrado`, `tests/test_correo_borrador.py::test_solo_informes_de_la_salida_del_espacio` |
| RF-4 | `tests/test_correo_borrador.py::test_la_firma_cubre_ruta_tamano_y_huella_de_cada_adjunto`, `tests/test_correo_borrador.py::test_un_byte_cambiado_tras_la_vista_previa_pide_revisarlo_sin_llamar_al_proveedor`, `tests/test_correo_borrador.py::test_un_adjunto_borrado_tambien_anula` |
| RF-5 | `tests/test_correo_borrador.py::test_la_firma_cubre_todo_lo_que_ve_el_operador`, `tests/test_correo_borrador.py::test_otro_destinatario_con_la_misma_firma_se_rechaza`, `tests/test_correo_borrador.py::test_el_borrador_va_y_vuelve_por_json_con_la_misma_firma` |
| RF-6 | `tests/test_correo_web.py::test_solo_la_ventana_del_navegador_confirma`, `tests/test_correo_web.py::test_una_orden_del_asistente_o_un_documento_solo_dejan_un_borrador`, `tests/test_correo_web.py::test_ningun_paso_del_asistente_alcanza_la_confirmacion` |
| RF-7 | `tests/test_correo_envios.py::test_la_clave_se_reserva_antes_de_llamar_al_proveedor`, `tests/test_correo_envios.py::test_dos_confirmaciones_de_la_misma_firma_una_sola_llamada`, `tests/test_correo_envios.py::test_doble_clic_a_la_vez_una_sola_llamada` |
| RF-8 | `tests/test_correo_envios.py::test_el_recibo_guarda_clave_id_estado_hora_destinatarios_y_huella`, `tests/test_correo_envios.py::test_los_recibos_viajan_en_la_copia_y_la_retencion_no_los_borra`, `tests/test_correo_proveedores.py::test_mime_con_cabeceras_message_id_de_la_clave_y_adjuntos` |
| RF-9 | `tests/test_correo_de_la_109.py::test_sin_cuenta_otra_cuenta_sin_permiso_o_revocada`, `tests/test_correo_envios.py::test_timeout_tras_aceptar_queda_desconocido_y_no_se_reenvia`, `tests/test_correo_envios.py::test_un_5xx_tambien_es_desconocido` |
| RF-10 | `tests/test_correo_borrador.py::test_un_enlace_que_no_es_https_limpio_se_rechaza`, `tests/test_correo_borrador.py::test_adjuntos_y_enlace_a_la_vez_no`, `tests/test_correo_de_la_109.py::test_conceder_lectura_a_esos_destinatarios` |
| RF-11 | `tests/test_correo_borrador.py::test_datos_crudos_y_credenciales_renombrados_se_rechazan_por_contenido`, `tests/test_correo_borrador.py::test_solo_word_pdf_y_excel`, `tests/test_correo_borrador.py::test_un_word_que_lleva_otro_fichero_dentro_o_una_credencial_se_rechaza` |
| RF-12 | `tests/test_correo_borrador.py::test_validez_un_informe_valido`, `tests/test_correo_borrador.py::test_validez_estudios_que_no_valen`, `tests/test_correo_borrador.py::test_validez_sin_json` |
| RF-13 | `tests/test_correo_envios.py::test_historial_por_informe`, `tests/test_correo_envios.py::test_un_recibo_roto_no_tumba_el_historial`, `tests/test_correo_web.py::test_estado_historial_y_resolver_un_desconocido` |
| RF-14 | `tests/test_correo_borrador.py::test_habituales_son_los_aceptados_y_la_cuenta`, `tests/test_correo_borrador.py::test_habituales_avisos_nueva_mal_escrita_y_habitual`, `tests/test_correo_borrador.py::test_habituales_el_aviso_no_impide_el_envio` |
