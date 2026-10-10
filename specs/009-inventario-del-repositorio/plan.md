# Plan — Spec 009

## Módulos

| Fichero | Cambio | RF |
| --- | --- | --- |
| `CODIGO_FUENTE.md` | Índice completo: una tabla por carpeta (`src/igea_dgs`, sus subpaquetes, `src/vnr_etl`, `tools/`, `frontend/src`), con la ruta entre comillas invertidas, qué hace y su spec. Los documentos, con su vigencia. | RF-1 |
| `tests/test_inventario.py` (nuevo) | Compara `git ls-files` con el índice; importaciones de `tests/` en `tools/`; docstring y `--help` de cada herramienta; estado de las specs y RF citados. | RF-2, RF-3, RF-5 a RF-11 |
| `tools/` | Retira las 10 de RF-4 con `git rm` (quedan en el historial). `_validate_selection_fidelity.py` pasa a `fidelidad_seleccion.py`, con argumentos en vez de rutas fijas y en español. Docstrings en español en `apply_catalog_to_model.py`, `compare_schema.py` y `suggest_line_type_aliases.py`. | RF-4, RF-6, RF-7, RF-8 |
| `docs/MANUAL_COMANDOS.md`, `README.md` | Órdenes y herramientas; pestaña de cargas en tres pasos; perfil de empresa. | RF-12, RF-13 |
| `src/igea_dgs/`, `src/vnr_etl/` | Quita 17 funciones y clases de nivel superior que nada usaba (`access.list_networks`, `batch.BatchCancelled`, `dgs._node_degrees`, `dgs._meter_span`, `model.UnresolvedLineTypesError`, `reglas.preparar_dataset_reconstruido`, `studies.estudios_ligeros/pesados`, tres `_import_*` del CLI VNR, `doctor.run_doctor`, `logging.JsonlSink/MemorySink`, `pipeline.resolve_schema/fingerprint_layers/add_loads`) y la rama `if False` de `doctor._native_status`. Docstring a los 8 módulos del núcleo que no lo tenían. | RF-1 |
| `tools/show_pf_diagram.py`, `tools/suggest_line_type_aliases.py` | El alimentador `AL104` y tres códigos de Electro Dunas dejan de ser valores por defecto. | RF-8 |
| `config/line_type_aliases.json`, `.gitignore` | Fuera de git: alias de una distribuidora. | RF-14 |
| `specs/004-*/tasks.md` | T8 marcada: todos sus RF ya los cita una prueba. | RF-11 |

## Decisiones

- **El índice es `CODIGO_FUENTE.md`**, que ya existía: un segundo inventario sería otro
  duplicado. *Descartado:* generarlo con un guion, porque lo valioso es la frase de qué
  hace cada fichero y su spec, que no se puede deducir.
- **`--help` se ejecuta en un subproceso** con `src` y `tools` en el `PYTHONPATH` y un
  tiempo límite: así se ve que importar la herramienta no lee datos ni abre DIgSILENT.
- **Una spec «implementada» se reconoce por sus tareas**: todas marcadas salvo las que
  dicen «a cargo del usuario» o «la hace el usuario».

## Pruebas

- `tests/test_inventario.py`, sin datos reales.
