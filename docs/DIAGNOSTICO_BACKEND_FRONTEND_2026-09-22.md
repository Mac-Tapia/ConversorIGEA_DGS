# Diagnóstico backend/frontend, cuellos de botella y plan de comercialización

Fecha: 2026-09-22
Revisor: auditoría asistida, ejecutada sobre `master` (commit `1c87484`)
Marco de evaluación: los dos skills del propio repo — `.cursor/skills/igea-dgs-backend/SKILL.md` y `.cursor/skills/igea-dgs-frontend/SKILL.md` — usados como criterio normativo (reglas de dominio + checklist de producción).
Método: lectura estática, ejecución de la suite con TXT reales, *profiling* con `cProfile`, y experimentos de reproducción y de parche en copia de trabajo aislada. **El repositorio no fue modificado**; los parches se midieron en una copia en directorio temporal.

Este documento complementa `DIAGNOSTICO_TECNICO_2026-09-21.md` y **corrige una de sus severidades** (ver §7).

---

## 1. Dictamen ejecutivo

El motor es sólido en lo que se propuso demostrar: estructura, determinismo, cobertura topológica y aceptación real en PowerFactory. Nada de lo que sigue cuestiona eso.

Lo que la evidencia de esta auditoría añade son tres conclusiones nuevas y accionables:

1. **El rendimiento no está limitado por el volumen de datos sino por dos bucles cuadráticos accidentales.** El 95 % del tiempo de CPU de una conversión se consume en dos funciones que recalculan la misma estructura una y otra vez. Dos cambios localizados llevan el alimentador mayor de **17,3 s a 0,80 s (21,6×)** y el lote completo de 96 alimentadores de **106 s a 35 s**, con resultados idénticos y la suite en verde. Hoy el coste crece con el cuadrado del tamaño del alimentador, lo que convierte el producto en inviable para redes urbanas grandes.

2. **Existe un defecto silencioso alcanzable desde un menú de la GUI.** Si el operador elige `EPSG:4326` como CRS de origen —una opción ofrecida en el desplegable— todas las longitudes salen **110.575 veces más pequeñas** y el conversor reporta `ok`, `errors_total = 0`. El validador no puede detectarlo porque compara el DGS contra el mismo modelo que lo generó. Es el hallazgo más grave del informe.

3. **La georreferenciación no es realmente opcional.** Con `--no-geography`, basta **un** nodo sin `CoordX/CoordY` para que el alimentador falle. Esto incumple la regla de dominio nº 5 del propio skill de backend y excluye a cualquier cliente cuyo export CYMDIST no traiga GIS.

**Clasificación:** producto interno maduro, **no comercializable todavía**. Los bloqueos para venta no son de funcionalidad eléctrica —esos están documentados en el diagnóstico del 21-09— sino de **escalabilidad, empaquetado, trazabilidad y licenciamiento**. Son de coste notablemente menor que la validación física y deberían ejecutarse primero.

---

## 2. Evidencia ejecutada en esta auditoría

| Medición | Resultado |
| --- | --- |
| Suite completa con TXT reales (`pytest -q`) | **84 passed, 1 skipped en 132,05 s** |
| Suite con los dos parches de rendimiento aplicados | **84 passed, 1 skipped en 55,03 s** — resultados idénticos |
| Lote completo, 96 alimentadores (`test_all_mode…`) | **106,29 s → 35,02 s** con los parches |
| Lectura del dataset (RED 10,0 MB + CARGA 1,4 MB + BD_Equipo 23 KB) | 0,44 s |
| Volumen real del export de referencia | 38.681 nodos · 38.657 secciones · 96 alimentadores (3 *stubs*) · 7.287 cargas · 37.283 nodos intermedios · 15.196 seccionalizadores |
| Conversión del alimentador mayor (SM218, 2.024 tramos) | 17,26 s → **0,80 s** con los parches; DGS 1,53 MB; `errors_total = 0` en ambos casos |
| Entorno | Python **3.14.4**, pyproj 3.8.0, Windows 11 |
| `ruff` / `mypy` / `pyright` | **no instalados ni configurados**; no existe `.github/` (sin CI) |

Reproducción de defectos:

| Experimento | Resultado |
| --- | --- |
| Convertir con `source_crs='EPSG:4326'` sobre coordenadas en grados | longitud total 127 m → **0,001145 m** (factor **110.575×**); manifiesto `ok`, `errors_total = 0` |
| `include_geography=False` con un nodo sin `CoordX/CoordY` | **falla**: `SI114: prueba de conexión MT/SED falló … sin CoordX/CoordY georreferenciadas` |
| Sustitución de longitud TXT por georreferencia, export completo | razón geo/TXT = **1,000 en los 38.657 tramos** (p1 = p50 = p99 = 1,000); 4.185,7 km por ambos métodos |

---

## 3. Evaluación del backend contra su skill

### 3.1 Reglas de dominio

