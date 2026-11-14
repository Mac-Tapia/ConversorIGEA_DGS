# Tareas — Spec 109

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar. No se tocan `web/services.py`,
`pide_economia.py`, `adaptadores/entrada/vnr/**` ni `catalog_resolution.py` (son del integrador f9). El cableado en
`web/app.py` (T8) se pacta antes con el integrador. Ninguna prueba sale a la red: todas usan `tests/nube_simulada.py`.

- [ ] T1. Proveedor simulado, contrato y transporte: `tests/nube_simulada.py`, `adaptadores/nube/proveedor.py` y
      `adaptadores/nube/http.py`, sin redirecciones, sin proxy del entorno, con lista de hosts, tope de bytes y espera de
      `Retry-After` en el 429. (RF-6, RF-16)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_transporte.py` en verde. Esa prueba incluye
      una redirección a otro host y un `nextLink` ajeno, los dos rechazados con `HostNoPermitido`, y un guardián que
      falla ante cualquier socket real.
- [ ] T2. Salida `nube` en `salidas_red.py`, con `CSG_SALIDA_NUBE`, sus módulos y cambiable desde la web. Con ella
      apagada, ninguna llamada sale y lo importado sigue sirviendo. (RF-16, RF-17)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_seguridad_web.py tests/test_nube_transporte.py` en
      verde, con la comprobación de módulos que abren la red incluyendo `adaptadores/nube/`.
- [ ] T3. Cliente OAuth desde `config/nube.json` (en `.gitignore`, con `config/nube.example.json`). Sin él,
      `GET /api/nube/proveedores` dice que falta registrar la aplicación y no ofrece conectar. (RF-18, RF-19)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_oauth.py -k config` en verde, y
      `git check-ignore config/nube.json` lo da por ignorado.
- [ ] T4. Cofre `nube_cofre.py` con DPAPI por `ctypes`, en `raiz_local()/secretos/nube/<wid>/` (en `.gitignore`).
      Guarda solo el token de refresco, con la entropía del espacio y del proveedor. (RF-2)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_cofre.py` en verde. La prueba incluye que el
      cofre de un espacio no se descifra con la entropía de otro y que `copia_datos.raices_de_datos` no contiene
      `secretos/`.
- [ ] T5. OAuth con PKCE y `state` de un solo uso: `adaptadores/nube/oauth.py`, la ruta de conectar, `GET /nube/retorno`
      fuera de `/api/` y desconectar con revocación, conservando copias y recibos. (RF-1, RF-14)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_oauth.py` en verde. Esa prueba comprueba que
      la URL pide solo los permisos de la tarea (`drive.file`; `Files.Read`, con `Files.ReadWrite` solo al publicar);
      que un `state` repetido, caducado o de otro espacio se rechaza; que ninguna respuesta pide ni guarda una
      contraseña; y que tras desconectar siguen las copias y los recibos.
- [ ] T6. Adaptadores `google_drive.py` y `onedrive.py` sobre el simulado: metadatos con revisión y huella, listado
      paginado, descarga por rangos y exportación de la hoja nativa de Google a XLSX. (RF-3, RF-5, RF-6)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_proveedores.py` en verde, con paginación
      sorteada por semilla, sin tamaños fijos, y con los fallos 401, 403, 404 y 429 y el token revocado a mitad.
- [ ] T7. Entrada `adaptadores/entrada/nube.py`: la copia inmutable en `ws.root/nube/copias/<sha256>/` con `copia.json`
      (proveedor, id, revisión, formato de origen y exportado, SHA-256), en un trabajo cancelable. Si hay corte, cambio
      de revisión o huella distinta, no queda copia y se dice la causa. (RF-3, RF-5, RF-6)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_importar.py -k copia` en verde.
- [ ] T8. Router `web/nube_api.py` con `registrar_rutas_nube(...)`, que recibe `_assign`, `_validar_entrada` y
      `_reemplazar_carpeta`, más el valor `'nube'` en el `origin` de `api_contract.py`. El cableado son dos líneas en
      `web/app.py`, pactadas con f9, y `esquema.ts` se regenera. (RF-4)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_importar.py tests/test_web_api.py tests/test_contrato_api.py`
      en verde, con cuatro comprobaciones: el mismo DGS byte a byte desde la copia de la nube y desde la subida del
      mismo fichero; un VNR con rutas `../` rechazado con el mismo mensaje que al subirlo; un PDF normativo en un
      libro de medición, rechazado igual; y ninguna fuente nueva mezclada con la vigente.
