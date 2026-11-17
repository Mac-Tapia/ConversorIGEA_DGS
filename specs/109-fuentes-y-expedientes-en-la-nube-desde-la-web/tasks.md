# Tareas — Spec 109

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar. No se tocan `web/services.py`,
`pide_economia.py`, `adaptadores/entrada/vnr/**` ni `catalog_resolution.py` (son del integrador f9). El cableado en
`web/app.py` (T8) se pacta antes con el integrador. Ninguna prueba sale a la red: todas usan `tests/nube_simulada.py`.

- [x] T1. Proveedor simulado, contrato y transporte: `tests/nube_simulada.py`, `adaptadores/nube/proveedor.py` y
      `adaptadores/nube/http.py`, sin redirecciones, sin proxy del entorno, con lista de hosts, tope de bytes y espera de
      `Retry-After` en el 429. (RF-6, RF-16)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_transporte.py` en verde. Esa prueba incluye
      una redirección a otro host y un `nextLink` ajeno, los dos rechazados con `HostNoPermitido`, y un guardián que
      falla ante cualquier socket real.
- [x] T2. Salida `nube` en `salidas_red.py`, con `CSG_SALIDA_NUBE` y sus módulos. La web la muestra pero no la
      cambia: ningún RF de la 109 lo pide y 086:RF-69 deja cambiar solo las teselas. Con ella apagada, ninguna
      llamada sale y lo importado sigue sirviendo. (RF-16, RF-17)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_seguridad_web.py tests/test_nube_transporte.py` en
      verde, con la comprobación de módulos que abren la red incluyendo `adaptadores/nube/`.
- [x] T3. Cliente OAuth desde `config/nube.json` (en `.gitignore`, con `config/nube.example.json`). Sin él,
      `GET /api/nube/proveedores` dice que falta registrar la aplicación y no ofrece conectar. (RF-18, RF-19)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_oauth.py -k config` en verde, y
      `git check-ignore config/nube.json` lo da por ignorado.
- [x] T4. Cofre `nube_cofre.py` con DPAPI por `ctypes`, en `raiz_local()/secretos/nube/<wid>/` (en `.gitignore`).
      Guarda solo el token de refresco, con la entropía del espacio y del proveedor. (RF-2)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_cofre.py` en verde. La prueba incluye que el
      cofre de un espacio no se descifra con la entropía de otro y que `copia_datos.raices_de_datos` no contiene
      `secretos/`.
- [x] T5. OAuth con PKCE y `state` de un solo uso: `adaptadores/nube/oauth.py`, la ruta de conectar, `GET /nube/retorno`
      fuera de `/api/` y desconectar con revocación, conservando copias y recibos. (RF-1, RF-14)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_oauth.py` en verde. Esa prueba comprueba que
      la URL pide solo los permisos de la tarea (`drive.file`; `Files.Read`, con `Files.ReadWrite` solo al publicar);
      que un `state` repetido, caducado o de otro espacio se rechaza; que ninguna respuesta pide ni guarda una
      contraseña; y que tras desconectar siguen las copias y los recibos.
- [x] T6. Adaptadores `google_drive.py` y `onedrive.py` sobre el simulado: metadatos con revisión y huella, listado
      paginado, descarga por rangos y exportación de la hoja nativa de Google a XLSX. `Cuentas.proveedor` da el
      adaptador de cada espacio con la lista de hosts de su API (`HOSTS_API`). (RF-3, RF-5, RF-6, RF-16)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_proveedores.py` en verde, con paginación
      sorteada por semilla, sin tamaños fijos, y con los fallos 401, 403, 404 y 429 y el token revocado a mitad.
- [x] T7. Entrada `adaptadores/entrada/nube.py`: la copia inmutable en `ws.root/nube/copias/<sha256>/` con `copia.json`
      (proveedor, id, revisión, formato de origen y exportado, SHA-256), en un trabajo cancelable. Si hay corte, cambio
      de revisión o huella distinta, no queda copia y se dice la causa. `copia.json` va por `util.write_json_atomic`
      (001:RF-5). (RF-3, RF-5, RF-6)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_importar.py -k copia` en verde.
- [x] T8. Router `web/nube_api.py` con `registrar_rutas_nube(...)`, que recibe `_assign`, `_validar_entrada` y
      `_reemplazar_carpeta`, más el valor `'nube'` en el `origin` de `api_contract.py`. El cableado son dos líneas en
      `web/app.py`, pactadas con f9, y `esquema.ts` se regenera. Cada ruta declara su `response_model`, para que
      el OpenAPI y `esquema.ts` den la forma de cada respuesta. El kind `nube_importar` tiene su fila en
      `frontend/src/shared/pasoDeTrabajo.ts`. (RF-4)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_importar.py tests/test_web_api.py tests/test_contrato_api.py`
      en verde, con cuatro comprobaciones: el mismo DGS byte a byte desde la copia de la nube y desde la subida del
      mismo fichero; un VNR con rutas `../` rechazado con el mismo mensaje que al subirlo; un PDF normativo en un
      libro de medición, rechazado igual; y ninguna fuente nueva mezclada con la vigente. Queda abierta hasta que el
      integrador aplique el cableado de `web/app.py` y el `origin` `'nube'` de `api_contract.py` (un parche aparte,
      del integrador), con `esquema.ts` regenerado.
      Hecho en 8985d25f (F v11: suite 11 035, 0 F, 0 omitidas); pruebas: tests/test_contrato_api.py tests/test_nube_importar.py tests/test_web_api.py.