| # | Regla | Estado | Evidencia |
| --- | --- | --- | --- |
| 1 | Sin DGS de referencia en runtime | **Cumple** | `NA205.dgs` no se parsea en producción; `runtime_reference_dependency: false` en el manifiesto. Pero ~20 constantes `NA205_*` en `dgs.py` codifican la *calibración* de esa red (§3.3) |
| 2 | Modo estricto por defecto; no inventar `DEFAULT` | **No cumple** | `_resolve_type` (`model.py:264`) siempre degrada a auto-mapeo por distancia de edición y luego a `DEFAULT`, **incluso en modo estricto**. El propio CLI lo documenta: «line types always auto-resolve» |
| 3 | Independencia por alimentador: un fallo no invalida otros | **Cumple parcialmente** | El bucle sí aísla fallos y el borrado de artefactos ya se limita a los de ese intento (`batch.py:194`). Pero `_selection` (`batch.py:56`) lanza `ValueError` por colisión de nombres cortos **antes** del bucle: un solo choque aborta el lote completo y no se convierte nada |
| 4 | Determinismo | **Cumple** | FID secuenciales sobre claves ordenadas; sin `set` en iteraciones de escritura, sin `hash()` ni tiempo en la salida |
| 5 | Geografía opcional | **No cumple** | `apply_georeferenced_lengths` y `prove_mt_connections` se invocan sin condición al final de `build_feeder_model` (`model.py:823`, `825`). `--no-geography` evita `pyproj`, pero **sigue exigiendo coordenadas completas**. Reproducido en §2 |

### 3.2 Checklist de producción

| Ítem del checklist | Estado | Nota |
| --- | --- | --- |
| Validar rutas de entrada antes de parsear | **Cumple** | `_require_input_files` (`cli.py:56`) |
| Códigos de salida 0 / 2 / 1 | **Cumple parcialmente** | 0 y 2 correctos; el `1` de «error de uso/IO» no existe por diseño: todo error de IO sale por `SystemExit(str)`, que devuelve 1 de forma incidental |
| Errores de usuario claros, sin *stack trace* en stdout | **Cumple parcialmente** | Buenos mensajes en CLI, pero **no hay `--verbose`**: no hay forma de obtener el detalle cuando el mensaje corto no basta |
| `batch_manifest.json` siempre escrito al final | **No cumple** | Se escribe en `batch.py:234`, fuera de `try`. Si `_selection` falla, o el bucle lanza una excepción no capturada (`MemoryError`, `KeyboardInterrupt`), **no hay manifiesto** y el lote queda sin traza |
| Callbacks de progreso sin acoplar a Tk | **Cumple** | `ProgressCallback` puro (`batch.py:22`) |
| `pyproj` no bloquea conversión sin GPS | **No cumple** | Ver regla de dominio 5 |
| Tests para cambios de conexión/validación | **Cumple** | 20 ficheros `test_*.py` (84 pruebas), cobertura funcional buena |
| Sin secretos ni rutas absolutas de máquina | **No cumple** | `gui.py:54` fija `C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12`; `cli.py:38` y `batch.py:75` fijan `EPSG:32718` (Ica, Perú) como CRS de origen por defecto |

### 3.3 Universalidad: lo que sigue codificado de una sola red

El README promete «universal por diseño». El motor lo cumple en nombres y conteos, pero **no en física**. Sigue fijado en `dgs.py`:

| Constante | Valor fijo | Consecuencia comercial |
| --- | --- | --- |
| `frnom` | `60` (en `ElmNet`, `TypLne`, `TypTr2`) | Ningún mercado de 50 Hz (Europa, Chile, Argentina, Bolivia, Paraguay, Uruguay) puede usar la salida sin editarla en PowerFactory |
| `NA205_SED_LV_KV` | `0.22` | La BT peruana. 0,4 / 0,38 / 0,23 kV no son configurables |
| `uktr`, `uk0tr` | `4.0` | Impedancia de cortocircuito inventada, no de catálogo |
| `pcutr`, `pfe` | `strn·10`, `strn·1.5` | Pérdidas sintetizadas por fórmula sin respaldo |
| `tr2cn_h='D'`, `tr2cn_l='YN'`, `nt2ag=5` | Dyn5 | Grupo de conexión asumido para todo transformador |
| `nlnph`, `nt2ph`, `nphase` | `3` | Todo trifásico |
| `it2p1/it2p2/it2p3` | `0/1/2` | Cada `StaCubic` conecta las 3 fases **ignorando `line.phase`**, que sí está en el modelo |
| `bline`, `bline0` | `0` | `B1/B0` se leen del catálogo y se descartan al escribir: sin susceptancia capacitiva |
| `ElmXnet.snss/rntxn/z2tz1` | vacíos | Sin potencia ni impedancia de cortocircuito en la fuente: cortocircuito no defendible |
| `NA205_DIAGRAM_UNITS_PER_METER` | `2.08` | Escala de diagrama calibrada a la latitud de Ica (−14,9°) |

Nada de esto es un error de código: es una decisión de alcance que quedó sin parametrizar. Pero **cada fila de esta tabla es un cliente que no puede comprar el producto**.

---

## 4. Evaluación del frontend contra su skill

