# Diagnóstico de organización, integración y código duplicado — 2026-10-07

Antes de reorganizar nada: qué hay, qué está repetido y qué no está integrado. El
diagnóstico sigue el enfoque de *spec-driven development* (SDD), y la última sección
propone cómo aplicarlo a la reorganización.

## 1. Spec-driven development, aplicado a este repositorio

SDD consiste en escribir primero la intención como un documento revisable y derivar de
él, en este orden, el plan, las tareas y el código. Las dos referencias actuales son
GitHub Spec Kit (*constitution → specify → plan → tasks → implement*) y Kiro
(`requirements.md` en notación EARS → `design.md` → `tasks.md`, con aprobación entre
fases).

| Pieza SDD | Qué tiene ya el repositorio | Qué le falta |
| --- | --- | --- |
| Constitución (principios no negociables) | `CLAUDE.md` y los skills `igea-dgs-backend` / `igea-dgs-frontend` | Nada importante: es la parte más sólida |
| Especificación | 6 specs en `docs/superpowers/specs/` + `VNR-GIS.md` (1 704 líneas) | Requisitos con identificador; criterios verificables (EARS: «CUANDO … EL SISTEMA DEBE …») |
| Plan y tareas | 10 planes en `docs/superpowers/plans/`, con 448 casillas `- [ ]` | **Ninguna casilla marcada**: el plan no dice qué está hecho |
| Trazabilidad spec ↔ prueba | — | **Ninguna prueba cita una spec o un requisito** (0 de 75 ficheros) |

Consecuencia práctica: las specs se escriben y luego se separan del código. Por ejemplo,
`VNR-GIS.md` §E7 sigue exigiendo tres ficheros de requisitos que ya no existen, y lo que
de verdad se implementó en VNR-GIS solo se sabe leyendo el código.

## 2. Método

- Duplicados en Python: detector propio sobre el AST de `src/` (cuerpos de función
  idénticos, cuerpos idénticos con otros nombres de variable, y nombres repetidos en
  varios módulos), seguido de lectura de cada candidato. jscpd no pudo descargarse
  en esta máquina.
- Duplicados en el front: ventanas de 6 líneas normalizadas sobre `frontend/src`.
- Integración: rutas declaradas en `web/app.py` frente a llamadas de `frontend/src/api.ts`.
- Front: `npx tsc --noEmit` y el checklist del skill `igea-dgs-frontend`.

## 3. Diagnóstico backend

Por gravedad. «Duplicado» significa misma responsabilidad en dos sitios que pueden
divergir, no solo líneas iguales.

### B1. La lectura de la entrada está implementada tres veces — alta

| Vía | Dónde | Modos |
| --- | --- | --- |
| Web | `web/sources/{txt,mdb,vnr}.py` (adaptadores con `SourceAdapter`) | TXT, MDB, VNR |
| CLI | `cli.py:119` `load_dataset` | TXT, MDB |
| GUI heredada | `gui.py:776-800` | TXT, MDB |

Las tres hacen lo mismo (validar el modo, leer TXT o `.mdb`, completar el catálogo con
`catalog_merge`, aplicar el estudio), cada una a su manera. Ya divergen: el CLI no admite
VNR-GIS, y la web pasa `aliases` a `completar`/`diagnosticar`, pero el CLI
(`cli.py:182`) y la GUI (`gui.py:799`) no. Los
adaptadores web son el diseño correcto, pero viven en `web/` y por eso el CLI no los
puede usar.

### B2. Dos caminos de VNR-GIS a DGS — alta

1. **El integrado**: paquete VNR → modelo canónico → `cymdist_bridge` → `CymdistDataset`
   → motor `igea_dgs` (reglas, validación, publicación atómica, determinismo).
2. **El paralelo**: `vnr_etl/exporters/dgs.py` (`DgsExporter`, 332 líneas) escribe su
   propio DGS «mínimo» desde el modelo canónico. Lo usan el CLI `vnr-etl` y la web
   `vnr-etl-web`.

