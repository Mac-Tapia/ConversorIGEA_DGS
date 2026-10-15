# Tareas — Spec 001

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.
Spec aprobada el 2026-10-08.

- [x] T1. Línea base de RF-14: generar los DGS de referencia con los TXT reales (todos los
      alimentadores, `workers=1`) y guardar sus SHA-256 en `output/linea_base_001.json` (ignorado por git). (RF-14)
      Hecho cuando: existe el JSON y la prueba RF-14 pasa contra el código sin tocar.
- [x] T2. `util.py` con `sha256_file`, `write_json_atomic`, `finite_or_none` y
      `nombre_seguro`, con sus pruebas; sustituir las copias de `igea_dgs`. (RF-4, RF-5)
      Hecho cuando: `pytest -q` en verde y el detector de duplicados no las lista.
      Hecho el 2026-10-08: el detector es ahora una prueba fija (`tests/test_util.py`).
      Fuera a propósito: `source_runs._atomic_json` (sin salto de línea final: cambiarla
      altera los ficheros de custodia ya escritos), `source_runs._sha256_copy` (copia y
      hashea a la vez) y `loads._number` (admite coma decimal y devuelve `nan`). Pendiente
      sin RF: cinco variantes de «SHA-256 de un JSON canónico» (`load_batch`,
      `reconstruction_service`, `powerfactory_metadata`, `source_runs`,
      `catalog_resolution`); unirlas cambia hashes ya guardados si difieren en algo.
- [x] T3. Sustituir en `vnr_etl` las copias de hash, `_require_requests` y número finito. (RF-4)
      Hecho cuando: `pytest -q tests/test_vnr_etl.py` en verde.
      Hecho el 2026-10-08. `_require_requests` no eran copias idénticas (cada una lanza su
      excepción): lo común pasa a `util.importar_opcional(modulo, error)`. El «número
      finito» de `catalogs/conductor.py` no lo era: dejaba pasar `nan` e `inf`, y un
      conductor con `X1 = nan` contaba como completo; ahora usa `finite_or_none`. La copia
      de `pipeline.py:485` ya no existía. `vnr_etl/web/app.py:252` hashea mientras recibe
      la subida (no es copia) y se retira en T11.
- [x] T4. `geography.make_transformer` único; `loads_create` lo usa y un CRS inválido da
      error con el nombre del CRS. (RF-6, RF-7)
      Hecho cuando: prueba de CRS inválido en verde y RF-14 sigue igual.
      Hecho el 2026-10-08: los cinco constructores (dos en `igea_dgs`, tres en `vnr_etl`)
      usan `make_transformer`, que da `ValueError` con los dos CRS. La web lo convierte en
      `UserError` (400) al crear SED. Sin pyproj, `loads_create` sigue dejando el GPS
      vacío a propósito. `tests/test_transformador.py` falla si aparece otro
      `Transformer.from_crs` en `src/`.
- [x] T5. Mover `web/sources` a `igea_dgs/sources` con reexportación. (RF-1)
      Hecho cuando: `pytest -q tests/test_web_*.py` en verde sin tocar las pruebas.
      Hecho el 2026-10-08. Los tipos de la instantánea (`SourceSnapshot`, `SourceFile`,
      `SourceMode`, `MODE_SLOTS`) pasan a `sources/snapshot.py`; la custodia
      (`create_source_run`, `load_source_run`) sigue en `web/source_runs.py`.
      Reexportan, hasta la spec 002: `web/sources/__init__.py`, `web/sources/vnr.py` y los
      tipos en `web/source_runs.py`. `tests/test_fuentes_sin_web.py` comprueba en otro
      proceso que importar los adaptadores no carga FastAPI.
- [x] T6. `cli.load_dataset` con `adapter_for`; el CLI acepta `--vnr-package` y pasa los
      alias al catálogo. (RF-1, RF-2, RF-3)
      Hecho cuando: pruebas de CLI con TXT (las dos disposiciones), MDB y VNR en verde.
      Hecho el 2026-10-08 (`tests/test_cli_fuentes.py`). El CLI construye la instantánea
      con `snapshot_from_paths`, sin copiar; VNR-GIS descomprime en una carpeta temporal
      que se borra al salir. Para igualar al CLI anterior, el adaptador TXT admite varios
      `equipment_extra` (en el orden indicado) y el MDB, `load_year`. Con una `.mdb` real,
      el CLI lee lo mismo que el lector directo; suite con las cinco variables: 977
      correctas. Fuera de T6: el CLI no bloquea alimentadores no listos como hace la web
      (`web/readiness.py`); si se quiere, es un requisito nuevo.