### 4.1 Lo que está bien resuelto

El *threading* está implementado exactamente como el skill lo pide, y eso es lo más fácil de equivocar en Tkinter:

- Trabajo pesado en `threading.Thread(target=worker, daemon=True)` (`gui.py:642`, `900`, `1071`).
- Toda actualización de UI vía `self.root.after(0, …)`; ningún widget se toca desde el hilo trabajador.
- `_set_busy` deshabilita el conjunto `_action_buttons`, no solo «Convertir».
- Progreso real por alimentador usando el callback del backend (`gui.py:1022`).
- Diálogo corto + detalle completo en el Registro, como pide el skill.
- `run_gui.bat` prefiere `.venv` e instala `requirements.txt` sin `[dev]`.
- Ninguna importación de Tk en el motor.

### 4.2 Checklist de producción: incumplimientos

| Ítem del checklist | Estado | Detalle |
| --- | --- | --- |
| Persistir últimas rutas en `%LOCALAPPDATA%/igea-dgs/gui_state.json` | **No cumple, por decisión explícita** | El código hace lo contrario: `_discard_legacy_state` (`gui.py:527`) **borra** el fichero y `_on_close` resetea la sesión. El operador vuelve a elegir tres ficheros en cada arranque. Es defendible para no arrastrar sesiones, pero contradice el checklist y es fricción diaria en uso real |
| Validar archivos y crear carpeta de salida | **Cumple** | `_require_inputs`, `mkdir` con manejo de error |
| Aliases: JSON legible si hay ruta | **Cumple** | |
| Errores: diálogo + Registro | **Cumple** | |

### 4.3 Vacíos no cubiertos por el checklist pero bloqueantes en producto

| # | Hallazgo | Ubicación | Consecuencia |
| --- | --- | --- | --- |
| F-01 | **No existe cancelación.** No hay botón Cancelar ni `threading.Event` en todo el módulo | `gui.py` | Un lote de 96 alimentadores hoy son ~2 min, pero un export urbano grande son decenas de minutos sin salida. El operador solo puede matar el proceso |
| F-02 | **Cerrar la ventana durante un lote corrompe la salida.** `_on_close` llama a `root.destroy()` sin comprobar `self._busy`; `mainloop` retorna, `main()` devuelve, el proceso termina y el hilo *daemon* muere **a mitad de escritura** | `gui.py:1107` | `.dgs` truncados indistinguibles de válidos; no hay escritura atómica que lo contenga |
| F-03 | **El Registro no se persiste.** Vive solo en el widget `ScrolledText` y se borra al cerrar | `gui.py:320`, `575` | Sin soporte posible: cuando un cliente reporte un fallo no habrá nada que pedirle. Bloqueante comercial |
| F-04 | **La GUI solo funciona desde el árbol de fuentes.** `_project_root()` es `Path(__file__).resolve().parents[2]`, que asume `<raíz>/src/igea_dgs/` | `gui.py:84` | Instalado como *wheel* en `site-packages`, `parents[2]` apunta fuera: `tools/powerfactory_acceptance.py` y `config/line_type_aliases.json` no se encuentran. Además `pyproject.toml` **no empaqueta `tools/` ni `config/`**. El botón de PowerFactory no funciona en una instalación real |
| F-05 | **Prefill desde `referencia/`.** `_default_referencia_inputs` rellena los tres campos con los TXT del repo | `gui.py:102` | Comodidad de desarrollo filtrada al producto: el operador puede convertir el export de otra empresa sin notarlo |
| F-06 | **Detección de PowerFactory frágil.** Ruta fija a «PowerFactory 2024\Python\3.12» + `glob` bajo `C:\Program Files\DIgSILENT` | `gui.py:54-72` | Falla con instalación en otra unidad, `Program Files` localizado, o versión no contemplada. No consulta el registro de Windows |
| F-07 | **`EPSG:4326` en el desplegable de CRS de origen** | `gui.py:42` | Es la vía de acceso al defecto crítico C-01 (§7). Opción que destruye el modelo eléctrico en silencio |
| F-08 | **Monolito de 1.129 líneas** sin separación vista/controlador/servicio | `gui.py` | La lógica de negocio (selección de CRS, aliases, orquestación de PF) es intestable: no hay un solo test de `gui.py` |

---

## 5. Cuellos de botella (medidos, no estimados)

### 5.1 Dónde se va el tiempo

Conversión del alimentador mayor (SM218, 2.024 tramos), etapa por etapa:

| Etapa | Tiempo | % |
| --- | --- | --- |
| `build_feeder_model` | 0,027 s | 0,1 % |
| `build_geography` (pyproj) | 0,097 s | 0,5 % |
| `validate_geography` | 0,001 s | 0,0 % |
| `write_dgs` | 2,282 s | 12,4 % |
| **`validate_dgs`** | **15,939 s** | **86,9 %** |

La lectura de los 11,4 MB de TXT (0,44 s) y el modelo (0,027 s) son irrelevantes. **El coste está íntegramente en escribir y validar el diagrama.**

### 5.2 La causa raíz: dos bucles cuadráticos