El segundo se salta `reglas.py`, `validate_dgs`, la geografía del motor y la auditoría
de completitud. Eso contradice la regla del skill backend: «si añade una vía nueva, llame
a estas funciones; no copie la lógica». Incluso su `_fmt` es una copia literal de
`dgs.py:71`.

### B3. Dos aplicaciones web con dos colas de trabajos — media-alta

`vnr_etl/web/app.py` es una segunda API FastAPI (`create_app`, 323 líneas) con su propia
cola `_Jobs` (hilos por carril, sin cancelación, sin eventos numerados ni WebSocket).
Su docstring lo dice: «para no replicar el patrón de colas del proyecto anfitrión aquí se
usa una cola mínima». El front no la llama: la web principal ya expone `/api/vnr/*`
importando `vnr_etl.discovery` directamente. Son dos servidores, dos colas y dos modelos
de estado para la misma función.

### B4. Trabajo largo dentro de la petición HTTP — media

`POST /diagnose` y `POST /reconstruct` (`web/app.py:542-554`) ejecutan
`diagnose_selection` y `reconstruct_selection` dentro de la petición. Con `all=true` y
200 alimentadores no hay progreso ni cancelación, y el navegador puede agotar el tiempo
de espera. Eso incumple el principio «nada largo se ejecuta dentro de una petición HTTP».

### B5. Utilidades repetidas — baja, pero son las que más se multiplican

| Utilidad | Copias |
| --- | --- |
| SHA-256 de un fichero por bloques | 7: `feeder_metadata.py:32`, `web/load_batch.py:54`, `web/reconstruction_service.py:432`, `web/source_runs.py:96`, `vnr_etl/discovery/download.py:43`, `vnr_etl/exporters/base.py:66`, `vnr_etl/web/app.py:252` |
| Reproyección con `Transformer.from_crs` | 5: `geography.py:55`, `loads_create.py:818`, `vnr_etl/gis/crs.py:68`, `vnr_etl/pipeline.py:223`, `vnr_etl/exporters/dgs.py:314` |
| Escritura atómica de JSON | 3 idénticas: `web/load_batch.py:78`, `web/reconstruction_service.py:439`, `web/services.py:288` |
| Número finito o `None` | 4: `catalog_resolution.py:380`, `reconstruction_topology.py:345`, `validate.py:53` (idénticas); `vnr_etl/catalogs/conductor.py:75` = `vnr_etl/pipeline.py:485` |
| `_require_requests` | 2: `vnr_etl/connectors/arcgis.py:22`, `vnr_etl/discovery/download.py:32` |
| Saneado del nombre de grupo | 2: `batch.py` (`nombre = ''.join(...)`) y `web/services.py` `group_name` |

### B6. Excepción callada que falsea un resultado — media

`loads_create.py:817-826`: si el CRS de origen no es válido, `Transformer.from_crs`
falla, se captura `Exception` y todas las coordenadas salen `None` sin ningún aviso.
Los `except Exception` de `powerfactory_metadata.py` no son el mismo caso: ahí la API de
PowerFactory lanza excepciones de clase desconocida al consultar atributos, y la
captura es deliberada.

### Falsos positivos revisados (no son duplicados)

- `convert_group` en `web/services.py:891` y en `batch.py:637`: la web delega en el motor y
  solo añade registro y trazabilidad. Es el patrón correcto.
- `convert`, `lote_plan`, `apply_plan` en `web/app.py` y en `web/services.py`: la ruta
  valida y la función de servicio trabaja.
- Los muchos `as_dict`, `load`, `read_layer`, `export`: son implementaciones de un mismo
  protocolo, no copias.
- `preparar_dataset` se llama al cargar (web) y otra vez al convertir (`batch`): está
  documentada como idempotente.

## 4. Diagnóstico frontend

El front está en buen estado. Comprobado:

