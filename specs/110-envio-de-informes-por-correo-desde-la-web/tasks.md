# Tareas — Spec 110

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.
Orden por dependencia: T1–T7 no necesitan la web ni la 109 real (proveedor, credenciales y compartidor simulados);
T8–T10 montan la web; T11–T12 dependen del registro OAuth del usuario. Ninguna toca `web/services.py`,
`pide_economia.py` ni el adaptador VNR.

- [x] T1. Proveedor simulado y contratos con la 109: `tests/correo_simulado.py` (acepta, 400, 401, 403, 413, 429, 5xx,
      `ConnectTimeout`, acepta y no responde) y los `Protocol` `FuenteDeCredenciales` y `Compartidor` en
      `src/convertersmartgrid/correo/__init__.py`; borrador con su firma en `correo/borrador.py`: la firma cubre
      cuenta, para, cc, cco, asunto, cuerpo, enlace y la ruta, el tamaño y el SHA-256 de cada adjunto; comprobar la
      firma vuelve a leer los adjuntos del disco. (RF-1, RF-4, RF-5)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_correo_borrador.py` en verde, con una prueba que
      cambia un byte de un adjunto tras la vista previa y obtiene «revise otra vez» sin ninguna llamada al simulado, y
      otra que cambia un destinatario con la misma firma y es rechazada.
- [ ] T2. Adjuntos admitidos y prohibidos: solo los ficheros que nombra el resumen `.json` de un informe publicado en
      `ws.out_dir`, con el proyecto y el escenario de la ventana y sin un trabajo de informes en curso; extensiones
      `.docx`, `.pdf` y `.xlsx`; rechazo por contenido de TXT, MDB y VNR (`identify.identificar`, `es_base_access`,
      `fuente_de`), de comprimidos y de credenciales; `archivo_informes._huella` pasa a `huella_fichero` con alias.
      (RF-3, RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_correo_borrador.py tests/test_evolucion_clientes_fijos.py`
      en verde, con informes sintéticos de dos perfiles de empresa y con un TXT, una MDB, un `.zip` y un `.env`
      renombrados a `.pdf`, todos rechazados.
- [ ] T3. Diario de envíos en `correo/envios.py`: reserva exclusiva de `<ws.root>/envios/<clave>.json` antes de llamar al
      proveedor; estados `reservado`, `enviando`, `aceptado`, `rechazado`, `desconocido` y `cancelado`; recibo con
      clave, identificador del proveedor, estado, hora, destinatarios y huella del informe; historial por informe;
      `reconciliar_al_arrancar` pasa a `desconocido` lo que quedó en `reservado` o `enviando`; resolver un desconocido
      con «Llegó» o «No llegó», y solo «No llegó» abre el intento siguiente. Se comprueba que la copia de datos de la
      086 incluye `envios/` y que la retención de la 062 no lo borra. (RF-7, RF-8, RF-9, RF-13)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_correo_envios.py` en verde, con dos
      confirmaciones de la misma firma (una sola llamada al simulado y el mismo recibo), un `ReadTimeout` tras aceptar
      (desconocido y cero reenvíos, también tras `reconciliar_al_arrancar`) y un intento nuevo solo después de
      «No llegó».
- [ ] T4. Validez del estudio: leer el resumen `.json` del informe; `error`, `no_terminado`, una marca de bloqueo o de
      fuera de dominio, o un resumen sin dictamen legible, dan «no válido como estudio» en la vista previa y en el
      cuerpo propuesto. (RF-12)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_correo_borrador.py -k validez` en verde, con un
      informe válido, uno con un estudio que no terminó, uno fuera de dominio y uno sin `.json`.