`cProfile` sobre una conversión completa (40,9 s, 59,2 M llamadas):

```
ncalls    tottime  cumtime  función
   7131     1.489   24.329  dgs.py:115(diagram_anchor_node)
   7131    17.507   22.830  dgs.py:106(_line_neighbors)       <-- 56 % del total
   8096     0.012   17.627  dgs.py:131(is_micro_service_stub_line)
      2     0.006   13.444  dgs.py:204(visible_pointterm_nodes)
6633464     6.232   11.107  validate.py:49(_loc)              <-- 6,6 M llamadas
20776075    5.105    5.105  {method 'replace' of 'str'}       <-- 20,8 M llamadas
```

**B-01 — `_line_neighbors` reconstruye la adyacencia completa en cada llamada.**
`diagram_anchor_node` (`dgs.py:115`) empieza con `neighbors = _line_neighbors(model).get(node_id, ())`: recorre las 2.024 líneas y construye un `defaultdict` entero **para leer una sola entrada**. Se le llama 7.131 veces. Peor: `is_micro_service_stub_line` la llama dos veces por línea, `diagram_line_sections` recorre todas las líneas llamándola, y `visible_pointterm_nodes` vuelve a invocar `diagram_line_sections`. El resultado es O(L²) con un factor constante alto — 22,8 s de los 40,9 s.

**B-02 — Búsqueda lineal dentro de un bucle en el validador.**
`validate.py:512`: `line = next((ln for ln in model.lines if _loc(ln.section_id) == name), None)` dentro de `for r in line_rows`. Son L² comparaciones, cada una normalizando una cadena con tres `str.replace` y un *slice*: de ahí los 6,6 M de `_loc` y los 20,8 M de `replace`.

### 5.3 Escalado: el problema real

El coste medido se ajusta a **t ≈ 4,8 × 10⁻⁶ · N²** segundos (N = tramos). El coeficiente es estable en todo el rango:

| Alimentador | Tramos | Total | µs/tramo² |
| --- | --- | --- | --- |
| SM218 | 2.024 | 16,92 s | 4,13 |
| CA101 | 1.261 | 8,61 s | 5,41 |
| PN107 | 565 | 1,56 s | 4,88 |
| SL141 | 364 | 0,70 s | 5,32 |

Proyección para un cliente con alimentadores urbanos grandes:

| Tramos | Hoy | Con los parches (lineal) |
| --- | --- | --- |
| 2.000 | 17 s | 0,8 s |
| 10.000 | **~8 min** | ~4 s |
| 20.000 | **~32 min** | ~8 s |

Un alimentador de 20.000 tramos no es exótico en una capital. **Hoy el producto no lo soporta**, y el modo `--all` sobre ese export sería cuestión de horas, en un solo hilo, sin cancelación ni reanudación.

### 5.4 La corrección, medida

Dos cambios localizados, aplicados y medidos en copia aislada:

1. Memoizar la adyacencia por modelo (`_NEIGHBOR_CACHE` invalidada por `len(model.lines)`) — 6 líneas.
2. Sustituir el `next(...)` de `validate.py:512` por un `dict` construido una vez — 2 líneas.

| Medición | Antes | Después | Mejora |
| --- | --- | --- | --- |
| SM218: `write_dgs` | 2,337 s | 0,131 s | 17,8× |
| SM218: `validate_dgs` | 14,926 s | 0,665 s | 22,4× |
| **SM218: total** | **17,26 s** | **0,80 s** | **21,6×** |
| Lote de 96 alimentadores | 106,29 s | 35,02 s | 3,0× |
| Suite completa | 132,05 s | 55,03 s | 2,4× |
| `errors_total` / resultado de la suite | 0 / 84 passed | 0 / 84 passed | **idéntico** |

Ocho líneas de código. Es la mejora de mayor relación valor/coste de todo este informe.

### 5.5 Cuellos de botella secundarios (reales pero no dominantes)

| # | Hallazgo | Medición |
| --- | --- | --- |
| B-03 | `build_feeder_model` recorre **todo** `customer_loads`, `switch_settings`, `sectionalizer_settings` y `intermediate_nodes` por cada alimentador, y `_catalog(dataset)` se reconstruye en cada llamada | O(F·N): 96 × 37.283 intermedios ≈ 3,6 M búsquedas. Medido: ~2 s para los 96 alimentadores. **Real pero marginal** frente a B-01/B-02; pre-indexar en `CymdistDataset` lo elimina |
| B-04 | `geography.py:117` repite el *bucketing* de nodos intermedios que `apply_georeferenced_lengths` ya hizo | Trabajo duplicado por alimentador |
| B-05 | `model.py:420`: rama de `_section_projected_path` que escanea `dataset.intermediate_nodes` por sección cuando no recibe el índice | O(S·I) latente. Hoy ningún llamador la activa; es una trampa para el próximo desarrollador |
| B-06 | Conversión estrictamente secuencial | Los alimentadores son independientes por diseño (regla 3). Con B-01/B-02 corregidos, un `ProcessPoolExecutor` daría otro 4-8× en el modo `--all` |