- `npx tsc --noEmit` sin errores.
- No hay bloques duplicados de 6 líneas o más.
- Sin sondeos: el progreso llega por WebSocket con `since`. El `setInterval` de
  `JobBar.tsx` es solo el reloj del tiempo transcurrido.
- Todo acceso a `localStorage` va en `try/catch`.
- No hay colores fijos en los componentes ni textos con un número fijo de alimentadores.
- Integración: cada ruta de la API tiene su cliente en `api.ts`, salvo
  `GET /runs/{run_id}/manifest`.

Hallazgos menores:

- **F1.** Métodos de cliente que nadie usa: `api.sourceRuns`, `api.events` y `api.job`
  (`api.ts:55, 97, 99`). `events` sería el respaldo si falla el WebSocket, pero
  `useWorkspace.ts` no lo usa.
- **F2.** `download()` (`api.ts:154`) repite la extracción del `detail` de `request()`,
  pero peor: no entiende el `detail` en forma de lista de los 422.
- **F3.** Diagnosticar y reconstruir esperan la respuesta HTTP en vez de ir como trabajo
  (`startJob`). Se arregla junto con B4: el front solo tendría que cambiar a `startJob`.
- **F4.** `Modules.tsx` (456 líneas) y `LoteTab.tsx` (278) son los paneles más grandes.
  No hay duplicación medible, pero son los primeros candidatos a partir si crecen.

## 5. Propuesta de organización e integración

Ordenada para que cada fase deje la suite en verde y tenga su spec antes que su código.

| Fase | Qué | Resuelve | Riesgo |
| --- | --- | --- | --- |
| 0 | Plantilla de spec con requisitos `RQ-<área>-NN` y criterios EARS; las pruebas citan el requisito en su docstring; los planes se marcan al cerrar | Trazabilidad (§1) | Nulo: solo documentación |
| 1 | Módulo `igea_dgs/util.py` (o `_io.py`) con `sha256_file`, `write_json_atomic`, `finite_float_or_none`, `nombre_seguro`; reproyección única en `geography.py` | B5, B6 | Bajo |
| 2 | Pasar `web/sources/` a `igea_dgs/sources/` y que el CLI y la GUI carguen con `adapter_for(mode)` | B1; el CLI gana VNR-GIS | Medio: lector, probar las dos disposiciones |
| 3 | `diagnose`/`reconstruct` como trabajos del carril `engine`; el front con `startJob` | B4, F3 | Bajo-medio |
| 4 | `DgsExporter` de `vnr_etl` como envoltorio del puente + `batch.convert_selection`; retirar el escritor propio | B2 | Medio: cambia la salida de `vnr-etl export` |
| 5 | Retirar `vnr_etl/web` (o montarlo como router dentro de la app principal y su `JobManager`) | B3 | Medio: quita el script `vnr-etl-web` |
| 6 | Limpieza del front: F1, F2 | F1, F2 | Nulo |

Las fases 4 y 5 cambian interfaces públicas (`vnr-etl export`, `vnr-etl-web`). Antes de
empezarlas hay que confirmar que nadie fuera de este repositorio las usa.

## 6. Verificación del diagnóstico (mismo día)

Una segunda pasada para comprobar que los hallazgos son ciertos y buscar lo que la
primera no miró.

### Lo comprobado

- Cada referencia de §3 y §4 (fichero y línea) sigue apuntando al código descrito.
- Suite completa con los tres TXT reales: **854 correctas, 58 omitidas, 0 fallos**
  (101 s). Las 58 omitidas son todas de la vía Access, por falta de `IGEA_MDB`.
- `tests/test_access_input.py` con las dos bases `.mdb`: **21 correctas, 6 omitidas**.
  Las 6 se omiten por diseño: la base y los TXT no son de la misma exportación.
- Front: `npx tsc --noEmit` sin errores y `npm run build` correcto (JS de 305 kB, 94 kB
  con gzip).