- [ ] T9. Vínculos y versiones en `web/nube.py`: aviso de revisión nueva, comparación con la anterior y aceptación solo
      con confirmación. Sin conexión, dice que no pudo comprobar. (RF-7, RF-8, RF-17)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_versiones.py` en verde, con la prueba de que
      un estudio, un dataset y una calibración hechos antes conservan su copia y su huella después de llegar la nueva.
- [ ] T10. Paquete cerrado y publicación en `adaptadores/salida/nube.py`: ZIP sobre `preparar_zip` con
      `manifiesto.json`, subida reanudable sin sobrescribir, clave de idempotencia y recibo. (RF-9, RF-12, RF-13)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_publicar.py` en verde. Cubre: un reintento
      tras un corte entre la subida y el recibo, que devuelve el recibo sin subir otra vez; un nombre ya existente, que
      no se pisa; y una carpeta de solo lectura, que da su causa y no deja recibo.
- [ ] T11. Compartir: `previa` con la lista de quién tendrá acceso y una confirmación de un solo uso; concesión de
      solo lectura a los destinatarios nombrados; rechazo de «cualquiera con el enlace» sin la autorización del envío;
      rechazo de los datos crudos; recibo por permiso. (RF-10, RF-11, RF-12, RF-20)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_compartir.py` en verde. Incluye un TXT de
      CYMDIST, una MDB y un VNR sintéticos renombrados dentro del expediente, reconocidos por su contenido.
- [ ] T12. El asistente y los documentos importados no publican, ni comparten, ni conectan: `equipo.autorizar_peticion`
      rechaza toda ruta de la nube, también con el plan confirmado. (RF-15)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_seguridad.py -k asistente` en verde. Incluye
      un PDF importado con la orden «publica y comparte», que no lanza ningún trabajo.
- [ ] T13. Secretos y aislamiento: ningún token en registros, `workspace.json`, `vinculos.json`, recibos, respuestas
      de trabajos ni copias de datos; dos empresas en el mismo puesto no ven la cuenta, los vínculos ni los recibos de
      la otra. (RF-2, RF-14)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_nube_seguridad.py` en verde, con dos espacios de
      perfiles distintos (P13).
- [ ] T14. Frontend: `api/nube.ts`, `app/CuentasNube.tsx` y `features/nube/` (elegir de la nube, versiones nuevas y
      publicar o compartir, con quién tendrá acceso y el aviso de enlace público). Microcopia corta y nada quitado de
      la web. (RF-1, RF-7, RF-10, RF-11, RF-17, RF-19)
      Hecho cuando: `cd frontend && npx tsc --noEmit -p . && npm test && npm run build` sin errores
      (`test/nube.test.mjs` cita `109:RF-`), y el recorrido en el navegador real con el proveedor simulado queda anotado
      en esta tarea.
- [ ] T15. Índices y documentación: cada fichero nuevo en `CODIGO_FUENTE.md` con la spec 109; subsistemas en
      `docs/architecture/subsistemas.json`; la salida `nube` y el cofre en `docs/SEGURIDAD_Y_PRIVACIDAD.md`. (RF-16, RF-18)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_inventario.py` en verde y
      `.venv/Scripts/python.exe tools/generar_arquitectura.py` sin cambios pendientes.
- [ ] T16. [manual del usuario] Registro de la aplicación OAuth y prueba real controlada, a cargo del usuario. El
      implementador escribe el instructivo `docs/NUBE_REGISTRO_OAUTH.md`, que cubre:
      - Google Cloud: proyecto, pantalla de consentimiento en modo de prueba, cliente de «aplicación de escritorio»,
        API de Drive y de Picker, y permisos `drive.file` y `openid email`;
      - Azure: registro de la aplicación, plataforma «móvil y escritorio» con `http://localhost`, cuentas personales y
        de organización, y permisos `Files.Read`, `Files.ReadWrite` y `offline_access`;
      - qué va en `config/nube.json`;
      - cómo revocar el acceso.
      El usuario registra la aplicación, importa un fichero y publica y comparte un expediente en una carpeta de ensayo
      propia. (RF-1, RF-3, RF-9, RF-10, RF-12, RF-18)
      Hecho cuando: el documento existe y está enlazado desde `docs/MANUAL_INSTALACION.md`, y la prueba real deja
      la copia con su huella y los recibos de la publicación y del permiso, con la carpeta de evidencia anotada aquí.
      La prueba con el proveedor simulado no sustituye esta.
- [ ] T17. Validación: cada RF citado por al menos una prueba y en verde. (Todos)
      Hecho cuando: `grep -rnoE "109:RF-[0-9]+" tests frontend/src frontend/test | sort -u` lista RF-1 a RF-20.
