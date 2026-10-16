# Plan — Spec 002

Lee: `docs/constitution.md`, `specs/001-reorganizacion/spec.md` (cumplida), esta spec y
`CODIGO_FUENTE.md`, que lista cada módulo con su spec (spec 009).

Estado: propuesto el 2026-10-10, pendiente de aprobar. No se ha movido código todavía.

## Punto de partida (medido el 2026-10-10)

- **Cruces entre paquetes:** 31 importaciones entre `igea_dgs` y `vnr_etl`, en los dos
  sentidos. `vnr_etl` usa del motor `dataset`, `geography`, `reconstruction`, `util`,
  `batch`, `coordenadas`, `reconstruction_pipeline`, `reglas`, `schema`, `validate` y
  `web.jobs`; el motor usa de `vnr_etl` `pipeline`, `cymdist_bridge`, `discovery.*`,
  `connectors.*` y `web.app`.
- **Ciclos (RF-4):** `model` ↔ `puentes`, `catalog_resolution` ↔ `reconstruction`,
  `web.source_runs` ↔ `web.workspace`, `web.reconstruction_service` ↔ `web.services` y
  `web` ↔ `web.app`.
- **Nombres privados importados de otro módulo (RF-5):** 12 (sin contar `__version__`):
  `batch` ← `model._tension_de_fuente`; `cargas_pf` ← `loads._normalise`, `_number`,
  `_power_conflict`, `_resolve_power`; `oraculo` ← `dgs._tr2_curmg_pct`, `_tr2_losses_kw`,
  `_tr2_strn_mva`; `reglas` ← `model._calc_p_q`; `validate` ← `dgs._line_neighbors`;
  `web.source_scope` ← `vnr_etl.pipeline._geojson_rows`, `_period_key`.
- **Convenciones de Electro Dunas en el código (RF-31 a RF-34):** `EPSG:32718` como valor
  por defecto en 6 módulos de `src/` (`batch`, `cli`, `geography`, `web.app`,
  `web.services`, `web.workspace`) y 7 herramientas (`accept_three_sources`,
  `apply_catalog_to_model`, `base_scenario`, `build_system_grid`, `convertir_grupos_mdb`,
  `linea_base_dgs`, `prueba_representacion`); `IN111` por defecto en
  `accept_three_sources`; la exclusión de SED `M…` en `reglas`/`trafomix`; la escala NA205
  en `dgs`. `reglas` importa `powerfactory_env` solo por `project_root`.
- **Perfil de empresa:** existe `config/perfil_empresa.json` (spec 005) con una sola
  clave, `carpeta_proyectos_pf`, leída por `carpeta_pf.nombre_de_perfil`.
- **Reexportaciones temporales:** `igea_dgs.web.sources` e `igea_dgs.web.sources.vnr`.

## Capas

De abajo arriba; una capa solo importa de las que tiene debajo (RF-1, RF-2).

| Capa | Qué va | Módulos de hoy |
| --- | --- | --- |
| `dominio` | El modelo de red y las reglas puras, sin E/S ni dependencias pesadas | `model`, la estructura de `dataset` (`CymdistDataset`, sin el lector), `naming`, `puentes`, `sed_potencia`, `trafomix`, `coordenadas`, `reconstruction`, `reconstruction_topology`, `catalog_resolution`, `catalog_data`, `ajuste_cabecera`, `economia`, `huella`, el perfil de empresa (nuevo) |
| `puertos` | Interfaces y su versión | `LectorDeRed` (de `sources/base.py`), `EscritorDeRed`, `Estudio`, `SesionPowerFactory` (RF-7) |
| `aplicacion` | Casos de uso que combinan puertos | `batch`, `reglas`, `combine`, `reconstruction_pipeline`, `inventory`, `catalog`, `catalog_merge`, `demanda_medida`, `cargas_pf` (plan), `studies`, el registro de módulos (nuevo) |
| `adaptadores` | Implementaciones de los puertos | entrada: el lector de `dataset`, `access`, `study`, `identify`, `loads`, `sources/*`, `vnr_etl` entero (RF-6); salida: `dgs`, `schema` y `schemas/`, `validate`, `export_tables`, `geography` (pyproj), `feeder_metadata`, `preview`; PowerFactory: `powerfactory_env`, `powerfactory_metadata`, `carpeta_pf`; estudios: `oraculo` (pandapower) |
| `presentacion` | Quien habla con el usuario | `cli`, `web/*`, el CLI y las rutas de `vnr_etl` |