- No hay módulos muertos (análisis de importaciones con el AST sobre `src/`, `tests/` y
  `tools/`).
- Checklist del skill backend: cada punto de entrada tiene su guarda
  `if __name__ == '__main__'`. El CLI devuelve 0/2/1 como pide el skill. No hay rutas de
  la máquina en el código. Los «96» de `src/` y `tests/` están en comentarios que citan
  una medición, nunca en la lógica.

### Corrección

- B1: la GUI tampoco pasa los alias al catálogo (`gui.py:799`), no solo el CLI. Ya está
  corregido en §3.

### Hallazgos nuevos

**S1. Las rutas locales del servidor fallan en abierto — media-alta.**
`_server_paths_allowed()` (`web/app.py:56-63`) las permite cuando la variable
`IGEA_WEB_SERVER_PATHS` no existe. Solo el lanzador `igea-dgs-web` las desactiva al
escuchar fuera de `127.0.0.1`, y lo hace con `os.environ.setdefault`, que no pisa un
valor previo. Si la app se arranca con `uvicorn igea_dgs.web.app:create_app --factory
--host 0.0.0.0`, o con la variable ya a `1`, cualquiera en la red puede asignar como
entrada cualquier fichero del disco del servidor. Además, la API no tiene autenticación;
`vnr_etl/web` sí acepta un `auth_token`. La decisión debería tomarla `create_app` según
la interfaz real de escucha, y por defecto en cerrado.

**T1. Laguna de cobertura TXT ↔ Access — media.** Las pruebas que comparan el mismo
alimentador por las dos vías (`test_feeder_pa217.py`, `test_feeder_sl143.py` y las 6
omitidas de `test_access_input.py`) nunca se ejecutan con los datos disponibles, porque
no hay un TXT y una `.mdb` de la misma exportación. Que las dos vías den el mismo modelo
no está comprobado hoy. Hace falta pedir a la distribuidora una pareja TXT + `.mdb` de la
misma fecha.

**T2. Duplicación en las pruebas — baja.** `tests/conftest.py` existe, pero:

- `test_feeder_pa217.py` y `test_feeder_sl143.py` copian sus fixtures `mdb_dataset` y
  `dataset_for` y el auxiliar `both`;
- `_module` (cargar un script de `tools/`) está en 4 ficheros;
- `_wait` (esperar a un trabajo) está en 2.

**T3. Aviso de dependencia — baja.** `fastapi.testclient` avisa de que usar `httpx` con
`starlette.testclient` está obsoleto. Hoy no falla nada, pero romperá las pruebas web
cuando Starlette lo retire.

### Lo que esta revisión no puede verificar

- PowerFactory: según la memoria del proyecto, la prueba en PF la hace el usuario.
- La GUI Tkinter: se usa a mano; sus pruebas solo comprueban el cableado.
- Rendimiento a gran escala más allá de la guarda determinista de O(F·N).

### Veredicto

Los hallazgos de §3 y §4 se sostienen. El diagnóstico **no** estaba completo: le
faltaban la seguridad de la API (S1), la cobertura real entre vías de entrada (T1) y las
pruebas (T2, T3). Con esta sección queda completo para el alcance de código, pruebas y
front. S1 entra en la spec 001 como RF-15.

## 7. Revisión de funcionamiento, módulo por módulo (mismo día)

### Cómo se comprobó

1. **Importación:** los 102 módulos de `src/` se importan en un proceso limpio, uno a uno.
   Resultado: **0 fallos**.
2. **Cobertura por línea** con la suite completa (TXT reales + vía Access con las dos
   `.mdb`). Se midió con `sys.monitoring` de Python 3.12, porque PyPI no respondía para
   instalar `coverage`. No ve lo que corre en procesos hijos del lote, pero las pruebas
   ejecutan esas mismas funciones también en el proceso principal. Resultado: **77 %**
   (15 500 de 20 069 líneas). Los `__init__.py` que salen al 0 % son un artefacto: se
   importan antes de que empiece la medición.