---

## 6. Qué falta para ser comercial

Separado por naturaleza del bloqueo. Ninguno de estos puntos es de física eléctrica: esos ya están en el diagnóstico del 21-09.

### 6.1 Legal y distribución — bloqueante absoluto

| # | Falta | Estado |
| --- | --- | --- |
| K-01 | **No hay `LICENSE`.** Sin términos, el cliente no puede legalmente usarlo ni su departamento legal aprobarlo | Ausente |
| K-02 | **No hay instalador.** No hay `.spec` de PyInstaller, MSI ni ejecutable. La instalación es `python -m venv` + `pip install` + editar `PYTHONPATH` | Ausente |
| K-03 | **El paquete no incluye lo que la GUI necesita.** `pyproject.toml` empaqueta solo `src/igea_dgs`; `tools/powerfactory_acceptance.py` (97 KB, la puerta de aceptación) y `config/` quedan fuera, y `_project_root()` los busca por ruta relativa al árbol de fuentes (F-04) | Roto en instalación real |
| K-04 | **Sin mecanismo de licenciamiento ni control de versión de producto** | Ausente |
| K-05 | **Sin política de soporte, versionado semántico documentado ni CHANGELOG** | Ausente |

### 6.2 Soporte y operación — bloqueante práctico

| # | Falta | Consecuencia |
| --- | --- | --- |
| K-06 | **Sin *logging* estructurado a fichero.** Ni el motor ni la GUI escriben log persistente (F-03) | Imposible diagnosticar la incidencia de un cliente |
| K-07 | **Sin `run_id`, hashes de entrada ni versiones en el manifiesto.** `batch_manifest.json` no registra versión del paquete, de Python, de `pyproj`, del perfil de esquema, ni *hash* de los TXT | Un resultado no es reproducible ni auditable a posteriori |
| K-08 | **Sin cancelación ni reanudación de lote** (F-01, B-06) | |
| K-09 | **Sin escritura atómica.** Se escribe directamente sobre el destino final; el borrado de artefactos en error ya está acotado al intento (`batch.py:194`), pero un corte a mitad de `write_dgs` deja un `.dgs` truncado que ninguna comprobación detecta | Salida parcial indistinguible de válida (F-02) |
| K-10 | **Sin CI.** No existe `.github/`; `ruff`, `mypy`/`pyright` y cobertura no están instalados ni configurados; no hay *lockfile* ni matriz de versiones (el `.venv` corre **Python 3.14** mientras `requires-python` declara `>=3.10`, sin nada que pruebe 3.10) | Regresiones invisibles; construcciones no reproducibles |
| K-11 | **Documentación de operador inexistente.** El README es una guía de desarrollador: `PYTHONPATH=src`, `pip install -e .`, rutas del repo | El cliente no puede instalar sin el autor |

### 6.3 Seguridad y gobierno del dato

| # | Hallazgo | Ubicación |
| --- | --- | --- |
| K-12 | **Inyección HTML/JS en la vista previa.** Los `popup` se construyen interpolando `node_id`, `section_id` y `type_code` sin escapar (`preview.py:174`, `207`) y se renderizan con `lyr.bindPopup(html)`, que interpreta HTML. Además el GeoJSON se incrusta en un `<script>` mediante `json.dumps` sin neutralizar `</script>` (`preview.py:285`) | `preview.py` |
| K-13 | **CDN sin `integrity`/SRI y sin modo *offline*.** `preview.py:293-294` carga Leaflet desde `unpkg.com` sin SRI | Las redes de utilities suelen estar aisladas: la vista previa simplemente no carga. Y sin SRI, un CDN comprometido ejecuta código en la máquina del operador |
| K-14 | **Datos de la distribuidora sin `.gitignore`.** `referencia/audit_ternas_{backbone,classified,ug}.json` (56 KB) contienen identificadores reales de la red — `IN110`, `SEC_2010_1146990_SE42147`, `NODE_…_SE42147` — y están **sin versionar pero tampoco ignorados**: `.gitignore` solo cubre `referencia/RED_*.txt`, `CARGA_*.txt` y `BD_Equipo*.txt`. Con `tools/_publish_to_github.py` en el repo, un `git add -A` los publica | `.gitignore`, `referencia/` |
| K-15 | **Sin protección frente a fórmulas en export CSV/TSV/XLSX.** Un identificador que empiece por `=`, `+`, `-` o `@` se ejecuta al abrir en Excel | `export_tables.py` |

### 6.4 Robustez de entrada

| # | Hallazgo | Ubicación |
| --- | --- | --- |
| K-16 | Un `SectionID` duplicado lanza `ValueError` **sin número de línea ni fichero**, y deja el dataset completo inutilizable | `dataset.py:112`, `117` |
| K-17 | `errors='replace'` en la lectura y asignación directa a `dict` en `nodes`/`sources`/`headnodes`: registros duplicados se sobrescriben en silencio, sin informe de ingestión | `dataset.py:81`, `104-108` |
| K-18 | `_float`/`_int` (`model.py:131`, `138`) convierten texto inválido en `0`/`default`: un `R1` corrupto se vuelve 0 Ω/km y pasa toda la validación | `model.py` |
| K-19 | `_calc_p_q` solo modela plenamente `ValueType=2`; cualquier otro modo termina con **Q = 0** sin aviso | `model.py:292` |
| K-20 | Colisión de nombre corto aborta el lote completo en lugar de aislar (regla de dominio 3) | `batch.py:56` |