- [x] T7. Retirar la GUI Tkinter: `gui.py`, la orden `gui` del CLI, el script
      `igea-dgs-gui`, `run_gui_escritorio.bat` y `tests/test_gui_wiring.py`, tomando
      como referencia el commit `52974c8e`. (RF-16)
      Hecho cuando: una prueba comprueba que `igea_dgs.gui` no existe y que el CLI no
      ofrece `gui`, y `pytest -q` en verde.
      Hecho el 2026-10-08 (`tests/test_sin_gui.py`). También se retira `settings.py`, que
      solo usaba la ventana (la web guarda eso en cada `Workspace`); `test_settings.py`
      prueba ahora esa persistencia en la web. `version_key` se usa desde
      `powerfactory_env` (la de `gui.py` era copia). A diferencia de la referencia,
      `run_gui.bat` conserva su nombre por los accesos directos ya creados. El entorno
      instalado conserva `igea-dgs-gui.exe` hasta el próximo `pip install -e .`.
- [x] T8. `diagnose` y `reconstruct` como trabajos del carril `engine`; la cancelación
      conserva el dataset anterior. (RF-8, RF-9)
      Hecho cuando: pruebas de API (202 + Job, cancelación) en verde.
      Hecho el 2026-10-08 (`tests/test_web_reconstruction.py`). La selección se valida
      antes de encolar: un alimentador desconocido sigue siendo un 400 de la petición.
      La cancelación se comprueba entre pasos; el informe y el dataset se publican tras
      `JobContext.sin_retorno()`, que bajo el mismo cerrojo que `JobManager.cancel`
      decide si la cancelación llegó antes (se conserva lo anterior) o ya no entra (el
      trabajo acaba `done`, nunca «cancelado» con la reconstrucción publicada). Fuera de
      T8: la reconstrucción que lanza `convert` por su cuenta sigue sin cancelarse a
      mitad, como antes.
- [x] T9. Front: `startJob` para diagnosticar y reconstruir; `download()` con el mismo
      tratamiento de `detail`; quitar los métodos sin uso. (RF-8, RF-12, RF-13)
      Hecho cuando: `npx tsc --noEmit -p frontend` y `npm run build` correctos.
      Hecho el 2026-10-08. El panel muestra el resultado del último trabajo terminado
      y encadena la conversión solo si la reconstrucción acaba bien. Fuera: `sourceRuns`,
      `job` y `events`. `apiError` es común a `request()` y `download()`. La orden real
      es `npx tsc --noEmit -p .` desde `frontend/`: desde la raíz, `npx` no encuentra
      TypeScript. Pruebas de contrato en `tests/test_web_reconstruction_ui_contract.py`.
- [x] T10. `DgsExporter` por el motor. (RF-10)
      Hecho cuando: `pytest -q tests/test_vnr_etl.py` en verde con el DGS validado.
      Hecho el 2026-10-08. `export` = `canonical_to_cymdist` (el puente de la web) +
      `batch.convert_group`: un solo DGS con todos los alimentadores del modelo, con las
      reglas, la validación y la auditoría del motor; mismo DGS byte a byte que el motor
      directo. Conserva las puertas del perfil verificado y de la procedencia, y su
      `.manifest.json`; deja al lado la validación y el manifiesto del motor. Nuevo: se
      bloquea si el puente deja algo fuera (tramo sin alimentador, carga sin tramo), si
      un alimentador no está listo o si falta un CRS de trabajo proyectado; el escritor
      anterior escribía líneas sin tipo. Por eso el modelo «listo para producción» de
      las pruebas lleva ahora alimentador y conductor.
- [x] T11. Una sola API web y una sola cola; se retira el script `vnr-etl-web`. (RF-11)
      Hecho cuando: las pruebas de `vnr_etl.web` pasan contra la app principal.
      Hecho el 2026-10-08. `vnr_etl/web/app.py` es ahora `create_router`, un `APIRouter`
      bajo `/api/vnr` que `create_app` monta; sus trabajos (`export`, `download`) van al
      `JobManager` común, carril `engine`, con los estados de siempre (`done`, no
      `SUCCEEDED`). No se repite lo que la API ya tenía: `/api/health`, `/api/jobs/{id}`
      y `/api/vnr/publications` (que con `?refresh=true` sustituye a
      `/api/discovery/refresh`). Se retiran `vnr_etl/web/__main__.py`, el script y el
      token `VNR_WEB_TOKEN`: la API única tiene un solo modelo de acceso (T11b), y las
      rutas de VNR solo leen ficheros subidos o URL oficiales HTTPS. `vnr-etl web` abre
      la web única. Una prueba exige que ninguna ruta esté dos veces.