3. **Puntos de entrada en vivo:**
   - `igea-dgs list` y `convert --all` sobre los 96 alimentadores reales: **96/96 OK**, con
     `--workers 1` (9 s) y `--workers 4` (5 s), y los 96 DGS **idénticos byte a byte**.
   - `igea-dgs-web` arrancado de verdad: salud, página, espacio de trabajo, rutas locales,
     carga (96 alimentadores), conversión de 3, salidas (20 ficheros) y `diagnose`.
     Rechaza bien una opción fuera de rango (422) y una ruta con `../..` (400). El
     registro del servidor no tiene ningún 500 ni ninguna traza.
   - Interfaz en un navegador real (Playwright): carga sin errores ni avisos de consola, el
     Registro conecta por WebSocket y detecta PowerFactory 2024 con Python 3.12.
   - `vnr-etl --help`, `vnr-etl doctor` e `igea-dgs-web --help`: responden.
4. **Oráculo pandapower** (`oraculo.py`, que ninguna prueba ejecuta) sobre los 96
   alimentadores reales con las reglas del proyecto: 31 s; **95 convergen, 1 con error**
   (`tension_imposible`; tensión mínima 0,756 pu en PE105); **0 excepciones**.

### Cobertura por módulo

#### Entrada

| Módulo | Líneas | Cobertura |
| --- | ---: | ---: |
| `dataset.py` | 245 | 96 % |
| `access.py` | 254 | 83 % |
| `identify.py` | 72 | 99 % |
| `study.py` | 44 | 98 % |
| `catalog_merge.py` | 144 | 95 % |
| `huella.py` | 38 | 0 % |
| `coordenadas.py` | 172 | 92 % |

#### Modelo y catálogo

| Módulo | Líneas | Cobertura |
| --- | ---: | ---: |
| `model.py` | 984 | 91 % |
| `catalog.py` | 629 | 92 % |
| `catalog_data.py` | 191 | 98 % |
| `catalog_resolution.py` | 330 | 93 % |
| `reglas.py` | 138 | 91 % |
| `puentes.py` | 128 | 96 % |
| `trafomix.py` | 45 | 98 % |
| `reconstruction.py` | 155 | 92 % |
| `reconstruction_topology.py` | 308 | 92 % |
| `naming.py` | 15 | 40 % |

#### Salida y validación

| Módulo | Líneas | Cobertura |
| --- | ---: | ---: |
| `dgs.py` | 955 | 95 % |
| `schema.py` | 40 | 90 % |
| `geography.py` | 251 | 84 % |
| `validate.py` | 640 | 79 % |
| `oraculo.py` | 241 | 0 % |
| `export_tables.py` | 86 | 85 % |
| `preview.py` | 286 | 73 % |
| `feeder_metadata.py` | 124 | 94 % |
| `inventory.py` | 275 | 88 % |

#### Lote y red unida

| Módulo | Líneas | Cobertura |
| --- | ---: | ---: |
| `batch.py` | 532 | 93 % |
| `combine.py` | 304 | 95 % |
| `studies.py` | 280 | 95 % |
| `economia.py` | 87 | 95 % |

#### Cargas

| Módulo | Líneas | Cobertura |
| --- | ---: | ---: |
| `loads.py` | 465 | 93 % |
| `loads_create.py` | 620 | 78 % |

#### PowerFactory

| Módulo | Líneas | Cobertura |
| --- | ---: | ---: |
| `powerfactory_env.py` | 79 | 25 % |
| `powerfactory_metadata.py` | 394 | 82 % |

#### Borde

| Módulo | Líneas | Cobertura |
| --- | ---: | ---: |
| `cli.py` | 251 | 66 % |
| `gui.py` | 1777 | 33 % |
| `settings.py` | 73 | 95 % |

- `igea_dgs/` — 1 módulos, 42 líneas, 93 %

