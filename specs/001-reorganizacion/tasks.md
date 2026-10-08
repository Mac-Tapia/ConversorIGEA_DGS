# Tareas — Spec 001

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.
Pendiente de aprobar la spec antes de empezar T1.

- [ ] T1. Línea base de RF-14: generar los DGS de referencia con los TXT reales (todos los
      alimentadores, `workers=1`) y guardar sus SHA-256 en `output/linea_base_001.json` (ignorado por git). (RF-14)
      Hecho cuando: existe el JSON y la prueba RF-14 pasa contra el código sin tocar.
- [ ] T2. `util.py` con `sha256_file`, `write_json_atomic`, `finite_or_none` y
      `nombre_seguro`, con sus pruebas; sustituir las copias de `igea_dgs`. (RF-4, RF-5)
      Hecho cuando: `pytest -q` en verde y el detector de duplicados no las lista.
- [ ] T3. Sustituir en `vnr_etl` las copias de hash, `_require_requests` y número finito. (RF-4)
      Hecho cuando: `pytest -q tests/test_vnr_etl.py` en verde.
- [ ] T4. `geography.make_transformer` único; `loads_create` lo usa y un CRS inválido da
      error con el nombre del CRS. (RF-6, RF-7)
      Hecho cuando: prueba de CRS inválido en verde y RF-14 sigue igual.
- [ ] T5. Mover `web/sources` a `igea_dgs/sources` con reexportación. (RF-1)
      Hecho cuando: `pytest -q tests/test_web_*.py` en verde sin tocar las pruebas.
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