---

## 7. Hallazgos críticos priorizados

| ID | Sev. | Hallazgo | Evidencia |
| --- | --- | --- | --- |
| **C-01** | **Crítica** | **`EPSG:4326` en el desplegable de CRS de origen corrompe el modelo en silencio.** `apply_georeferenced_lengths` aplica `math.hypot` a `CoordX/CoordY` **crudas** e interpreta el resultado como metros, sin consultar las unidades del CRS. Si las coordenadas son grados, las longitudes salen 10⁵ veces menores. El validador no lo detecta porque su oráculo es el mismo modelo | Reproducido: 127 m → 0,001145 m, **factor 110.575×**, manifiesto `ok`, `errors_total = 0`. La opción está en `gui.py:42` |
| **C-02** | **Alta** | **Dos bucles cuadráticos consumen el 95 % del CPU y hacen el producto inviable a escala urbana.** `t ≈ 4,8·10⁻⁶·N²` | §5. Corregido y medido: 21,6× en un alimentador, 3× en el lote, suite en verde |
| **C-03** | **Alta** | **`--no-geography` no funciona sin coordenadas.** Incumple la regla de dominio 5 | Reproducido: un nodo sin `CoordX/Y` hace fallar el alimentador |
| **C-04** | **Alta** | **Fases ignoradas.** `line.phase` existe en el modelo y se descarta: todo `StaCubic` escribe `it2p1/2/3 = 0/1/2` | `dgs.py:675`, `688`, `697` y siguientes |
| **C-05** | **Alta** | **Transformadores SED sintetizados.** 0,22 kV, Dyn5, uk = 4 %, pérdidas por fórmula; una SED por cada carga que haga *match* con una expresión regular | `dgs.py:604-614`, `model.py:15` |
| **C-06** | **Alta** | **Sustitución silenciosa de tipo de línea en modo estricto**, por distancia de edición o `DEFAULT` | `model.py:264` |
| **C-07** | **Alta** | **Sin licencia, sin instalador, y la GUI no funciona instalada** | K-01, K-02, K-03, F-04 |
| **C-08** | **Media** | **Cerrar la ventana durante un lote trunca los ficheros**; sin cancelación ni escritura atómica | F-01, F-02, K-09 |
| **C-09** | **Media** | **Sin log persistente, sin `run_id`, sin hashes: no hay soporte ni auditoría posibles** | K-06, K-07 |
| **C-10** | **Media** | **Inyección HTML/JS en la vista previa y CDN sin SRI** | K-12, K-13 |
| **C-11** | **Media** | **Datos identificables de la distribuidora sin `.gitignore`, con un script de publicación a GitHub en el repo** | K-14 |
| **C-12** | **Media** | **Sin CI, sin lint, sin tipado, sin lockfile, sin matriz de versiones** | K-10 |

### Corrección al diagnóstico del 2026-09-21

Aquel documento clasificó como **Crítica (C-01)** que «las longitudes se reemplazan siempre por distancia euclidiana». La medición de esta auditoría lo matiza: **en este export la sustitución no cambia nada**. La razón geo/TXT es exactamente **1,000 en los 38.657 tramos** (p1 = p50 = p99 = 1,000) y el total coincide en 4.185,7 km — es decir, el `Length` de CYMDIST **ya es** la longitud de la polilínea en metros, y el CRS es métrico.

El defecto no es que hoy produzca números malos, sino que **no hay nada que impida que los produzca**: no se comprueban las unidades del CRS, y la GUI ofrece precisamente la opción que lo dispara. La severidad se mantiene crítica, pero la causa y la prueba son distintas, y eso cambia la corrección: no hay que dejar de usar la georreferencia, hay que **validar las unidades del CRS y contrastar la razón geo/TXT**.

---

## 8. Plan de mejora

Ordenado por relación valor/coste, no por severidad. Las estimaciones son de esfuerzo de desarrollo, sin validación física.

### P0 — Bloqueantes de corrección y escala (1-2 semanas)

**P0.1 · Los ocho líneas de rendimiento — *hacer primero*** · ~2 h

1. Memoizar la adyacencia: `_NEIGHBOR_CACHE` en `dgs.py`, invalidada por `len(model.lines)`; o mejor, pasar el índice explícitamente a `diagram_anchor_node`, `is_micro_service_stub_line` y `diagram_line_sections` para que la dependencia sea visible en la firma.
2. Calcular `diagram_line_sections(model)` **una vez** por conversión y propagarlo, en lugar de recomputarlo en `visible_pointterm_nodes` y `diagram_line_rail_counts`.
3. `validate.py:512`: `_line_by_loc = {_loc(ln.section_id): ln for ln in model.lines}` antes del bucle.