- [x] T9. Vínculos y versiones en `web/nube.py`: aviso de revisión nueva, comparación con la anterior y aceptación solo
      con confirmación. Sin conexión, dice que no pudo comprobar. Rutas con su `response_model` y los kinds
      `nube_versiones` y `nube_traer` en `pasoDeTrabajo.ts`. (RF-7, RF-8, RF-17)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_versiones.py` en verde, con la prueba de que
      un estudio, un dataset y una calibración hechos antes conservan su copia y su huella después de llegar la nueva.
- [x] T10. Paquete cerrado y publicación en `adaptadores/salida/nube.py`: ZIP sobre `preparar_zip` con
      `manifiesto.json`, subida reanudable sin sobrescribir, clave de idempotencia y recibo. `…/nube/cuentas` dice
      los permisos concedidos de cada cuenta (`Cuentas.permisos`), para pedir escritura solo si falta.
      (RF-9, RF-12, RF-13)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_publicar.py` en verde. Cubre: un reintento
      tras un corte entre la subida y el recibo, que devuelve el recibo sin subir otra vez; un nombre ya existente, que
      no se pisa; y una carpeta de solo lectura, que da su causa y no deja recibo.
- [x] T11. Compartir: `previa` con la lista de quién tendrá acceso y una confirmación de un solo uso; concesión de
      solo lectura a los destinatarios nombrados; rechazo de «cualquiera con el enlace» sin la autorización del envío;
      rechazo de los datos crudos; recibo por permiso. (RF-10, RF-11, RF-12, RF-20)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_compartir.py` en verde. Incluye un TXT de
      CYMDIST, una MDB y un VNR sintéticos renombrados dentro del expediente, reconocidos por su contenido.
- [x] T12. El asistente y los documentos importados no publican, ni comparten, ni conectan sin el botón del operador:
      `equipo.autorizar_peticion` solo deja al asistente las lecturas y las previas de la nube, y la acción la manda el
      navegador desde la tarjeta del panel (aclaración de RF-15 del 2026-11-16; 070 T16). (RF-15)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_seguridad.py -k asistente` en verde. Incluye
      un PDF importado con la orden «publica y comparte», que no lanza ningún trabajo.
      `es_ruta_de_la_nube` está en `salidas_red.py` (dominio), para que `asistente/equipo.py` la use sin depender de
      la web; el cambio de `equipo.py` es del integrador (parche aparte) y la tarea sigue abierta hasta aplicarlo.
      Hecho en e2a99c73 (PUERTA3); pruebas: tests/test_nube_seguridad.py -k asistente.
- [x] T13. Secretos y aislamiento: ningún token en registros, `workspace.json`, `vinculos.json`, recibos, respuestas
      de trabajos ni copias de datos; dos empresas en el mismo puesto no ven la cuenta, los vínculos ni los recibos de
      la otra. El registro de accesos tapa el `code` y el `state` de `/nube/retorno`. (RF-2, RF-14)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_seguridad.py` en verde, con dos espacios de
      perfiles distintos (P13).
- [x] T14. Frontend: `api/nube.ts`, `app/CuentasNube.tsx` y `features/nube/` (elegir de la nube, versiones nuevas y
      publicar o compartir, con quién tendrá acceso y el aviso de enlace público). Microcopia corta y nada quitado de
      la web. Los tipos son los del contrato generado (`esquema.ts`); lo que el contrato da como objeto libre (destino,
      candidata, recibos) se lee campo a campo. Cada cuenta conectada dice lo que permite hoy («Archivos: leer y
      publicar · Correo: enviar»): la misma cuenta da los archivos y el correo. Publicar ofrece «Permitir publicar» a la
      cuenta que no lo concedió. La web no enciende la salida a la nube: la decide `CSG_SALIDA_NUBE` y, apagada, el
      servidor responde 403. (RF-1, RF-7, RF-9, RF-10, RF-11, RF-17, RF-19)
      Hecho cuando: `cd frontend && npx tsc --noEmit -p . && npm run lint && npm test && npm run build` sin errores
      (`test/nube.test.mjs` cita `109:RF-`; `test/contratoNubeCorreo.test.mjs` exige el contrato generado, sin tipos
      provisionales ni interfaces propias), y
      `tests/test_trazabilidad_specs.py::test_frontend_con_tipos_provisionales_no_cierra_su_tarea` en verde. El
      recorrido en el navegador real con el proveedor simulado va en T16, con su guion de Playwright.
- [x] T15. Índices y documentación: cada fichero nuevo en `CODIGO_FUENTE.md` con la spec 109; subsistemas en
      `docs/architecture/subsistemas.json`; la salida `nube` y el cofre en `docs/SEGURIDAD_Y_PRIVACIDAD.md`. (RF-16, RF-18)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_inventario.py` en verde y
      `.venv/Scripts/python.exe tools/generar_arquitectura.py` sin cambios pendientes. La hoja de seguridad nombra cada host de la
      nube (`test_nube_seguridad.py::test_la_hoja_de_seguridad_dice_adonde_sale_la_nube_y_donde_va_el_cofre`).