`util` (SHA-256, JSON atómico, números) va a `dominio`: no tiene dependencias. Los guiones
de `tools/` que se ejecutan con el intérprete de PowerFactory quedan fuera del paquete,
como hoy: son procesos aparte que reciben un plan JSON (P7).

## Decisiones

- **La comprobación de capas es una prueba de la suite** (`tests/test_capas.py`), con
  `ast` y la tabla módulo → capa en `pyproject.toml` (`[tool.igea_dgs.capas]`), y tarda
  menos de 10 s (requisito no funcional). Mientras dure la migración lleva una lista de
  excepciones medidas que solo puede encoger: una violación nueva falla, una retirada
  obliga a quitarla de la lista. *Descartado:* `import-linter`, una dependencia más
  para lo que son 80 líneas, y que no comprueba RF-5 ni la universalidad (RF-34).
- **Se rompen primero los ciclos y los privados**, en su sitio de hoy: son cambios
  pequeños y verificables con la línea base, y después mover ficheros no arrastra nada.
- **El perfil de empresa crece en `config/perfil_empresa.json`**, el que ya existe (spec
  005): `crs_origen`, `patron_sed_medicion` (regex), `escala_diagrama`, `forma_alimentador`.
  Se incluye `config/perfiles/electro_dunas.json` como un perfil más (RF-35), sin datos
  de la red, solo convenciones; la spec 009 (RF-14) se ajusta para admitir esa carpeta.
  Sin perfil ni CRS en la entrada, la web y el CLI piden el CRS (RF-32) en vez de suponer
  `EPSG:32718`; la línea base se regenera con el perfil de Electro Dunas, no con un valor
  por defecto.
- **Entry points en `pyproject.toml`**, grupo `igea_dgs.modulos`, también para los
  lectores y el escritor propios (RF-9). El registro se resuelve una vez en el proceso
  principal y se pasa a los hijos con `workers>1` (RF-29). Lista de permitidos en
  `config/modulos_permitidos.json`, sin ruta web que la cambie (RF-23, RF-24).
- **Mover sin cambiar comportamiento:** cada movimiento deja una reexportación en la ruta
  vieja hasta la tarea de limpieza (RF-21), y cada tarea compara la línea base de DGS
  byte a byte (`tools/linea_base_dgs.py`, RF-20).
- **`vnr_etl` entra como `igea_dgs.adaptadores.entrada.vnr`** con su CLI (`vnr-etl`, RF-22)
  apuntando a la ruta nueva; `VNR-GIS.md` sigue siendo su diseño.
- **Tipos del front generados** desde `/openapi.json` con `openapi-typescript` (dependencia
  de desarrollo de npm) en `frontend/src/api/esquema.ts`; una prueba de Python regenera el
  esquema y lo compara (RF-16, RF-17). Exige que las respuestas de la API tengan modelos
  Pydantic, que hoy son `dict`: es la tarea más larga del front.
- **Fronteras del front** con ESLint y `eslint-plugin-boundaries` (RF-19).

## Riesgos

- Mover `dataset` parte la clase del lector: es el módulo que más importan (motor,
  `vnr_etl`, pruebas). Se hace en dos pasos, con reexportación.
- Los pickles de `workers>1` llevan rutas de módulo: la línea base con `workers=4`
  detecta cualquier diferencia (P1).
- Pedir el CRS cambia el uso de quien hoy no lo indica: el aviso dice qué perfil crear.

## Pruebas

- `tests/test_capas.py`: capas, ciclos, privados, universalidad (RF-2 a RF-5, RF-34).
- `tests/test_modulos.py`: descubrimiento, orden, exclusiones, duplicados, versiones,
  permitidos, dependencias ausentes, entry points desfasados, hijos con `workers>1`
  (RF-8 a RF-15, RF-23 a RF-30), con paquetes falsos instalados en `tmp_path`.
- `tests/test_perfil_empresa.py`: dos perfiles sobre la misma red sintética (RF-36), sin
  CRS (RF-32), sin patrón (RF-33), manifiesto (RF-37).
- `tests/test_contrato_api.py`: esquema OpenAPI frente a los tipos generados (RF-17).
- Línea base de DGS antes y después de cada tarea (RF-20), con las tres variables `IGEA_*`.