- [x] T11b. `create_app` decide las rutas locales según la interfaz de escucha, por
      defecto en cerrado. (RF-15)
      Hecho cuando: prueba de API con host de red → 403 en `/inputs/{slot}/path`, aunque
      la variable esté a `1`.
      Hecho el 2026-10-08 (`tests/test_web_api.py`). `create_app(host=...)`; sin él lee
      `IGEA_WEB_HOST`, que pone el lanzador (con `factory=True` uvicorn no pasa
      argumentos), y sin ninguno de los dos, cerradas: un `uvicorn --factory --host
      0.0.0.0` a mano también queda cubierto. Solo 127.0.0.1, `localhost` y `::1` las
      abren; `IGEA_WEB_SERVER_PATHS=0` las apaga en local, pero ya no las abre fuera.
- [x] T12. Validación: cada RF citado y en verde; RF-14 contra la línea base. (Todos)
      Hecho cuando: `grep -rnoE "001:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-16.
      Hecho el 2026-10-08. RF-1 a RF-16 citados por al menos una prueba, todas en verde.
      Suite con las cinco variables `IGEA_*`: 929 correctas y 18 omitidas (las
      comparaciones tramo a tramo TXT↔Access, que no son la misma exportación).
      `test_linea_base_001` se ejecutó, no se omitió: los DGS por alimentador y de la red
      unida son idénticos byte a byte a los de T1 (RF-14). Front: `npx tsc --noEmit -p .`
      (desde `frontend/`) y `npm run build` correctos. Spec cumplida.

## Cambio del 2026-10-08 (RF-17 a RF-21)

- [x] T13. La reconstrucción de la web sale a un módulo puro del motor, sin `Workspace`,
      para que la use también VNR. (RF-17)
      Hecho cuando: `pytest -q tests/test_web_reconstruction.py` en verde sin cambios.
      Hecho el 2026-10-08: `igea_dgs/reconstruction_pipeline.py` (`reconstruir_seleccion`,
      `catalogos_del_fichero`). Única prueba tocada: la de cancelación, que sustituía
      `repair_discontinuities` en el módulo web y ahora lo hace en el nuevo.
- [x] T14. El resolvedor completa un conductor con parámetros a medias sin descartar los
      que trae. (RF-18, RF-19)
      Hecho cuando: prueba con un conductor sin R0 ni Amps, con y sin catálogo.
      Hecho el 2026-10-08 (`tests/test_catalog_resolution.py`). Antes, una fila con el
      código bastaba para darlo por resuelto aunque le faltaran parámetros.
- [x] T15. Reconstrucción del modelo canónico VNR: alimentador por conectividad, fuente,
      tensión, fases, longitud, ubicación de cargas y CRS (UTM o sin geografía). (RF-17, RF-20)
      Hecho cuando: pruebas de cada caso, deterministas.
      Hecho el 2026-10-08: `vnr_etl/application/reconstruccion.py`. Alimentador por BFS
      multiorigen desde los tramos que lo tienen (gana el más cercano y, a igual
      distancia, el de nombre menor); islas sin ninguno, uno propio. Fuente en el nodo
      raíz si falta; si sobran, se conserva la primera. Tensión más frecuente de la red o
      la provisional de la política. Fases `ABC`. Longitud por geometría, por nodos o
      1 m. Carga fuera de la red, al nodo más cercano. CRS geográfico → zona UTM de sus
      coordenadas; desconocido → sin geografía y `CoordOrigen='sin_crs'`, para que el
      motor use la longitud del modelo. El puente pasa material y sección (atributos
      compatibles) y elige, por identificador, entre tramos del mismo alimentador en el
      nodo de una carga. `convert_group(include_geography=False)`, nuevo.
- [x] T16. `DgsExporter` y `VnrApplicationService.export` reconstruyen y exportan; B, C y
      D se informan sin bloquear; informe de reconstrucción junto al DGS. (RF-17, RF-21)
      Hecho cuando: los tres casos que antes bloqueaban exportan un DGS validado.
      Hecho el 2026-10-08 (`tests/test_vnr_etl.py`): modelo → `reconstruir_modelo` →
      puente → `reconstruir_seleccion` con el catálogo del proyecto (o
      `DgsExporter(catalogo=...)`) → `convert_group`. `<red>_reconstruccion.json` y su
      resumen en el manifiesto. Bloquean solo A, E (procedencia, perfil) y F. Nuevo
      estado `EXPORT_RECONSTRUCTED`. Las pruebas de T10 que exigían el bloqueo se
      sustituyen por las de RF-17 a RF-21.
- [x] T17. Validación: RF-17 a RF-21 citados y suite completa en verde, RF-14 igual.
      Hecho el 2026-10-08: suite con las cinco `IGEA_*`, 939 correctas y 18 omitidas (las
      de siempre); `test_linea_base_001` en verde.

## Segundo cambio del 2026-10-08 (RF-22 a RF-25)

- [x] T18. Procedencia reconstruida en `reconstruir_modelo`; perfil sin verificar y
      relectura con errores no bloquean; el servicio no bloquea por puertas A–F. (RF-22, RF-23, RF-24)
      Hecho cuando: un modelo sin procedencia ni perfil exporta un DGS validado y el
      manifiesto lo dice.
      Hecho el 2026-10-08. Huella del modelo para `source_fingerprint`, `source_sha256`,
      `schema_fingerprint` y `source_publication_id` (`DIRECT-…`); el resto,
      `DESCONOCIDO`. Manifiesto: `perfil_verificado`, `procedencia_reconstruida`,
      `roundtrip` (`PASS`/`FAIL`), `roundtrip_errors`, `avisos`. Un export escrito es
      `EXPORT_READY` o `EXPORT_RECONSTRUCTED`, nunca `BLOCKED`. Solo bloquean un modelo
      sin tramos y `require_simulator` sin evidencia.
- [x] T19. Deducción de CRS común (`vnr_etl.gis.crs.deducir_crs`), usada por la
      reconstrucción, `vnr-etl convert` y `/api/vnr/topology/build`. (RF-25)
      Hecho cuando: una capa en grados sin CRS y otra en metros sin CRS convierten.
      Hecho el 2026-10-08. De paso, dos rigideces previas: `canonicalize_sections` solo
      buscaba la geometría en `geometry` (las capas ArcGIS la traen en `__geometry__`) y
      se quedaba en grados aunque se dijera EPSG:4326; y la ruta web solo encontraba la
      capa de tramos si su nombre decía «tramo», cosa que una subida nunca cumple. Ahora
      las dos vías usan `pipeline.buscar_capa_de_tramos`.
- [x] T20. Validación: RF-22 a RF-25 citados, suite completa en verde y RF-14 igual.
      Hecho el 2026-10-08: 945 correctas y 18 omitidas (las de siempre); RF-14 en verde.

## Tercer cambio del 2026-10-08 (RF-26, RF-27)

- [x] T21. Lista única de formatos VNR-GIS en el servidor (`vnr_etl.connectors.registry`),
      publicada en `/api/health` con la casilla; la web la usa. (RF-26)
      Hecho cuando: prueba de que lo que ofrece la casilla es lo que acepta el servidor.
      Hecho el 2026-10-08: `FORMATOS_PAQUETE_VNR` = `.zip`, `.rar` y las fuentes del
      lector menos `.shp` suelto (necesita `.dbf` y `.shx`: va en un ZIP o RAR).
      `validate_vnr_package_file` la usa y nombra los formatos al rechazar. Etiqueta de
      la casilla: «Paquete o base VNR-GIS», con los formatos bajo ella.
- [x] T22. `igea_dgs.web.runtime --front` dice si `frontend/dist` está por detrás del
      código del front; `run_gui.bat` recompila en ese caso. (RF-27)
      Hecho cuando: prueba con un fichero del front más reciente que `dist`.
      Hecho el 2026-10-08 (`tests/test_web_runtime_front.py`). Probado además en `cmd`
      con una copia del lanzador: al día abre directo; con `api.ts` tocado, recompila y
      abre. Sin Node.js y con un `dist` viejo, avisa y abre el anterior en vez de cerrar.
- [x] T23. Validación: RF-26 y RF-27 citados, `tsc` y `build` correctos, suite en verde.
      Hecho el 2026-10-08: 951 correctas y 18 omitidas (las de siempre); RF-14 en verde.

## Cuarto cambio del 2026-10-15 (RF-28 a RF-33)

- [x] T24. `/api/health` publica `servidor` (PID, huella del código, trabajos en curso) y
      `POST /api/sistema/cerrar` cierra el servidor desde el lanzador. (RF-33)
      Hecho cuando: pruebas de la huella, del rechazo sin cabecera, desde fuera y con
      trabajos en curso, y del cierre aceptado.
      Hecho el 2026-10-15 (`tests/test_lanzador_web.py`).
- [x] T25. `igea_dgs.web` resuelve el puerto ocupado: reutiliza, reemplaza, respeta los
      trabajos, termina el colgado o cambia de puerto; abre el navegador cuando responde;
      `run_gui.bat` no pide tecla salvo error. (RF-28 a RF-32)
      Hecho cuando: una prueba por caso, con servidores falsos en puertos libres.
      Hecho el 2026-10-15; `test_web_api.py` ajustada: el puerto en manos de otro programa
      ya no sale con 2, solo si tampoco hay un puerto libre después.
- [x] T26. Validación: suite en verde y el acceso directo probado en Windows con la web ya
      abierta, con un servidor de otra versión y con el puerto en uso por otro programa.
      Hecho el 2026-10-15 con procesos reales en 8797 a 8799: el mismo código se reutiliza
      (sale con 0 al momento), otra versión sin trabajos se cierra por petición y el nuevo
      toma su puerto, y con `http.server` en el puerto arranca en el siguiente.