*Aceptación:* `test_all_mode…` por debajo de 40 s; SM218 por debajo de 1 s; `84 passed` sin cambios; añadir un test de regresión de rendimiento con umbral (p. ej. el alimentador mayor en < 3 s) para que el O(N²) no vuelva.

**P0.2 · Cerrar C-01 (CRS)** · ~1-2 días

1. Pasar `source_crs` a `build_feeder_model` / `apply_georeferenced_lengths`.
2. Rechazar con error accionable cualquier CRS cuyo eje no sea lineal en metros (`pyproj.CRS(...).axis_info[0].unit_name`), o medir geodésicamente con `pyproj.Geod` cuando el CRS sea geográfico.
3. **Quitar `EPSG:4326` del desplegable de CRS de origen** o, si se mantiene, conmutar a medición geodésica.
4. Añadir al validador un control de **razón geo/TXT**: mediana, MAD y umbral por clase; error si la mediana se aparta de 1 más de una tolerancia configurable. Esto convierte la comprobación en independiente del supuesto.

*Aceptación:* el experimento de §2 (coordenadas en grados) debe **fallar** con mensaje claro, no reportar `ok`.

**P0.3 · Hacer opcional la geografía de verdad (C-03)** · ~1 día

- Ejecutar `apply_georeferenced_lengths` y la parte georreferenciada de `prove_mt_connections` **solo** si `include_geography=True`.
- Con `--no-geography`: conservar `Length` del TXT y validar únicamente topología.

*Aceptación:* test que convierta un alimentador con nodos sin `CoordX/Y` y `--no-geography`, y pase.

**P0.4 · Integridad de la salida (C-08)** · ~2-3 días

- Escritura transaccional: carpeta temporal + `os.replace` por alimentador.
- `threading.Event` de cancelación consultado en el callback de progreso de `convert_selection`; botón Cancelar en la GUI.
- `_on_close` debe comprobar `self._busy`, pedir confirmación y señalar la cancelación antes de `destroy()`.
- Escribir `batch_manifest.json` en un `finally`, con los ítems procesados hasta el momento y `status: 'cancelled'`.

*Aceptación:* cancelar a mitad de lote no deja ningún `.dgs` parcial y sí un manifiesto coherente.

**P0.5 · Aislar la colisión de nombres (K-20 / regla 3)** · ~2 h

- Sustituir el `ValueError` de `_selection` por desambiguación `<short>__<hash8(network_id)>` y aviso en el manifiesto; si se decide seguir fallando, que falle **solo ese alimentador**.

### P1 — Comercializable (3-4 semanas)

**P1.1 · Legal y empaquetado (C-07)**

- Añadir `LICENSE` y `CHANGELOG.md`; decidir modelo (propietario / comercial / dual).
- Mover `tools/powerfactory_acceptance.py` a `src/igea_dgs/powerfactory/` y `config/` a `package-data`; eliminar `_project_root()` y resolver recursos con `importlib.resources`.
- Construir ejecutable (PyInstaller *onedir*) + instalador, con `pyproj` y sus datos de proyección embebidos.

*Aceptación:* instalar en una máquina limpia sin Python y ejecutar un lote completo, incluido el botón de PowerFactory.

**P1.2 · Soporte y trazabilidad (C-09)**

- `logging` estructurado con `run_id`, a `%LOCALAPPDATA%/igea-dgs/logs/` con rotación; la GUI vuelca el mismo log al widget.
- Enriquecer `batch_manifest.json`: versión del paquete, Python, `pyproj`, perfil de esquema, SHA-256 de los tres TXT, tiempos por etapa, política de imputación aplicada.
- Botón «Exportar diagnóstico» que empaquete log + manifiesto + inventario en un ZIP para soporte.

**P1.3 · Calidad de construcción (C-12)**

- `.github/workflows/ci.yml`: Windows + Linux, Python 3.10-3.13, `ruff`, `pyright`, `pytest` con cobertura y el umbral de rendimiento de P0.1.
- Declarar `ruff` y el comprobador de tipos en `requirements-dev.txt` (el diagnóstico anterior ya señaló que `ruff` no era instalable) y fijar un *lockfile*.
- Decidir la versión mínima real: el `.venv` usa 3.14 y nada prueba 3.10.

**P1.4 · Seguridad (C-10, C-11)**

- Escapar con `html.escape` todo identificador interpolado en `popup`; serializar el GeoJSON con `json.dumps(...).replace('</', '<\\/')`.
- Empotrar Leaflet localmente o añadir `integrity` + `crossorigin`; modo *offline* por defecto.
- Añadir `referencia/*.json` y `referencia/*.dgs` a `.gitignore`; auditar el historial por si ya se publicó algo; revisar `tools/_publish_to_github.py` antes de cualquier publicación.
- Prefijar con `'` los valores que empiecen por `=`, `+`, `-`, `@` en TSV/XLSX.

**P1.5 · Parametrizar la física fijada (§3.3)**

