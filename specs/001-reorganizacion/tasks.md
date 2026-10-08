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
- [ ] T6. `cli.load_dataset` con `adapter_for`; el CLI acepta `--vnr-package` y pasa los
      alias al catálogo. (RF-1, RF-2, RF-3)
      Hecho cuando: pruebas de CLI con TXT (las dos disposiciones), MDB y VNR en verde.
- [ ] T7. Retirar la GUI Tkinter: `gui.py`, la orden `gui` del CLI, el script
      `igea-dgs-gui`, `run_gui_escritorio.bat` y `tests/test_gui_wiring.py`, tomando
      como referencia el commit `52974c8e`. (RF-16)
      Hecho cuando: una prueba comprueba que `igea_dgs.gui` no existe y que el CLI no
      ofrece `gui`, y `pytest -q` en verde.
- [ ] T8. `diagnose` y `reconstruct` como trabajos del carril `engine`; la cancelación
      conserva el dataset anterior. (RF-8, RF-9)
      Hecho cuando: pruebas de API (202 + Job, cancelación) en verde.
- [ ] T9. Front: `startJob` para diagnosticar y reconstruir; `download()` con el mismo
      tratamiento de `detail`; quitar los métodos sin uso. (RF-8, RF-12, RF-13)
      Hecho cuando: `npx tsc --noEmit -p frontend` y `npm run build` correctos.
- [ ] T10. `DgsExporter` por el motor. (RF-10)
      Hecho cuando: `pytest -q tests/test_vnr_etl.py` en verde con el DGS validado.
- [ ] T11. Una sola API web y una sola cola; se retira el script `vnr-etl-web`. (RF-11)
      Hecho cuando: las pruebas de `vnr_etl.web` pasan contra la app principal.
- [ ] T11b. `create_app` decide las rutas locales según la interfaz de escucha, por
      defecto en cerrado. (RF-15)
      Hecho cuando: prueba de API con host de red → 403 en `/inputs/{slot}/path`, aunque
      la variable esté a `1`.
- [ ] T12. Validación: cada RF citado y en verde; RF-14 contra la línea base. (Todos)
      Hecho cuando: `grep -rnoE "001:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-16.