- `igea_dgs/web/` — 11 módulos, 3425 líneas, 76 %. Bajo 70 %: `__main__.py` 0 %, `runtime.py` 68 %, `services.py` 66 %

- `igea_dgs/web/sources/` — 4 módulos, 143 líneas, 92 %

- `vnr_etl/` — 6 módulos, 1025 líneas, 76 %. Bajo 70 %: `__main__.py` 0 %, `cli.py` 67 %, `logging.py` 65 %

- `vnr_etl/application/` — 2 módulos, 339 líneas, 88 %

- `vnr_etl/audit/` — 1 módulos, 136 líneas, 88 %

- `vnr_etl/catalogs/` — 1 módulos, 59 líneas, 0 %. Bajo 70 %: `conductor.py` 0 %

- `vnr_etl/connectors/` — 6 módulos, 599 líneas, 70 %. Bajo 70 %: `arcgis.py` 61 %, `delimited.py` 70 %, `registry.py` 68 %

- `vnr_etl/discovery/` — 6 módulos, 958 líneas, 77 %. Bajo 70 %: `download.py` 57 %, `freshness.py` 64 %

- `vnr_etl/electrical/` — 1 módulos, 59 líneas, 92 %

- `vnr_etl/exporters/` — 3 módulos, 398 líneas, 75 %. Bajo 70 %: `cymdist.py` 37 %

- `vnr_etl/gis/` — 3 módulos, 245 líneas, 65 %. Bajo 70 %: `crs.py` 30 %, `geometry.py` 45 %

- `vnr_etl/models/` — 1 módulos, 221 líneas, 99 %

- `vnr_etl/reconciliation/` — 1 módulos, 72 líneas, 64 %. Bajo 70 %: `diff.py` 64 %

- `vnr_etl/topology/` — 1 módulos, 106 líneas, 80 %

- `vnr_etl/validation/` — 1 módulos, 115 líneas, 98 %

- `vnr_etl/web/` — 2 módulos, 391 líneas, 70 %. Bajo 70 %: `__main__.py` 60 %

### Veredicto por capa

| Capa | ¿Funciona? | Base |
| --- | --- | --- |
| Entrada (TXT y Access) | Sí | Pruebas al 83-99 % y conversión real de los 96 |
| Modelo, catálogo y reglas | Sí | 91-98 %; DGS deterministas |
| Salida DGS y validación | Sí | `dgs.py` al 95 %; validación al 79 % |
| Oráculo pandapower | Sí, **sin pruebas** | Comprobado a mano sobre los 96; 0 % en la suite |
| Lote y red unida | Sí | 93-95 %; serie = paralelo byte a byte |
| Cargas (plantillas) | Sí | 78-93 % |
| API web y front | Sí | Recorrido en vivo completo; `services.py` al 66 % |
| CLI `igea-dgs` | Sí | Conversión real; 66 % en la suite |
| GUI Tkinter | Sin comprobar en vivo | 33 %; es heredada y se usa a mano |
| PowerFactory | Sin comprobar | Lo prueba el usuario en PF |
| VNR-GIS (`vnr_etl`) | Sí en lo que se prueba | 86 pruebas en verde. Falta `gis/crs.py` (30 %) y `exporters/cymdist.py` (37 %); 5 drivers opcionales sin instalar |

### Defectos y riesgos nuevos de esta revisión

- **R1. El oráculo pandapower no tiene pruebas** (0 % de 241 líneas), aunque es la
  validación física que da la web antes de PowerFactory. Funciona hoy, pero nada avisaría
  si una versión de pandapower lo rompe. Hace falta una prueba sintética que lo ejecute.
- **R2. La instalación es todo o nada.** Con un único `requirements.txt`, un driver opcional
  que no se descargue (aquí `psycopg2-binary`, porque PyPI no respondía) hace fallar todo
  `pip install -r requirements.txt`, también la instalación automática de `run_gui.bat`.
  Además, el `.venv` de esta máquina no tiene `leafmap`, `chardet`, `SQLAlchemy`,
  `oracledb`, `psycopg2-binary`, `opencv-python`, `pdf2image` ni `rarfile`.
