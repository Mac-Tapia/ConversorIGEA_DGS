# Plan — Spec 001

Lee: `docs/constitution.md`, `specs/001-reorganizacion/spec.md` y el diagnóstico
`docs/DIAGNOSTICO_SDD_2026-10-07.md` (§3 backend, §4 frontend).

## Contexto técnico

- Entrada: `src/igea_dgs/web/sources/{base,txt,mdb,vnr}.py` (el diseño bueno),
  `src/igea_dgs/cli.py:119` y `src/igea_dgs/gui.py:776-800` (las copias).
- Utilidades copiadas: ver la tabla B5 del diagnóstico.
- Trabajos: `src/igea_dgs/web/app.py:542-554` (`diagnose`, `reconstruct` síncronos),
  `web/jobs.py` (`JobManager`, carril `engine`).
- VNR: `src/vnr_etl/exporters/dgs.py`, `src/vnr_etl/web/app.py`,
  `src/vnr_etl/application/cymdist_bridge.py` (el puente bueno).

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| A. Utilidades comunes | nuevo `src/igea_dgs/util.py` (`sha256_file`, `write_json_atomic`, `finite_or_none`, `nombre_seguro`); `geography.make_transformer` | RF-4, RF-5, RF-6 |
| B. CRS inválido | `loads_create.py:810-830` usa `geography.make_transformer` y deja propagar el error | RF-7 |
| C. Adaptadores de entrada | `web/sources/` pasa a `src/igea_dgs/sources/`; `web/sources/__init__.py` reexporta; `cli.load_dataset` y `gui.py` llaman a `adapter_for` | RF-1, RF-2, RF-3 |
| D. Trabajos | `diagnose`/`reconstruct` con `JobManager.submit(lane='engine')`; front con `startJob` | RF-8, RF-9 |
| E. Front | `api.ts`: `download()` reutiliza la extracción de `detail` de `request()`; quitar `sourceRuns`, `events`, `job` | RF-12, RF-13 |
| F. VNR a DGS | `DgsExporter.export` = puente + `batch.convert_selection` | RF-10 |
| G. Una API | `vnr_etl/web` como `APIRouter` montado en `web/app.py` sobre `JobManager`, o retirado | RF-11 |

## Decisiones

- `util.py` en `igea_dgs` y no en un paquete nuevo: `vnr_etl` ya importa de `igea_dgs`
  (perfil de esquema). Descartado: un paquete `common/`, que añade empaquetado sin ganar nada.
- Los adaptadores salen de `web/` porque el CLI no debe importar FastAPI. Se deja
  `web/sources/__init__.py` reexportando para no romper importaciones existentes.
  Descartado: que el CLI importe `igea_dgs.web.sources` (arrastra la capa web al CLI).
- El CLI usa los adaptadores sobre una instantánea (`SourceSnapshot`) construida a partir
  de las rutas de los argumentos, sin copiar los ficheros. Descartado: copiar como hace la
  web, porque duplica gigas de `.mdb` para una ejecución de un solo uso.
  [Ver T5: si `SourceSnapshot` exige copia, se separa la parte de validación.]
- F y G van al final y solo con las dudas resueltas: son los únicos cambios visibles para
  quien use `vnr-etl`.

## Comprobación contra la constitución

- P1 Determinismo y RF-14: antes de A se guardan los DGS de referencia (T1) y cada fase
  compara contra ellos.
- P3 Dos disposiciones: C toca la entrada, así que se prueba con `ExportSpec(layout='completo')`.
- P5 Una sola vía: es el objetivo de toda la spec.
- P7 Nada largo en HTTP: D.
- P9 Datos de la distribuidora: los DGS de referencia de T1 se guardan fuera del
  repositorio (`output/`, que está en `.gitignore`), nunca en `tests/`.

## Estrategia de pruebas

- Pruebas nuevas citan su requisito: `"""001:RF-n — …"""`.
- RF-14: prueba que regenera con los TXT reales y compara los hash con los guardados en T1;
  se omite sin las variables `IGEA_*`, como el resto de pruebas reales.
- C: las pruebas existentes de `tests/test_web_*` y del CLI deben pasar sin cambios.

## Riesgos

- La GUI Tkinter tiene poca cobertura: el cambio en C se comprueba a mano abriéndola y
  cargando una entrega.
- Mover `web/sources` puede romper importaciones en pruebas: la reexportación lo cubre.