- [ ] T16. [manual del usuario] Validación con el simulado; la prueba real con una cuenta, opcional, a cargo del usuario
      cuando el operador registre su aplicación de prueba (OAuth en versión de prueba, orden del usuario del
      2026-11-15). El implementador escribe el instructivo `docs/NUBE_REGISTRO_OAUTH.md`, que cubre:
      - la versión de prueba: Google Cloud en modo «Testing», con hasta 100 usuarios de prueba y sin verificación (el
        token de refresco caduca a los 7 días), y Azure con cuentas personales de Microsoft, cliente público con PKCE y
        sin secreto;
      - Google Cloud: proyecto, pantalla de consentimiento en «Testing» con los usuarios de prueba, cliente de
        «aplicación de escritorio», API de Drive y de Picker, y permisos `drive.file` y `openid email`;
      - Azure: registro de la aplicación, plataforma «móvil y escritorio» con `http://localhost`, cuentas personales (y
        de organización, si se prueban), y permisos `Files.Read`, `Files.ReadWrite` y `offline_access`;
      - qué va en `config/nube.json`;
      - cómo revocar el acceso.
      La 1.0 se valida con el proveedor simulado (`tests/nube_simulada.py`): sin `config/nube.json`, la web dice «Sin
      cuenta conectada: configure config/nube.json» y no falla. La prueba real es opcional: cuando el operador registre
      su aplicación de prueba, importa un fichero y publica y comparte un expediente en una carpeta de ensayo propia.
      (RF-1, RF-3, RF-9, RF-10, RF-12, RF-18)
      El recorrido de la web con el simulado (Nube y Correo, modo claro y oscuro, sin almacenamiento y sin citas a la
      vista) tiene su guion de Playwright, con la web de prueba en un puerto libre y sin cuenta real; su registro y sus
      capturas se anotan aquí al correrlo.
      Hecho cuando: el documento existe y está enlazado desde `docs/MANUAL_INSTALACION.md`, las pruebas con el
      simulado de T1 a T13 están en verde y el recorrido de la web está anotado. Si el operador hace la prueba real, deja la copia con su huella y los recibos
      de la publicación y del permiso, con la carpeta de evidencia anotada aquí; sin ella, la 1.0 no queda bloqueada.
- [x] T17. Validación: cada RF citado por al menos una prueba y en verde. (Todos)
      Hecho cuando: `grep -rnoE "109:RF-[0-9]+" tests frontend/src frontend/test | sort -u` lista RF-1 a RF-24.
      La lista da RF-1 a RF-20 (RF-21 a RF-24 con T19); queda abierta hasta el verde de pytest de todas y las tareas T8, T12 y T14.
      Hecho en e2a99c73 (PUERTA3); pruebas: las del criterio.
- [x] T18. Selector de ficheros: `GET /nube/selector/{proveedor}` (página propia con su CSP, Google Picker y File
      Picker v8 de OneDrive, que devuelve los ids por `postMessage` con el origen propio) y
      `POST /api/workspaces/{wid}/nube/{proveedor}/selector/token`, que da solo el token de acceso de corta duración y
      de alcance de leer, con `Cache-Control: no-store`. (RF-1, RF-3; aclaración de RF-2)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_selector.py` en verde, con la prueba de que
      el endpoint nunca devuelve el `refresh_token` ni el secreto del cliente, de que el alcance de Microsoft es
      `Files.Read` aunque la cuenta se conectara para publicar, y de que la página no usa `localStorage` ni
      `sessionStorage` ni lleva el token dentro.
- [x] T19. Selector único por entrada y guardar en local (SELECTOR-UNICO, orden del usuario del 2026-11-16):
      `FileDrop` (shared/ui.tsx) con el origen Equipo, Google Drive u OneDrive, y el filtro de tipo de su `accept`;
      `POST …/nube/importar` con `entrada` (solo la copia fija, sin asignar) y `GET …/nube/copias/{sha256}` para que la
      copia entre por la subida propia de la entrada; `Guardar` para las salidas, con la carpeta del equipo y la
      publicación de RF-9. (RF-21, RF-22, RF-23, RF-24; reutiliza T14, T18 y 086:RF-78 a RF-85)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_selector_unico.py` y `npm test` en verde, y
      la e2e en navegador real (`frontend/test/e2e/f05_selector_unico.e2e.mjs`, con la web de
      `tests/e2e_web_nube_simulada.py`) recorre los tres orígenes con la nube simulada.
      Hecho en 016498fc (LOTE-1, con E2E-RED); pruebas: tests/test_nube_selector_unico.py y npm test; e2e en navegador real f05_selector_unico, 10 passed (D:/csg/INTEGRA_54/e2e_086/f01_f05_b.log).