- Perfil de red en JSON: `frnom`, kV de BT, grupo de conexión, `uk`, pérdidas, escala de diagrama. Sin valores por defecto peruanos silenciosos: si el perfil no los declara, exigirlos.
- Esto es lo que convierte «universal en nombres» en «universal en física», y abre los mercados de 50 Hz.

**P1.6 · Contrato de ingestión (K-16…K-19)**

- Informe de ingestión con fichero, sección, línea, columna, valor, regla y severidad.
- `_float`/`_int` deben distinguir *ausente* de *inválido*: lo inválido falla con ubicación exacta.
- Especificar **todos** los `ValueType` de CYMDIST con pruebas; prohibir el `Q = 0` silencioso.

### P2 — Fidelidad eléctrica (paralelizable; ver diagnóstico del 21-09)

Estos puntos no se re-desarrollan aquí porque `DIAGNOSTICO_TECNICO_2026-09-21.md` ya los especifica con criterios de aceptación. Orden recomendado:

1. **Fases extremo a extremo** (C-04): mapear `line.phase` a `it2p*`, `nlnph`, `nphase`; casos de prueba mono/bi/trifásicos.
2. **Transformadores reales** (C-05): leer catálogo/*placement*; si no existe, marcar la SED como gráfica y **no** sintetizar parámetros en modo producción.
3. **No sustituir tipos en silencio** (C-06): auto-mapeo y `DEFAULT` desactivados por defecto; exigir alias aprobado y reportar R/X/B/ampacidad de origen y destino.
4. **B1/B0 y cortocircuito de fuente**: escribir `bline`/`bline0`; exigir `snss`/`rntxn`/`z2tz1` en `ElmXnet`.
5. **Oráculo independiente**: 5-10 alimentadores dorados con modelo PowerFactory revisado por ingeniero; comparar por elemento y por resultado con tolerancias fijadas *antes* de observar.
6. Separar `converges_original_case` de `converges_after_modification` en la puerta de aceptación.

### P3 — Rendimiento avanzado (opcional, tras P0.1)

- Pre-indexar `CymdistDataset` por alimentador para eliminar B-03/B-04 (`loads_by_feeder`, `devices_by_feeder`, `intermediate_by_section`) y cachear `_catalog`.
- Eliminar la rama O(S·I) latente de `model.py:420` (B-05).
- `ProcessPoolExecutor` en `convert_selection` para el modo `--all` (B-06): los alimentadores ya son independientes por diseño.
- Refactorizar `gui.py` en vista / controlador / servicio (F-08) para que la lógica sea testable.

---

## 9. Criterios de aceptación de «comercializable»

Propuesta de definición de terminado, medible:

| # | Criterio |
| --- | --- |
| 1 | Ningún CRS de origen no métrico produce una conversión `ok`; la razón geo/TXT se valida con umbral explícito |
| 2 | `--no-geography` convierte un export sin coordenadas |
| 3 | Coste lineal en el número de tramos; test de regresión de rendimiento en CI |
| 4 | Un alimentador de 20.000 tramos convierte en menos de 30 s |
| 5 | Cancelar o cerrar durante un lote no deja ningún artefacto parcial |
| 6 | Instalación en máquina limpia sin Python, con el flujo de PowerFactory funcional |
| 7 | `LICENSE`, `CHANGELOG` y manual de operador presentes |
| 8 | Todo resultado trazable: `run_id`, hashes de entrada, versiones y tiempos en el manifiesto |
| 9 | CI en verde en Windows y Linux, Python 3.10 a 3.13, con lint, tipado y cobertura de ramas |
| 10 | Vista previa sin inyección posible y operativa sin acceso a internet |
| 11 | Cero datos identificables de distribuidora publicables por accidente |
| 12 | Física de red parametrizada por perfil: 50 y 60 Hz, BT y grupo de conexión configurables |
| 13 | Fase preservada en el 100 % de los elementos |
| 14 | Cero sustituciones de parámetro eléctrico sin aprobación explícita registrada |
| 15 | Comparación contra oráculo independiente dentro de tolerancias fijadas *a priori* |

Los criterios 1-12 son los que separan el estado actual de un producto vendible y son de coste acotado. Los 13-15 son la validación científica y son el trabajo largo.

---

## 10. Conclusión

El trabajo de ingeniería es real y la aceptación en PowerFactory es un activo poco frecuente. Lo que esta auditoría aporta es que **los obstáculos más caros no son los que parecían**.

El diagnóstico anterior situaba el cuello de botella en la trazabilidad física, y tiene razón en el largo plazo. Pero medido hoy: el 95 % del CPU se pierde en dos bucles que ocho líneas corrigen; el defecto más peligroso es un elemento de un menú desplegable; y lo que impide vender no es la física sino la ausencia de licencia, instalador, log y CI.

**Orden recomendado: P0.1 primero** — dos horas de trabajo, 21× de mejora, suite en verde, y establece el test de regresión que evita que el O(N²) regrese. Después P0.2, que cierra un defecto capaz de entregar a un cliente un modelo eléctricamente falso con el sello `errors_total = 0`.