- [ ] T5. Proveedores y mensaje: `correo/mensaje.py` (MIME con `Message-ID` de la clave) y `correo/proveedores.py`
      (`EnvioGmail` con `gmail.send` y `EnvioOutlook` con `Mail.Send`; `allow_redirects=False`, `trust_env=False`,
      plazo `(10 s, 60 s)`, `exigir_salida` antes de abrir la red; tabla de errores a `aceptado`, `rechazado` o
      `desconocido`; límites de tamaño por proveedor con su fuente, comprobados contra la documentación vigente).
      Salidas `correo_google` y `correo_microsoft` en `salidas_red.py`, serializado con la 109. (RF-2, RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_correo_proveedores.py tests/test_seguridad_web.py`
      en verde, con un transporte de prueba que comprueba URL, alcance pedido, que no se siguen redirecciones y que una
      salida apagada no abre la red; ninguna prueba abre la red ni inicia OAuth.
- [ ] T6. Contactos habituales del espacio: direcciones con algún envío aceptado desde ese espacio, más la cuenta del
      operador; aviso junto a cada dirección que no esté, con la habitual parecida como sugerencia (distancia de
      edición ≤ 2), sin bloquear el envío. (RF-14)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_correo_borrador.py -k habituales` en verde, con
      una dirección nueva (aviso), una mal escrita de una habitual (aviso con sugerencia), una habitual (sin aviso) y
      un envío que sale igual tras el aviso; dos espacios no comparten sus contactos.
- [ ] T7. Enviar un enlace: primero `Compartidor.conceder_lectura` (109:RF-10) a esos destinatarios exactos, con su
      recibo; solo si queda concedido, el correo con el enlace, con el suyo; si el permiso falla, no sale el correo.
      Un adjunto por encima del límite del proveedor ofrece este camino en la vista previa. (RF-10)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_correo_envios.py -k enlace` en verde, con el
      orden permiso → correo comprobado en el simulado, dos recibos, y cero correos cuando el permiso falla.
- [ ] T8. Rutas web en `web/correo_api.py` (`registrar_rutas_correo`): vista previa, confirmar con la firma, estado,
      historial y resolver un desconocido; modelos en `web/api_contract.py`; carril `correo` en `web/jobs.py`, sin
      `reanudar`; la confirmación rechaza lo que no venga de la sesión del navegador (sin `Origin` propio o con las
      cabeceras del ejecutor); filtro `_SinCorreoEnElRegistro` en `web/seguridad.py` y títulos de trabajo sin
      direcciones. Una orden del asistente o el texto de un documento que piden enviar dejan solo un borrador; ningún
      plan de `asistente/ejecutor.pasos` alcanza la ruta de confirmar (`GobiernoEquipo.autorizar_peticion` la
      rechaza). (RF-1, RF-5, RF-6, RF-7, RF-13)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_correo_web.py tests/test_contrato_api.py
      tests/test_asistente_equipo.py` en verde, montando las rutas en una `FastAPI()` de prueba, con doble clic (un
      solo trabajo), orden del asistente (sin envío) y una captura del registro y de los eventos sin ninguna dirección
      completa ni token.
- [ ] T9. Cableado mínimo en `web/app.py`, **pactado con el integrador f9**: las dos líneas de `registrar_rutas_correo`
      junto a `registrar_rutas_copia`; `docs/asistente/openapi.json`, `CODIGO_FUENTE.md` y el catálogo de la 090 al día.
      (RF-1)
      Hecho cuando: f9 da el visto bueno al diff de `web/app.py`, y `.venv/Scripts/python.exe -m pytest -q
      tests/test_web_api.py tests/test_correo_web.py tests/test_contrato_api.py tests/test_inventario.py
      tests/test_arquitectura_generada.py` en verde, con las rutas servidas por `create_app`.
- [ ] T10. Web: `frontend/src/api/correo.ts` y `frontend/src/features/powerfactory/EnviarInforme.tsx` (cuenta, para,
      cc, cco, asunto, cuerpo editable, adjuntos o enlace, avisos de validez y de contactos habituales, «Confirmar y
      enviar» desactivado mientras el trabajo corre, historial de envíos); «Enviar por correo» junto a «Descargar Word»
      en `InformesPF.tsx` y en `ArchivoInformes.tsx`, sin quitar nada; sin cuenta conectada, el botón dice por qué.
      (RF-1, RF-12, RF-13, RF-14)
      Hecho cuando: `npx tsc --noEmit -p frontend` sin errores, `npm run build` correcto, y revisión en un navegador
      real con el proveedor simulado (modo claro y oscuro, sin `localStorage`, sin «RF» ni jerga visibles), con
      captura guardada en la evidencia de la tarea.
- [ ] T11. Instructivo `docs/CORREO_OAUTH.md`: registrar la aplicación en Google Cloud (`gmail.send`) y en Azure
      (`Mail.Send`), con la URI de retorno local y dónde va la configuración, fuera del repositorio. (RF-2)
      Hecho cuando: el instructivo existe, lo enlaza `docs/MANUAL_COMANDOS.md`, y una prueba comprueba que no contiene
      identificadores ni secretos reales.
- [ ] T12. Prueba real controlada, tras el registro OAuth del usuario (decisión 1): un envío desde la web, con su cuenta,
      a una dirección del propio usuario, con su recibo; uno con Gmail y uno con Outlook si tiene las dos cuentas.
      (RF-2, RF-7, RF-8)
      Hecho cuando: el recibo real (clave, identificador del proveedor o `Message-ID`, estado `aceptado`, hora,
      destinatario y huella) queda en la evidencia de la tarea, y el correo aparece en «Enviados» de esa cuenta.
- [ ] T13. Validación: cada RF citado por al menos una prueba y en verde; la prueba con el simulado no acredita la
      integración real, que acredita T12. (Todos)
      Hecho cuando: `grep -rnoE "110:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-14.