- **R3. Ayuda del CLI en inglés.** `igea-dgs --help` («Universal IGEA/CYMDIST TXT to
  DIgSILENT DGS converter», «List feeders…», «Convert one, several…») incumple la regla de
  idioma.
- **R4. Ruido de pandapower.** Imprime un aviso de `numba` por cada alimentador calculado
  (96 veces en un lote). Se evita pasando `numba=False` a `runpp`, o instalando `numba`.
- **R5. Módulos VNR poco probados:** `gis/crs.py` (30 %), `gis/geometry.py` (45 %),
  `exporters/cymdist.py` (37 %) y `catalogs/conductor.py` (0 %; se importa, pero
  `ConductorCatalog` no se ejecuta nunca).
- **Matiz a S1 (§6):** la ayuda de `igea-dgs-web` documenta que `IGEA_WEB_SERVER_PATHS=1`
  es la forma deliberada de activar las rutas al exponer el servidor. El riesgo real es
  arrancar la app con `uvicorn` directamente, sin pasar por el lanzador.

### Conclusión

Todo lo que el usuario usa a diario funciona y está comprobado con los datos reales:
conversión por CLI y por web, lote en serie y en paralelo, red unida, validación y
oráculo. Lo que no está comprobado es lo que solo se puede probar a mano (GUI Tkinter,
PowerFactory) y la parte de VNR-GIS sin datos reales. Los riesgos R1-R5 no rompen nada
hoy; R1 y R2 son los que más conviene cerrar.

## 8. Correcciones (2026-10-08)

- **R1 — corregido.** `tests/test_oraculo.py` (10 pruebas) ejecuta el oráculo sobre exports
  sintéticos con las dos disposiciones. Comprueba el recuento de barras, líneas,
  transformadores y cargas, el balance «fuente = carga + pérdidas», que no modifique el
  modelo y que sea determinista, la impedancia nula, la red unida y la ausencia de
  pandapower.
- **Fallo nuevo, descubierto al escribir R1 y corregido.** Con la disposición **completa**
  el oráculo daba «no converge» en redes sanas. Cada carga en el punto medio cuelga de una
  derivación virtual de 0 m, que el oráculo llevaba a 1 mm. Una impedancia de 10⁻⁷ Ω
  junto a tramos de decenas de metros deja la matriz mal condicionada. Se midió: converge
  desde 1 cm; falla con 0 m y con 1 mm. Ahora un tramo de menos de 1 cm se calcula como
  conexión (interruptor entre barras), abierta si alguna maniobra de ese tramo lo está.
  La entrega de 03/08, en disposición reducida, da el mismo resultado que antes: 95
  convergen y 1 da error.
- **R3 — corregido.** La ayuda y los mensajes de `igea-dgs` están en español, y el
  programa se presenta como `igea-dgs` (antes, `cli.py`). Siguen en inglés los textos fijos
  de `argparse` («usage», «options», «show this help message and exit»).
- **R4 — corregido.** `runpp(..., numba=False)`: ya no hay avisos de numba (antes, 96 por
  lote). Una prueba lo vigila.
- **R2 — corregido separando los drivers.** `requirements-drivers.txt` lleva los seis
  drivers opcionales de VNR-GIS (PostgreSQL, Oracle, SQLAlchemy, OpenCV, pdf2image y RAR);
  `requirements.txt` conserva todo lo demás, incluido `pyodbc` para la vía Access. Los
  mensajes de `vnr_etl` que piden un driver remiten al nuevo fichero, y la auditoría de
  dependencias lee los dos. Al probarlo, `leafmap` también hizo fallar el fichero
  principal: con la red cortándose, pip no pudo resolver sus muchas dependencias. Es
  opcional (sin él, la vista previa usa Leaflet por CDN), así que pasó al fichero aparte.
