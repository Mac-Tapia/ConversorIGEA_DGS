# Catálogo de la arquitectura

Generado por `tools/generar_arquitectura.py` (spec 090): **no se edita a mano**. Un gancho de git lo regenera en cada
commit y en cada fusión, y `tests/test_arquitectura_generada.py` falla si no está al día. Si hace falta a mano:
`python tools/generar_arquitectura.py --escribir`. Lo que explica el porqué está en [`ARQUITECTURA.md`](ARQUITECTURA.md).

## Cifras

| Parte | Carpeta | Ficheros |
| --- | --- | --- |
| Motor, web, gemelo y asistente | `src/convertersmartgrid/` | 302 |
| Motor, web, gemelo y asistente | `src/convertersmartgrid/` | 296 |
| Módulo VNR-GIS | `src/convertersmartgrid/adaptadores/entrada/vnr/` | 50 |
| Herramientas y guiones | `tools/` | 98 |
| Interfaz | `frontend/src/` | 49 |
| Pruebas de la interfaz | `frontend/test/` | 12 |
| Pruebas | `tests/` | 403 |
| Pruebas | `tests/` | 401 |
| Pruebas de modelos | `tests_ml/` | 6 |
| Specs | `specs/` | 295 |

`web/services.py` tiene 12601 líneas y 382 funciones, pendiente de partir (002).

### Specs

| Estado | Specs |
| --- | --- |
| cumplida | 51 |
| implementada | 30 |
| aprobada | 16 |
| reservada | 1 |
| retirada | 1 |

99 specs con 3247 RF. El detalle, en [`specs/README.md`](../specs/README.md).

### Capas

| Capa | Abrev. | Módulos |
| --- | --- | --- |
| adaptadores | Ada | 120 |
| aplicacion | Apl | 101 |
| dominio | Dom | 36 |
| adaptadores | Ada | 119 |
| aplicacion | Apl | 100 |
| dominio | Dom | 33 |
| presentacion | Pre | 32 |
| puertos | Pue | 3 |

292 módulos y 34 excepciones en la deuda de `tools/arquitectura.py`.
286 módulos y 37 excepciones en la deuda de `tools/arquitectura.py`.

### Carriles de trabajos

`engine`, `powerfactory`, `asistente`, `control`.

### Rutas de la API

145 en `web/app.py`, y 13 bajo `/api/vnr` en `adaptadores/entrada/vnr/web/app.py`.

| Familia | Ámbito | Rutas |
| --- | --- | --- |
| `demanda` | espacio | 25 |
| `pf` | espacio | 20 |
| `informes` | espacio | 11 |
| `asistente` | espacio | 8 |
| `powerfactory` | espacio | 8 |
| `digital-twin` | espacio | 7 |
| `asistente` | general | 6 |
| `lote` | espacio | 4 |
| `catalog` | espacio | 3 |
| `inputs` | espacio | 3 |
| `obras` | espacio | 3 |
| `pide` | espacio | 3 |
| `jobs` | general | 3 |
| `sistema` | general | 3 |
| `(raíz)` | espacio | 2 |
| `agente` | espacio | 2 |
| `convert` | espacio | 2 |
| `feeders` | espacio | 2 |
| `outputs` | espacio | 2 |
| `runs` | espacio | 2 |
| `source-scope` | espacio | 2 |
| `vnr` | espacio | 2 |
| `workspaces` | general | 2 |
| `cargas` | espacio | 1 |
| `diagnose` | espacio | 1 |
| `estructura` | espacio | 1 |
| `events` | espacio | 1 |
| `files` | espacio | 1 |
| `inputs-auto` | espacio | 1 |
| `load` | espacio | 1 |
| `no-disponibles` | espacio | 1 |
| `options` | espacio | 1 |
| `outputs.zip` | espacio | 1 |
| `reconstruct` | espacio | 1 |
| `restaurar-copia` | espacio | 1 |
| `system` | espacio | 1 |
| `ws` | espacio | 1 |
| `health` | general | 1 |
| `modelos` | general | 1 |
| `pf` | general | 1 |
| `powerfactory` | general | 1 |
| `vnr` | general | 1 |
| `{full_path:path}` | general | 1 |

### Órdenes y módulos instalados

| Orden | Punto de entrada |
| --- | --- |
| `convertersmartgrid` | `convertersmartgrid.cli:main` |
| `convertersmartgrid-web` | `convertersmartgrid.web.__main__:main` |
| `vnr-etl` | `convertersmartgrid.adaptadores.entrada.vnr.cli:main` |

| Módulo enchufable | Objeto |
| --- | --- |
| `escritor-dgs` | `convertersmartgrid.escritores:MODULO_DGS` |
| `lector-mdb` | `convertersmartgrid.sources.mdb:MODULO` |
| `lector-txt` | `convertersmartgrid.sources.txt:MODULO` |
| `lector-vnr` | `convertersmartgrid.sources.vnr:MODULO` |

## El asistente y su equipo

El intérprete acepta al modelo de órdenes con confianza 0.85, salvo que traiga su umbral calibrado, y a Ollama con 0.6.

### Equipo

| Rol | Ejecuta | Lee el proyecto | Encargo |
| --- | --- | --- | --- |
| `operador` | sí | sí | Confirma cada escritura y es el único que ejecuta. |
| `fuentes` | no | sí | Revisa si cada afirmación de la propuesta está en la evidencia citada, con el mismo valor. |
| `fisica` | no | sí | Revisa la consistencia física: tensiones, cargas y límites de la propuesta frente a los de la evidencia. |
| `coste` | no | sí | Revisa los costes y cantidades de la propuesta frente a los precios y cantidades de la evidencia. |
| `riesgo` | no | sí | Revisa el riesgo de operación: si, según la evidencia, la propuesta deja cargas sin respaldo o sin servicio. |
| `cliente_mcp` | no | sí | Un cliente MCP de esta máquina: solo las lecturas del proyecto. |

### Tareas (48)

Carril donde corre si se ejecuta; `opcional?` es un dato que no hace falta dar. «Producto» dice si queda en esa edición.

| Tarea | Modo | Escribe | Carril | Producto | Función | Datos | Qué hace |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `estado` | consulta | no | engine | sí | `feeder_rows` | — | Qué hay cargado en el espacio, sus alimentadores, trabajos y salidas. |
| `proyectos` | consulta | no | engine | sí | `pf_proyectos_guardados` | — | Los proyectos de DIgSILENT que la web ya conoce. |
| `resultados_pide` | consulta | no | engine | sí | `pide_ejecutar` | proyecto? | Las obras, prioridades y formatos del último PIDE de un proyecto. |
| `episodios` | consulta | no | engine | no | `gemelo_episodios` | proyecto? | Los episodios del gemelo digital por clase y caso. |
| `pregunta` | consulta | no | engine | no | `asistente_pregunta` | texto | Cómo funciona el conversor, con cita de ficheros, funciones y RF. |
| `clasificar_informe` | consulta | no | engine | sí | `asistente_clasificar` | texto | A qué tipo y subtipo de estudio corresponde un informe o un pedido. |
| `buscar_internet` | consulta | no | engine | sí | `asistente_buscar` | texto | Busca librerías, proyectos o artículos, sin datos de la red (RF-29). |
| `leer_proyectos` | trabajo | no | powerfactory | sí | `pf_projects` | — | Lee de DIgSILENT la lista de proyectos. |
| `evaluar_gemelo` | trabajo | no | engine | no | `gemelo_evaluar` | — | Cuánto se apartan de DIgSILENT el modelo del gemelo y la física (024:RF-74). |
| `cargar_fuente` | trabajo | sí | engine | sí | `load_dataset` | — | Carga la fuente asignada al espacio. |
| `convertir` | trabajo | sí | engine | sí | `convert` | alimentadores | Convierte alimentadores a DGS, uno por fichero. |
| `unir` | trabajo | sí | engine | sí | `convert_group` | alimentadores | Convierte varios alimentadores en una red unida. |
| `convertir_sistema` | trabajo | sí | engine | sí | `convert_group` | sistema | Convierte un sistema eléctrico a un DGS por sistema. |
| `sistema_completo` | proceso | sí | powerfactory | sí | `sistema_web` | sistema, periodo, ruta? | Sistema eléctrico de punta a punta: convertir, importar y calibrar (022:RF-56). |
| `flujo` | trabajo | sí | powerfactory | sí | `powerfactory_flow` | alimentadores | Flujo de potencia en DIgSILENT de los alimentadores. |
| `verificar_caso_base` | trabajo | sí | powerfactory | sí | `pf_verificar_base` | proyecto, alimentadores? | Verifica el «Caso base» frente al archivo original (spec 015). |
| `cargas_nuevas` | trabajo | sí | powerfactory | sí | `cargas_ejecutar` | proyecto, alimentadores, ruta | Integra las cargas nuevas de un Excel en «Con proyecto» (specs 007 y 014). |
| `obras` | trabajo | sí | powerfactory | sí | `obras_ejecutar` | proyecto, alimentadores | Aplica en DIgSILENT las obras pendientes del espacio (spec 011). |
| `estudios` | trabajo | sí | powerfactory | sí | `estudios_ejecutar` | proyecto, alimentadores, estudio? | Estudios de la red en los casos del proyecto (spec 011). |
| `obras_escalera` | trabajo | sí | powerfactory | sí | `obras_escalera` | proyecto, alimentadores, ruta? | Escalera de obras en «Con proyecto»: bancos, sección y terna hasta dejar la red en norma (025:RF-44). |
| `optimizar_con_proyecto` | trabajo | sí | powerfactory | sí | `con_proyecto_optimizar` | proyecto, alimentadores, ruta?, set? | Optimiza «Con proyecto»: escalera carga a carga y SET nueva para las que no caben (042:RF-13, spec 052). |
| `transferencia` | trabajo | sí | powerfactory | sí | `transferencia_ejecutar` | proyecto, alimentadores | Transferencia de carga entre dos alimentadores (spec 011). |
| `pide` | trabajo | sí | powerfactory | sí | `pide_ejecutar` | proyecto, alimentadores, periodo? | Metodología del PIDE: diagnóstico, obras propias y formatos (024, T13 y T14). |
| `gemelo_aprender` | trabajo | sí | powerfactory | no | `gemelo_aprender` | proyecto, alimentadores, numero? | Aprendizaje activo del gemelo: escenarios en una copia del proyecto (024, T10). |
| `gemelo_entrenar` | trabajo | sí | engine | no | `gemelo_entrenar` | — | Reentrena el oráculo PINN del gemelo con lo que hay en el búfer (024, T11). |
| `gemelo_temporal` | trabajo | sí | engine | no | `gemelo_temporal` | alimentadores? | Gemelo temporal del mes con las curvas de la última máxima (024, T12). |
| `informe_estudio` | trabajo | sí | engine | sí | `informe_estudio` | proyecto, alimentadores, subtipo? | Informe de estudio eléctrico en Word (spec 017). |
| `informe_factibilidad` | trabajo | sí | powerfactory | sí | `informe_factibilidad` | proyecto, alimentadores, sed, subtipo? | Informe de factibilidad de una carga nueva (spec 017). |
| `consultar_datos` | consulta | no | engine | sí | `sed_de_alimentador` | alimentadores?, proyecto?, set?, periodo? | Consulta lo que hay: alimentadores, SED, medidores, clientes fijos, máximas buscadas, años de medición, catálogo, variaciones escaneadas, proyectos y última calibración, con su fuente (070:RF-41). |
| `no_disponible` | consulta | no | engine | sí | `estudios_catalogo` | estudio?, proyecto? | Dice por qué un estudio no está disponible: cortocircuito, protecciones, optimización no lineal y los que el catálogo no ofrece, sin ejecutar nada (070:RF-47). |
| `evaluar_carga_nueva` | etapas | sí | powerfactory | sí | `agente_proyecto` | proyecto, alimentadores, sed, periodo?, ruta? | Evalúa una carga nueva de una vez: diagnóstico, calibración si hace falta, carga, informe y obras solo si hay problemas (070:RF-50). |
| `cancelar_trabajo` | trabajo | sí | engine | sí | `pf_projects` | — | Cancela los trabajos en curso del espacio, nombrándolos antes (070:RF-32). |
| `convertir_set` | trabajo | sí | engine | sí | `sistema_seleccion` | set | Convierte una SET sola, con sus alimentadores y su barra (022:RF-82). |
| `set_completo` | proceso | sí | powerfactory | sí | `sistema_web` | set, periodo, ruta? | Una SET de punta a punta: convertir, importar y calibrar con su máxima de barra (070:RF-21). |
| `alimentadores_completo` | proceso | sí | powerfactory | sí | `sistema_web` | alimentadores, periodo, ruta? | Uno o varios alimentadores de punta a punta: convertir, importar y calibrar (028:RF-25). |
| `buscar_maxima` | trabajo | no | engine | sí | `demanda_cabecera` | alimentadores?, set?, sistema?, periodo?, alcance? | Busca la máxima según el alcance: alimentadores, SET o sistema (028:RF-27). |
| `cruzar_clientes` | trabajo | no | engine | sí | `demanda_clientes` | alimentadores?, periodo? | Cruza los clientes de la máxima ya buscada: quiénes quedan fijos (035:RF-1). |
| `calibrar` | trabajo | sí | powerfactory | sí | `ajuste_plan` | proyecto | Calibra un proyecto con la última máxima buscada: prepara el plan y lo aplica (spec 006). |
| `simular_calibracion` | trabajo | sí | powerfactory | sí | `ajuste_plan` | proyecto | Simula la calibración de un proyecto con la última máxima, sin aplicarla (spec 006). |
| `recalibrar` | proceso | sí | powerfactory | sí | `sistema_web` | proyecto, periodo, ruta? | Recalibra un proyecto ya importado, sin reconvertir (028:RF-21). |
| `escanear` | trabajo | no | powerfactory | sí | `escanear_alimentadores` | proyecto, alimentadores | Lee del proyecto generadores, bancos y lo cambiado a mano, sin escribir (spec 028). |
| `verificar_convergencia` | trabajo | no | powerfactory | sí | `pf_verificar` | proyecto, alimentadores? | Corre el flujo con lo activo para ver si el proyecto converge, sin grabar (008:RF-18). |
| `carga_nueva_sola` | trabajo | sí | powerfactory | sí | `cargas_plan` | proyecto, alimentadores, sed | Conecta una carga nueva sola, con el formulario de 3.2 (008:RF-24, 070:RF-29). |
| `proyecto_entero` | etapas | sí | powerfactory | sí | `agente_proyecto` | sistema, periodo, ruta? | El proyecto entero de un sistema, etapa por etapa, con la lista de etapas a la vista (027:RF-43). |
| `leer_solicitud` | trabajo | sí | engine | sí | `informe_documentos` | ruta | Lee los PDF del solicitante y propone sus datos, sin rellenar el formulario (017:RF-137). |
| `descargar_resultados` | trabajo | no | engine | sí | `feeder_rows` | alimentadores? | Prepara el ZIP de los resultados y da el enlace para bajarlo (spec 001). |
| `pronostico` | trabajo | sí | engine | no | `gemelo_temporal` | ruta, alimentadores? | Pronóstico de demanda de cabecera o de clientes fijos, con su competencia de modelos (spec 046). Es un pronóstico, nunca una medición. |
| `entrenar_asistente` | proceso | sí | engine | no | `asistente_entrenar` | — | Reentrena el Transformer de órdenes y, solo si hay informes reales en su prueba, el clasificador de informes; lo que no pase sus puertas deja el modelo en uso (026:RF-20, 067:RF-28). |

### Etapas del proyecto entero

| Etapa | Tarea | Opcional | Proceso aparte | Condición |
| --- | --- | --- | --- | --- |
| `fuente` | `cargar_fuente` | no | no | — |
| `sistema` | `sistema_completo` | no | sí | — |
| `caso_base` | `verificar_caso_base` | no | no | — |
| `cargas_nuevas` | `cargas_nuevas` | sí | no | — |
| `obras` | `obras` | no | no | — |
| `estudios` | `estudios` | no | no | — |
| `pide` | `pide` | no | no | — |
| `informe` | `informe_estudio` | sí | no | — |

### Etapas de una carga nueva

| Etapa | Tarea | Opcional | Proceso aparte | Condición |
| --- | --- | --- | --- | --- |
| `diagnostico` | `verificar_convergencia` | no | no | — |
| `calibracion` | `recalibrar` | no | sí | sin_calibracion |
| `carga` | `carga_nueva_sola` | no | no | — |
| `evaluacion` | `informe_factibilidad` | no | no | — |
| `obras` | `optimizar_con_proyecto` | no | no | si_no_factible |
| `informe` | `informe_factibilidad` | no | no | si_hubo_obras |

### Familias de modelos

Orden de entrenamiento: `transformer`, `clasificador`, `gru`, `pinn`, `evolutivos`, `embeddings`, `qlora`.

Con puntero en uso gobernado por `asistente/modelos_en_uso.py`: `clasificador` (informes), `transformer` (ordenes).
Qué modelo está en uso vive en `output/`, fuera de git: ver [`ARQUITECTURA.md`](ARQUITECTURA.md#modelos-024-026-043-045-046-060-069-075-079-085).

## Ficheros

Papel, specs y capa salen de `CODIGO_FUENTE.md` y `pyproject.toml`. El subsistema, de `docs/architecture/subsistemas.json`.
Las pruebas no se listan: cada una cita los `NNN:RF-n` que cubre.

### Motor: transversales

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `__init__.py` | Dom | 034 | Paquete del motor y su versión. |
| `util.py` | Dom | 001, 086 | SHA-256, JSON atómico y duradero, con copia anterior, y números: una sola implementación. |
| `runtime_paths.py` | Dom | 065, 086 | Raíces externas, identidad estable de la instalación, staging por volumen o junto al destino, custodia y reconciliación de temporales. |
| `naming.py` | Dom | 034, 011 | Nombres y selectores de alimentador. |
| `perfil_empresa.py` | Dom | 002, 020, 021, 025 | Perfil de empresa: CRS de origen, patrón de las SED de medición, escala del diagrama y forma de los alimentadores, fuera del código. |
| `perfil_esquema.py` | Ada | 086 | Valida un perfil contra su esquema: valores imposibles, claves desconocidas y lo que falta con la función que afecta. |
| `edicion.py` | Dom | 086 | Qué edición corre y qué entrega la de producto: rutas y tareas fuera de alcance, y funciones en beta. |
| `salidas_red.py` | Dom | 086 | Lista de cada salida a la red con su interruptor: encendidas en desarrollo, apagadas en la edición de producto. |
| `sesion_web.py` | Dom | 086 | Token de la sesión de la web: el lanzador lo crea en un fichero solo del usuario y los clientes locales lo leen. |
| `registro_rotativo.py` | Ada | 086 | Registro del programa en ficheros rotativos, fuera de la carpeta del programa. |
| `cli.py` | Pre | 001, 022 | Orden `convertersmartgrid`: `list`, `convert` y `web`.; `--por-sistema [ZONAL]` y `--estructura`, aparte de `--unir` |

### Motor: entrada de datos

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `sources/__init__.py` | Ada | 001 | Registro de adaptadores, común a la web y al CLI. |
| `sources/base.py` | Pue | 001 | Contrato de los lectores de las tres procedencias. |
| `sources/txt.py` | Ada | 001 | Adaptador de los tres TXT. |
| `sources/mdb.py` | Ada | 001 | Adaptador de base Access. |
| `sources/vnr.py` | Ada | 001, 053 | Adaptador de un paquete VNR-GIS. |
| `sources/snapshot.py` | Dom | 001 | Qué ficheros forman una lectura y su huella. |
| `source_contract.py` | Dom | 001, 004, 006 | Contrato canónico y evidencia de auditoría compartidos por TXT, MDB y VNR-GIS. |
| `dataset.py` | Ada | 034 | Lector de los TXT (RED, CARGA, BD_Equipo), en las dos disposiciones. |
| `access.py` | Ada | 034, 001 | Lector de la base Access de CYMDIST (`.mdb`), la segunda vía de entrada. |
| `identify.py` | Ada | 034, 059 | Reconoce cada TXT por su contenido, no por su nombre, y a qué fuente (TXT, Access o VNR-GIS) pertenece un fichero. |
| `study.py` | Ada | 034 | Estudio de CYMDIST (`.zxst`/`.xst`), entrada opcional que filtra la selección. |
| `inventory.py` | Apl | 034 | Inventario detallado de un dataset cargado. |
| `feeder_metadata.py` | Ada | 034, 022 | Procedencia por alimentador de los objetos de una red conjunta.; la red externa de una barra de SET, una vez con sus alimentadores |

### Motor: reconstrucción y catálogo

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `reconstruction.py` | Dom | 001 | Contrato de la reconstrucción auditable del dataset. |
| `reconstruction_pipeline.py` | Apl | 001 | Reconstrucción de una selección de alimentadores, sin estado de la web. |
| `reconstruction_topology.py` | Dom | 001 | Reconstrucción determinista de la topología. |
| `catalog.py` | Apl | 034, 053 | Catálogo de parámetros eléctricos: tabla de entrada y auditoría del modelo. |
| `catalog_data.py` | Dom | 034 | Datos de fabricante y de norma para los parámetros eléctricos. |
| `catalog_merge.py` | Apl | 034, 001 | Completa el catálogo de equipos cuando el export llega incompleto. |
| `catalog_resolution.py` | Dom | 001 | Resolución de equipos por evidencia, sin renombrar los códigos de origen. |
| `coordenadas.py` | Dom | 034 | Completa las coordenadas que faltan con el grafo de la red. |

### Motor: modelo y reglas

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `model.py` | Dom | 034 | Modelo eléctrico de un alimentador. |
| `reglas.py` | Apl | 034, 002, 021, 022, 032, 057 | Reglas que se aplican a todo alimentador, venga de TXT o de base. |
| `puentes.py` | Dom | 034, 021 | Funde los tramos puente de CYMDIST en vez de modelarlos como líneas. |
| `trafomix.py` | Dom | 034, 002, 021 | Equipos de medición en MT que la base registra como SED, con el patrón del perfil de empresa. |
| `sed_potencia.py` | Dom | 034, 057 | Lleva al tamaño normalizado las SED cuya carga supera su transformador. |
| `fases_red.py` | Dom | 054 | Qué fases le llegan a cada tramo y SED desde la cabecera. |
| `comprobacion_fases.py` | Dom | 081 | Contrato de fases de toda la clase de fallos: ningún elemento con más fases que su barra ni con fases que no le llegan, en cualquier fuente. |
| `geography.py` | Ada | 034, 001 | Del CRS de origen a WGS84. |
| `capacidades.py` | Ada | 015 | Capacidades, grupo de conexión y tensión de baja de transformadores y líneas del DGS original, y su comparación con lo leído en DIgSILENT. |

### Motor: conversión, red unida y oráculo

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `batch.py` | Apl | 034, 001, 022, 065 | Conversión de uno, varios o todos los alimentadores, en serie o en paralelo.; la red unida por zonal y SET con su informe, aperturas y oráculo |
| `combine.py` | Apl | 034, 022 | Une todos los alimentadores en una sola red. |
| `enlaces.py` | Apl | 022 | Puntos de enlace de la red unida con sus SET y caminos cerrados (entre SET, entre alimentadores, anillos): abre la maniobra más lejana de su fuente… |
| `estructura.py` | Apl | 022, 055 | La estructura de la empresa: zonales, SET (con sus siglas) y alimentadores con su sistema eléctrico, sector típico y norma. |
| `oraculo.py` | Ada | 034, 022, 057, 082 | Flujo independiente con pandapower antes de escribir el DGS. |
| `resolver_convergencia.py` | Dom | 081 | Si el «Caso base» no converge: su causa, corregir lo reconstruible, volver a medir, y decir lo que queda con su elemento y qué hacer. |
| `preflight_contract.py` | Apl | 065 | Contrato JSON del modelo efectivo, fijado al DGS antes de su importación. |
| `comprobacion_flujo.py` | Dom | 081 | Lo que un flujo o una calibración dijeron frente a lo que pasó: barras de baja a 0 p.u., cargas que no consumen, estado verdadero del trabajo y… |

### Motor: salida y módulos enchufables

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `schema.py` | Ada | 034, 054 | Perfiles de esquema DGS versionados. |
| `schemas/pf21_dgs_1_8_4.json` | — | 034 | Perfil DGS genérico de PowerFactory. |
| `schemas/perfil_empresa_v1.schema.json` | — | 086 | Esquema del perfil de empresa: cada clave con su tipo, la función que afecta, qué se hace sin ella y si es de la empresa o de una norma. |
| `schemas/protecciones_v1.schema.json` | — | 049 | Contrato del dispositivo de protección (campos obligatorios, clases con su clase de PowerFactory, unidades admitidas y campos que pide cada unidad o… |
| `schemas/asistente_orden_v1.schema.json` | — | 047 | Contrato base de salida estructurada para el intérprete local. |
| `schemas/revision_propuesta_v1.schema.json` | — | 047 | Contrato del dictamen de un rol: lo que se pide a Ollama y lo que se valida. |
| `schemas/digital_twin_episode_v1.schema.json` | — | 024 | Esquema JSON publicado del episodio del gemelo digital, igual al contrato de `digital_twin/episode.py`. |
| `schemas/digital_twin_episode_v2.schema.json` | — | 045 | Esquema JSON del episodio v2: cuatro casos y contexto físico con su identidad nativa y sus huellas. |
| `dgs.py` | Ada | 034, 010, 011, 128, 021, 022, 054 | Escritor DGS: tablas, FID, cubículos, maniobras, capa gráfica y trazado GPS de las líneas. |
| `validate.py` | Ada | 034, 010, 021, 022, 054 | Validación del DGS escrito, con el trazado GPS de cada línea.; reconoce la red por zonal y SET |
| `export_tables.py` | Ada | 034 | DGS a Excel multihoja o TSV. |
| `preview.py` | Ada | 034, 086 | Vista previa georreferenciada del modelo, con Leaflet propio dentro del fichero y su política de contenido. |
| `recursos/NOTAS_VERSION.md` | — | 086 | Notas de la versión que muestra la pantalla «Acerca de». |
| `recursos/leaflet/leaflet.js` | — | 086 | Leaflet, copia exacta con huella comprobada. |
| `recursos/leaflet/leaflet.css` | — | 086 | Estilos de Leaflet, copia exacta con huella comprobada. |
| `recursos/leaflet/LICENSE` | — | 086 | Licencia de la copia de Leaflet que sirve la propia web, sin salir a internet. |
| `puertos.py` | Pue | 002 | Interfaces y versión de los módulos enchufables. |
| `registro_modulos.py` | Apl | 002 | Descubre, filtra y carga los módulos. |
| `escritores.py` | Ada | 002 | El escritor DGS como módulo y la entrega del modelo auditado a un escritor. |

### Motor: enlace con DIgSILENT

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `pf_arnes.py` | Ada | 019, 064, 091 | Arnés de DIgSILENT: turno del motor de la máquina, conexión común con reintento, caso restituido y proceso que se queda abierto. |
| `pf_estado.py` | Ada | 064 | Foto del estado de DIgSILENT antes de una orden del servidor (caso, hora, escenario, variaciones) y su restitución si la orden falla. |
| `powerfactory_env.py` | Ada | 034 | Dónde está la API de PowerFactory y qué intérprete la carga. |
| `powerfactory_metadata.py` | Ada | 034, 078 | Procedencia del conversor en los objetos de PowerFactory, y la lectura única del flujo y su clasificación. |
| `powerfactory_binding.py` | Ada | 004, 006, 011, 015, 078 | Vínculo auditable entre ejecución fuente, DGS, inventario releído y proyecto nativo aceptado, con el estado del «Caso base» de cada alimentador. |
| `native_action.py` | Dom | 004, 006, 011 | Contexto firmado fuente–proyecto–alimentadores y vocabulario común de resultados para toda acción nativa. |
| `carpeta_pf.py` | Ada | 005, 011 | Carpeta de DIgSILENT donde quedan los proyectos importados. |
| `studies.py` | Apl | 034, 012, 056 | Qué estudios de PowerFactory se pueden correr y qué dato falta para cada uno. |
| `estadistica_ordenes.py` | Dom | 081 | Estadística de las órdenes de DIgSILENT: registro por orden, descriptiva con IC 95 %, contraste de versiones (Mann-Whitney, Fisher) y fallos que se… |

### Motor: demanda y calibración

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `demanda_medida.py` | Apl | 004, 013, 021, 022, 025, 038, 039, 060, 088, 089, 091 | Máxima de cabecera por medidor y clientes importantes con su SED. |
| `libros_por_anio.py` | Apl | 025 | Libros de demanda por año de medición: árbol de libros con su año (carpeta de cuatro cifras a cualquier altura) y su ruta relativa, años disponibles… |
| `cabecera_ancha.py` | Apl | 051 | Medición de cabecera entregada a lo ancho (una columna por alimentador, fecha y hora en dos columnas, hojas de activa y reactiva) y tablas de máximas… |
| `loads.py` | Ada | 004 | Lector de libros de cargas por SED (columnas, potencia y FP), que usa `cargas_pf.py`. |
| `cargas_pf.py` | Apl | 004, 007, 008, 016, 030, 093, 099 | Lectura de los libros de demandas y cargas nuevas, y plan para DIgSILENT. |
| `ajuste_cabecera.py` | Dom | 006, 021, 035, 041, 095 | Reparto y cuadre de las demandas a la máxima de cabecera, sin DIgSILENT. |
| `oraculo_calibracion.py` | Ada | 083 | El oráculo antes de calibrar: los factores de arranque, sin gastar flujos de DIgSILENT. |
| `crecimiento.py` | Apl | 029 | Tasa anual de crecimiento de la demanda de cada alimentador desde la medición de cabecera: máximas de los meses comunes del primer y el último año,… |
| `valle.py` | Apl | 073 | El valle de un alcance desde la medición: limpieza de lo dudoso con su motivo, energía de sus medidores, inicio y duración por búsqueda exacta, por… |
| `escaneo.py` | Apl | 028 | Reglas del escaneo de un alimentador antes de recalibrar: de quién es cada generador, banco y variación por los prefijos del conversor, resumen y… |
| `transferencia_operador.py` | Dom | 098 | Transferencias de carga del operador: qué SED están transferidas, qué zona forman, qué abrir y qué cerrar para calibrar con la red de la fuente, y lo… |
| `trafos_sed.py` | Apl | 020 | Transformador nuevo para una SED fija sobrecargada: la menor potencia de la tabla de fichas del perfil (por tensión primaria) con la máxima en el… |
| `economia.py` | Dom | 004 | Datos de la evaluación técnico-económica (`ComTececo`). |

### Motor: obras y optimización

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `obras_pf.py` | Apl | 011, 016, 042, 048, 098 | Obras de mejora sin DIgSILENT: modelo y validación de cada obra (lo de «Sin proyecto» pasa a «Con proyecto». |
| `troncal.py` | Ada | 016 | Troncal de las obras sin DIgSILENT: camino continuo más largo desde la cabecera sobre el árbol de caminos más cortos en metros (anillos cerrados… |
| `escalera_optima.py` | Apl | 025, 073, 098 | Escalera optimizada de obras: variantes en el orden bancos, regulador, terna y sección con sus combinaciones, criterio de «no empeorar» por sorteo,… |
| `optimizacion_oraculo.py` | Apl | 052, 073, 098 | «Con proyecto» optimizado con el flujo del gemelo: obras sobre el grafo, búsqueda bayesiana (Optuna), frente de Pareto (NSGA-II), sorteos de Markov y… |
| `perfil_tension.py` | Apl | 094 | Perfil de tensión de un alimentador (tensión de cada barra de media frente a su distancia eléctrica) y bancos ubicados según el perfil hasta la… |
| `catalogo_reguladores.py` | Apl | 025 | Reguladores de tensión de catálogo (Eaton VR-32, 50 Hz): unidad por tensión del sistema y por corriente, y los datos de su `TypVoltreg`. |
| `instalacion_ternas.py` | Apl | 084 | Dos o más ternas subterráneas: una por ducto, triangular o rectangular, y la capacidad del fabricante para esa configuración, de la tabla del perfil. |
| `set_nueva.py` | Apl | 042 | SET nueva para las cargas que la red existente no atiende: potencia de diseño a la vida útil con la tasa de la 029 y el factor de seguridad, módulo… |
| `sitio_set.py` | Apl | 084 | Sitio de una SET nueva: distancia al trazado de los alimentadores y a las calles de un fichero local, punto apartado y «sin verificar en plano» si… |
| `vias.py` | Apl | 016 | Trazado de una línea nueva por la vía pública con un enrutador OSRM (OpenStreetMap): ruta con sus curvas, largo con los accesos, metros fuera de vía… |
| `madrl_obras.py` | Ada | 074 | Entorno multiagente de obras, sus controles, su fidelidad contra DIgSILENT y la puerta del aprendizaje. |
| `madrl_politica.py` | Ada | 074 | Política GATv2 compartida entre agentes, con crítico central y PPO, del piloto MADRL. |

### Motor: estudios

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `estudios_pf.py` | Apl | 011, 012, 049 | Estudios sobre los casos «Sin proyecto» y «Con proyecto», sin DIgSILENT: qué estudios se ofrecen (los de la 012 según el libro de la empresa y la… |
| `estudios_red_pf.py` | Apl | 012 | Resultados de confiabilidad y capacidad sin DIgSILENT: índices por alimentador y su comprobación por cargas, ENS total y diferencias, aportes, mejora… |
| `datos_empresa.py` | Apl | 012, 049 | Libro de la empresa de la confiabilidad, la capacidad y las protecciones: hojas, columnas y unidades validadas con hoja, fila y columna. |
| `protecciones.py` | Apl | 049 | Estudio de protecciones sin DIgSILENT: contrato de cada ajuste (modelo, unidades, TC/TT, poder de corte y procedencia), fila DEFAULT de la fuente que… |
| `transferencia_pf.py` | Apl | 011, 110, 117, 121, 123, 125, 129 | Transferencia de carga sin DIgSILENT: pasos del camino y carga transferida, viabilidad y elemento que limita, máximo por seccionador y por nodo,… |

### Motor: informes

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `informes.py` | Ada | 017, 107, 108, 115, 121, 122, 128, 129, 132, 134 | Informes de estudio eléctrico y de factibilidad sin DIgSILENT: qué toman del perfil de empresa (modelos, banda y umbral, bandas de coloreado,… |
| `informe_docx.py` | Ada | 017, 106, 113, 114, 118, 120, 122, 128, 132, 135 | Escribe en Word los informes de estudio eléctrico y de factibilidad como esquemas generales sobre el modelo de la empresa: de él solo la forma… |
| `libro_informe.py` | Ada | 066 | El libro Excel de cada informe, relleno desde el modelo de la empresa con el plano de su perfil |
| `libros_informe.py` | Ada | 017 | Libro de pérdidas de la empresa (sistema eléctrico, % reconocidos en potencia y energía, precio de compra), buscado por los nombres de hojas y… |
| `mapa_informe.py` | Ada | 017, 116, 133 | Imágenes del informe de estudio (ubicación, tensión, cargabilidad y detalle de las obras) con el GPS y los resultados del flujo de DIgSILENT. |
| `documentos_solicitud.py` | Ada | 017, 136, 141 | PDF del solicitante (carta, oficio, ficha del punto de diseño): capa de texto por página y, en las escaneadas, OCR con Tesseract y la imagen… |

### Motor: PIDE y planeamiento

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `pide.py` | Apl | 024 | Metodología del PIDE (RM 428-2017-MEM/DM): proyección y densidad de carga por cuadrículas de la Tabla N.º 2, diagnóstico con su causa (caída, FP,… |
| `pide_economia.py` | Apl | 024, 073 | Evaluación económica y priorización del PIDE: libro CAPEX por nombres del perfil (sin datos personales), anualidad, costo anual, VAN y TIR del art. |
| `pide_dataset.py` | Ada | 024 | Corpus PIDE universal desde un expediente de la empresa en solo lectura: custodia, calidad y fragmentos de texto. |
| `estudio_planeamiento.py` | Dom | 072 | Estudio de planeamiento: del año de presentación, cada 4 años, salen el año 00 y los años de largo plazo y del PIDE. |
| `proyeccion_mercado.py` | Apl | 072 | Proyección anual por sistema desde el Formato 01: métodos comparados contra lo ocurrido, sin mirar el futuro. |
| `costos_fuentes.py` | Apl | 072 | Costos oficiales: contrato de fuente, lectores del SICODI público y de los módulos estándar de transmisión, cruce por código, tensión, estructura y… |
| `metrados.py` | Apl | 072 | Metrados por código desde el modelo de la red, y su valoración con costos oficiales. |
| `formatos_pide.py` | Apl | 072 | Los formatos 01 a 15 de un estudio con cada hueco nombrado y su motivo. |
| `informes_planeamiento.py` | Ada | 072 | Los entregables de un estudio, un Word ligero por módulo, desde un mismo cálculo. |

### Motor: gobierno de modelos

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `model_registry.py` | Apl | 043, 060 | Candidatos inmutables, integridad, promoción atómica y reapertura en subproceso. |
| `training_coordinator.py` | Apl | 043 | Etapas reanudables, bloqueo GPU mediante guardia OS compartida y memoria física/comprometible antes de cargar pesos. |
| `trabajadores_ml.py` | Ada | 043 | Informes atómicos, dataset v2 verificado y herencia comprobada de la guardia GPU en procesos hijos. |
| `aprendizaje_continuo.py` | Apl | 050 | Ciclo común de aprendizaje: instantánea copiada y verificada, vistas por familia con particiones por observación, ciclo único sobre el coordinador,… |
| `evaluacion_modelos.py` | Apl | 044 | Política previa y validación de cuatro particiones por grupos. |
| `experimentos.py` | Apl | 043 | Contexto exacto y contratos inmutables de configuración, con SHA-256 canónico. |
| `upstream_ia.py` | Ada | 043 | Verifica origen, commit, licencia y árbol limpio de repositorios reutilizados. |

### Gemelo digital: `digital_twin/`

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `__init__.py` | Ada | 024 | Paquete del gemelo digital: episodios, búfer y captura, sin PowerFactory ni PyTorch. |
| `episode.py` | Ada | 024 | Contrato del episodio: clase y caso, fuente y proyecto, resultados del flujo (balance, pérdidas, cargabilidad, tensiones, confiabilidad, o el motivo… |
| `buffer.py` | Ada | 024 | Búfer local e inmutable de episodios: un JSON por huella, escritura atómica e idempotente, colisión detectada, índice SQLite reconstruible con… |
| `capture.py` | Ada | 024 | Ensamblaje del episodio desde el contexto firmado, el resultado del guion y la lectura tras reabrir. |
| `integration.py` | Ada | 024 | Captura tras cada acción nativa de la web: plan de lectura, norma de cada alimentador por su sistema y límites más estrictos, referencia del último… |
| `native_snapshot.py` | Ada | 024 | Identidad estable de un objeto de DIgSILENT, huella SHA-256 de un trazado e islas por tramos cerrados, sin suponer red radial. |
| `evaluacion.py` | Ada | 024 | Evaluación por caso: «Caso base» y «Sin proyecto» con las violaciones como diagnóstico (y el cuadre de la calibración), «Con proyecto» contra la… |
| `escenarios.py` | Ada | 024 | Matriz de escenarios (demanda escalada y N-1), familia topológica y partición fija, elección por incertidumbre o diversidad y presupuesto de licencia… |
| `auditoria.py` | Ada | 027 | Auditoría del dataset de cada modelo antes de entrenar: muestras, redes distintas, nodos, columnas, fracción etiquetada, rangos, no finitos (no se… |
| `curva.py` | Ada | 027 | Episodios del gemelo por sistema eléctrico frente a los 30/10/10 (reparto fijo por la huella de cada episodio) y curva de aprendizaje que dice si un… |
| `hiperparametros.py` | Ada | 027, 060 | Búsqueda de hiperparámetros del gemelo con Optuna (TPE y poda por mediana), con presupuesto de ensayos y tiempo, evaluada solo en validación. |
| `contratos_fisicos.py` | Ada | 045 | Versión y alcance del grafo del gemelo: qué física representa y por qué rechaza una red, y huellas de controles y caso. |
| `oraculo.py` | Ada | 024, 060 | Oráculo PINN/GNN (PyTorch, GPU si la hay): grafo por unidad, red de grafos sobre la física mallada con pérdida física de balance por barra eléctrica,… |
| `flujo.py` | Ada | 024 | Flujo de carga físico por matriz de admitancias dispersa, con lazos: acopladores fusionados en una barra, factorización LU una sola vez, punto fijo… |
| `motores_flujo.py` | Ada | 083 | Motores de flujo del oráculo sobre la misma red: Z-bus, Anderson, Newton, power-grid-model y OpenDSS. |
| `benchmark_fisico.py` | Ada | 045 | Ablaciones del gemelo sobre las mismas particiones (física pura, red sin término físico, híbrido y PowerFlowNet) y comprobación de dominio antes de… |
| `adaptador_pyg.py` | Ada | 045 | Adapta el MPN de PowerFlowNet a correcciones físicas de tensión y ángulo, mediante carga opcional. |
| `evolutivo.py` | Ada | 024, 044, 048 | Algoritmo genético, NSGA-II y evolución diferencial autoadaptativa (jDE), deterministas con su semilla. |
| `problema_optimizacion.py` | Ada | 048 | Contrato común de una búsqueda de obras y consignas: variables tipadas con unidad, origen y coste trazable, restricciones, objetivos, contexto y… |
| `adaptador_pymoo.py` | Ada | 048 | GA, NSGA-II y DE de pymoo, opcionales, como candidatos del benchmark de la 048: genes reparados por la regla común y presupuesto cortado por el… |
| `benchmark_optimizacion.py` | Ada | 048 | Benchmark de los optimizadores vigentes y los de pymoo: al menos veinte semillas comunes, presupuesto en evaluaciones reales (caché aparte),… |
| `adaptador_pnl.py` | Ada | 048 | Tramo continuo con Pyomo y un solucionador PNL (Ipopt por omisión, HiGHS para cuadráticos) con las discretas fijas: punto local continuo, nunca… |
| `temporal.py` | Ada | 024, 046, 060 | Gemelo temporal: GRU de las curvas de cabecera (estacional sin PyTorch), GRU multihorizonte para competir en el pronóstico, métricas, desviaciones… |
| `temporal_entrenamiento.py` | Ada | 043, 046, 060 | Lectura de series mediante lectores existentes, ajuste causal GRU, objetivos de cabecera y clientes, competición de pronósticos con ganador por… |
| `series_causales.py` | Ada | 046 | Cadencia, unidades, huecos, disponibilidad de covariables, particiones por día y ventanas causales. |
| `pronostico.py` | Ada | 046 | Contrato multihorizonte: objetivos, conjunto en rejilla común, referencias ingenuo y estacional semanal, calibración de intervalos y filas con la… |
| `evaluacion_temporal.py` | Ada | 046 | Política predeclarada, pinball y cobertura por horizonte, error de la máxima y de su instante y familias para las puertas. |
| `adaptador_neuralforecast.py` | Ada | 046 | N-HiTS, TFT y PatchTST de neuralforecast, opcionales y solo en CUDA, con la interfaz común. |

### Asistente: núcleo y operación

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `__init__.py` | Apl | 026 | Paquete del asistente de órdenes en lenguaje natural. |
| `tareas.py` | Apl | 026 | Catálogo de tareas: datos tipados, si escribe (confirmación), modo (consulta, trabajo, proceso), función de la web que lo hace y plantillas de frases. |
| `interprete.py` | Apl | 026 | Intérprete híbrido: Transformer, si duda Ollama, si duda pregunta. |
| `plan.py` | Apl | 026, 078 | Del texto interpretado al plan: datos contrastados con lo que existe (parecido, tomados del texto), lo que falta, dudas y razonamiento. |
| `planes_guardados.py` | Apl | 067 | Planes que escriben guardados por espacio con escritura atómica: sobreviven a un reinicio, sin confirmación y sin reanudarse. |
| `contratos_salida.py` | Apl | 047 | Esquema de órdenes y validación de tareas, campos, confianza y entidades del contexto. |
| `ejecutor.py` | Apl | 026 | Ejecuta el plan confirmado por las rutas y trabajos de la web, paso a paso, esperando cada trabajo. |
| `orquestador.py` | Apl | 027, 061 | El proyecto entero desde el espacio, etapa por etapa por las rutas de la web (fuente, sistema, «Caso base», cargas nuevas, obras, estudios, PIDE,… |
| `equipo.py` | Apl | 065 | Gobierno de herramientas y permisos sellados por plan, rol y fuente. |
| `revision_roles.py` | Apl | 065, 047 | Revisión local por roles sin autorización de escrituras nativas, y su comparación contra un revisor único. |
| `evidencias_web.py` | Apl | 067 | Custodia como evidencia del espacio el resultado de los informes y estudios que terminan bien, con su proyecto y su fuente verdaderos, para la… |
| `observacion.py` | Apl | 061 | Diario SQLite por espacio, contexto inmutable, informes custodiados y control de identidad de reanudación, sin promoción. |
| `vigilancia.py` | Apl | 026, 050 | Vigilancia de trabajos (fallos, tiempos, colas, reintento del 4002), modelos, calidad de resultados y suite nocturna con el RF de cada fallo. |
| `mejoras.py` | Apl | 026 | Mejoras en una rama aparte (git worktree) con spec y pruebas y su suite. |
| `internet.py` | Apl | 026 | Búsquedas en GitHub, PyPI y arXiv con el filtro de identificadores de la red y rutas. |
| `almacen.py` | Apl | 026 | Dónde guarda el asistente lo suyo, en la máquina: registros JSONL de solo añadir (órdenes, ejemplos, decisiones, avisos, internet, suite) y JSON… |
| `senales.py` | Apl | 027 | Recompensas y penalizaciones de cada orden, pares de preferencia para DPO, memoria de reflexiones y contexto de órdenes parecidas para Ollama. |

### Asistente: modelos de órdenes y documentos

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `transformer.py` | Apl | 026 | Transformer propio por caracteres: tarea y datos (etiquetas por carácter decididas por palabra), entrenamiento en GPU, prueba fija, registro,… |
| `codificador_ordenes.py` | Apl | 069, 075 | Intérprete de órdenes con codificador preentrenado congelado, cabezas de tarea y de datos, clase «ninguna» y el lugar en que el modelo la ve. |
| `afinado_ordenes.py` | Apl | 079 | Afinado de las últimas capas del codificador junto con las cabezas: lo congelado una vez, tasas diferenciadas, contrastiva, lotes por grupo, parada… |
| `validacion_cruzada.py` | Apl | 075 | Validación cruzada con las órdenes confirmadas: familias de frases casi iguales, reparto en 5 vueltas estratificado por tarea, cabezas por vuelta… |
| `datos_por_palabra.py` | Apl | 026, 069 | Etiquetas de los datos de una orden y su decisión por palabra, comunes a los dos modelos de órdenes. |
| `clasificador.py` | Apl | 026 | Clasificador de informes en dos niveles (estudio o factibilidad, y subtipo del perfil) sobre el mismo codificador. |
| `modelos_en_uso.py` | Apl | 067, 085 | Pone en uso lo que el registro aprobó con un único puntero atómico, conserva el anterior y vuelve a él con el registro de acuerdo. |
| `ollama.py` | Apl | 026 | Cliente del modelo local de Ollama: solo direcciones de la máquina, tareas como herramientas con respuesta JSON, respuestas con cita y embeddings. |

### Asistente: datos y entrenamiento

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `sinteticos.py` | Apl | 026 | Órdenes sintéticas por plantilla con los nombres reales del espacio y erratas solo en las palabras de la plantilla. |
| `ordenes_fijas.py` | Apl | 027 | Las 200 órdenes fijas del asistente escritas por el maestro (Claude), de todas las tareas y distintas de las plantillas, con su huella y su reparto… |
| `ordenes_maestro.py` | Apl | 085 | Órdenes que redacta el maestro en el estilo del operador: las valida, aparta por tarea un 25 % de sus familias para examen y dice qué conjunto decide… |
| `maestro_real.py` | Apl | 068 | Lee y valida las etiquetas de plata del maestro sobre textos reales, dice cuándo dos textos son la misma frase o familia y añade las erratas… |
| `curriculo_maestro.py` | Apl | 047, 068 | Familias sintéticas de órdenes escritas por el maestro de sesión, separadas antes del entrenamiento, y frases de estilo real solo de entrenamiento. |
| `curriculo_llm_real.py` | Apl | 047 | Solicitudes nuevas de prueba redactadas por el maestro. |
| `propuestas_maestro.py` | Apl | 047 | Corpus separado de 200 propuestas únicas, con anotaciones y procedencia del maestro. |
| `prueba_sellada.py` | Apl | 070 | La prueba sellada de las órdenes desde la 070: seis frases por tarea, un vocabulario propio y una huella fija. |
| `prueba_sellada_079.py` | Apl | 079 | La prueba sellada que decide desde la 079: seis frases por tarea escritas de una vez antes de medir, vocabulario inventado, huella fija y su método… |
| `aceptacion.py` | Apl | 047 | Auditoría, evaluación del intérprete/plan y puertas de aceptación por alcance. |
| `dataset_entrenamiento.py` | Apl | 043 | Custodia de datos reales, sintéticos y de contexto. |
| `calidad_datos.py` | Apl | 043 | Calidad y contaminación entre particiones sin inflar el conjunto humano. |
| `entrenamiento_dataset.py` | Apl | 043 | Ajuste de clasificadores pequeños sobre particiones v2 explícitas. |
| `destilacion.py` | Apl | 027 | Destilación del modelo local de Ollama (maestro) al Transformer de órdenes: k votos con temperatura por orden sin etiqueta, filtro por acuerdo y… |
| `destilacion_integral.py` | Apl | 047 | Comparación supervisado/destilado, calibración, prueba sellada, recarga y registro del alumno. |
| `ajuste_condicionado.py` | Apl | 047 | Puertas de 027:RF-18 sobre órdenes reales independientes y decisión de ajustar el LLM, sin entrenar ni activar. |
| `llm_destilacion.py` | Apl | 047, 060 | Custodia de referencia, corpus del LLM con entidades reales y objetivos causales de respuesta. |
| `llm_checkpoint.py` | Apl | 002 | Comprobaciones de un checkpoint, comunes a entrenar y publicar. |
| `llm_runtime.py` | Apl | 047 | Verifica checkpoints y publica exportación, GGUF e importación local secuencial con hashes y readback. |
| `custodia_corpus.py` | Apl | 047, 065 | Resolución explícita y verificable de fuentes custodiadas tras su traslado, sin alterar ejemplos ni particiones. |
| `reubicacion_corpus.py` | Apl | 047, 065 | Nueva custodia externa del corpus LLM con cuotas, hashes, preflight y conservación del original. |
| `corpus_redaccion.py` | Apl | 072 | Corpus de redacción del PIDE: solo lo que una persona revisó y aprobó para redactar o dar formato, sin cifras ni códigos de otra red, en un registro… |

### Asistente: conocimiento y RAG

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `indice.py` | Apl | 026, 047 | Índice local del proyecto (CODIGO_FUENTE, RF de las specs, docstrings, manual, constitución), BM25 y vectores fusionados por posición, cálculo de… |
| `embeddings.py` | Apl | 043, 047 | Pares contrastivos, métricas de recuperación, encoder CUDA local y persistencia de índices con hashes. |
| `reranker.py` | Apl | 047 | Reranker por cross-encoder en CUDA, con revisión fijada, la política que lee la decisión de la evaluación sellada y los umbrales de abstención… |
| `evaluacion_rag.py` | Apl | 047 | Conjunto sintético sellado, medición de BM25, híbrido y rerankers, decisión según la política declarada, calibración de la abstención y su puerta en… |
| `corpus_proyecto.py` | Apl | 077 | Corpus ampliado del índice: ficheros, troceado sin perder líneas, caché por fichero y medida de tamaño. |
| `lectura_proyecto.py` | Apl | 077 | Lecturas del proyecto para el LLM y el MCP: leer un fichero, buscar un texto literal y consultar una ruta en el OpenAPI, con política local o… |
| `ejemplos_pide.py` | Apl | 027 | Ejemplos del agente desde el corpus PIDE entregado: por artículo sus evidencias en cada PIDE (por la ruta y el texto), por formato F01 a F15 sus… |

### Web: `web/`

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `__init__.py` | Pre | 001 | Paquete de la interfaz web. |
| `__main__.py` | Pre | 001 | Arranca la web: `python -m convertersmartgrid.web` o `convertersmartgrid-web`. |
| `app.py` | Pre | 001, 004, 008, 011, 104, 017, 103, 021, 022, 025, 035, 039, 042, 061, 091 | Rutas FastAPI sobre el motor.; conversión por sistema eléctrico (`/convert/sistema`, `/estructura`) y la tabla de la estructura |
| `api_contract.py` | Pre | 065, 002 | Modelos públicos Pydantic y contratos OpenAPI del frontend. |
| `services.py` | Pre | 001, 004, 008, 092, 011, 121, 017, 104, 020, 021, 022, 025, 018, 030, 032, 035, 037, 038, 039, 041, 042, 060, 061, 091 | Las acciones de la interfaz, sin interfaz. |
| `requisitos.py` | Pre | 002 | Lo que un servicio exige antes de trabajar y el error del operador. |
| `jobs.py` | Pre | 001, 011, 061, 086 | Trabajos largos en cola, con progreso, cancelación y límite de tiempo por guion (P7). |
| `operaciones_lentas.py` | Pre | 065 | ZIP cancelable, cuotas y entrega de archivos por trabajo. |
| `workspace.py` | Pre | 001, 011, 025, 018, 035, 038, 065, 086 | Espacio de trabajo: entradas, opciones, salida de una sesión y obras de mejora sin aplicar. |
| `source_runs.py` | Pre | 001 | Custodia inmutable de los ficheros de cada ejecución. |
| `source_scope.py` | Pre | 001, 059 | Empresa y periodo de los paquetes VNR-GIS. |
| `readiness.py` | Pre | 001, 053 | Puertas por alimentador antes de producir DGS. |
| `reconstruction_service.py` | Pre | 001 | Diagnóstico y reconstrucción como trabajos de la web. |
| `asistente_operacion.py` | Pre | 070 | Lo que cada tarea del asistente necesita del espacio, comprobado antes de ofrecer confirmar: calibración, libros, costeo, formulario y las formas que… |
| `asistente_consultas.py` | Pre | 070 | Las consultas del asistente sin escribir ni abrir DIgSILENT: qué dato se pide, su fuente, «no lo encuentro» y por qué un estudio no está disponible. |
| `equipo_api.py` | Pre | 065 | API del equipo LLM: permisos por plan y revisiones locales en cola. |
| `seguridad.py` | Pre | 086 | La puerta de la web, en un middleware ASGI: Host, Origin, token de la sesión (también en el WebSocket) y política de contenido. |
| `runtime.py` | Pre | 001, 036, 065 | Comprobación del entorno que hace el lanzador de Windows y huella del código. |
| `doctor.py` | Pre | 086, 091 | Qué le falta a la instalación, qué función afecta y cómo arreglarlo, para la orden y la pantalla. |
| `soporte.py` | Pre | 086 | Paquete de soporte con una lista cerrada, sin datos del cliente: registros anonimizados y forma del perfil. |
| `copia_datos.py` | Pre | 086 | Copia y restauración de los datos con manifiesto, según la regla de la retención, y aviso de copia vieja. |
| `retencion.py` | Pre | 062, 065 | Revisión diaria de ejecuciones y temporales sin referencias, de más de siete días, con protección de datos y resumen persistido. |
| `suspension.py` | Pre | 096 | Tiempo suspendido del equipo y petición a Windows de no suspender mientras corre un trabajo. |
| `cierre.py` | Pre | 081 | Registro de cada arranque y cierre de la web, con su motivo. |
| `sources/__init__.py` | Pre | 002 | Reexportación temporal de `convertersmartgrid.sources`. |
| `sources/vnr.py` | Pre | 002 | Reexportación temporal de `convertersmartgrid.sources.vnr`. |

### VNR-GIS: `adaptadores/entrada/vnr/`

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `__init__.py` | Ada | 001 | Paquete del módulo VNR-GIS. |
| `__main__.py` | Pre | 001 | `python -m vnr_etl`. |
| `cli.py` | Pre | 001 | Orden `vnr-etl`. |
| `config.py` | Ada | 001 | Configuración del ETL. |
| `doctor.py` | Ada | 001 | Dependencias y capacidades (`vnr-etl doctor`). |
| `logging.py` | Ada | 001 | Registro estructurado de eventos. |
| `pipeline.py` | Ada | 001 | Capa de aplicación compartida por el CLI y la web. |
| `application/__init__.py` | Ada | 001 | Servicios compartidos por el CLI y la API. |
| `application/cymdist_bridge.py` | Ada | 001 | Del modelo canónico VNR al contrato del motor. |
| `application/reconstruccion.py` | Ada | 001 | Reconstruye el modelo canónico antes del motor. |
| `application/services.py` | Ada | 001 | Validación y exportación VNR en un solo sitio. |
| `audit/__init__.py` | Ada | 001 | Auditoría de solo lectura. |
| `audit/project.py` | Ada | 001 | Auditoría del proyecto anfitrión. |
| `catalogs/__init__.py` | Ada | 001 | Catálogos aprobados de conductores y equipos. |
| `catalogs/conductor.py` | Ada | 001 | Mapeo del catálogo de conductores. |
| `connectors/__init__.py` | Ada | 001 | Conectores de fuente. |
| `connectors/base.py` | Ada | 001 | Contrato de los conectores. |
| `connectors/registry.py` | Ada | 001 | Registro de adaptadores de fuente. |
| `connectors/arcgis.py` | Ada | 001 | Conector ArcGIS REST. |
| `connectors/databases.py` | Ada | 001 | Bases de datos y volcados SQL. |
| `connectors/delimited.py` | Ada | 001 | Texto delimitado (CSV/TXT) con codificación y separador deducidos. |
| `connectors/vector.py` | Ada | 001 | GeoJSON, Shapefile y GeoPackage. |
| `connectors/sqlserver_vnr.py` | Ada | 023, 054 | Copia de SQL Server (`.bak`) de VNR-GIS de cualquier concesionaria: restaura con su huella, lee las tablas por sus campos y arma el modelo canónico… |
| `discovery/__init__.py` | Ada | 001 | Descubrimiento, huella, catálogo y descarga de fuentes. |
| `discovery/catalog.py` | Ada | 001 | Catálogo de publicaciones y empresas. |
| `discovery/download.py` | Ada | 001, 065 | Descargas y manejo seguro de archivos. |
| `discovery/fingerprint.py` | Ada | 001 | Huella de fuente y de esquema. |
| `discovery/freshness.py` | Ada | 001 | La publicación más nueva por fecha autoritativa. |
| `discovery/official.py` | Ada | 001 | Publicaciones oficiales de OSINERGMIN. |
| `discovery/schema.py` | Ada | 001 | Descubrimiento semántico del esquema. |
| `electrical/__init__.py` | Ada | 001 | Enriquecimiento eléctrico. |
| `electrical/enrich.py` | Ada | 001 | Completa los datos eléctricos del modelo. |
| `exporters/__init__.py` | Ada | 001 | Exportadores de simulador. |
| `exporters/base.py` | Ada | 001 | Contrato del exportador y perfil de destino. |
| `exporters/cymdist.py` | Ada | 001 | Exportador CYMDIST. |
| `exporters/dgs.py` | Ada | 001 | Exportador DIgSILENT: delega en el motor. |
| `gis/__init__.py` | Ada | 001 | CRS, snapping y reconstrucción de nodos. |
| `gis/crs.py` | Ada | 001 | CRS de las capas y su deducción. |
| `gis/geometry.py` | Ada | 001 | Geometría auxiliar, sin `shapely`. |
| `gis/snapping.py` | Ada | 001 | Snapping y reconstrucción de nodos. |
| `models/__init__.py` | Ada | 001 | Modelo canónico VNR-GIS. |
| `models/canonical.py` | Ada | 001 | Clases del modelo canónico. |
| `reconciliation/__init__.py` | Ada | 001 | Reconciliación y comparación de periodos. |
| `reconciliation/diff.py` | Ada | 001 | Comparación incremental por ID estable. |
| `topology/__init__.py` | Ada | 001 | Topología y validación del grafo. |
| `topology/graph.py` | Ada | 001 | Validación de topología con NetworkX. |
| `validation/__init__.py` | Ada | 001 | Puertas de validación A–H. |
| `validation/gates.py` | Ada | 001 | Las puertas A–H. |
| `web/__init__.py` | Pre | 001 | Rutas web VNR-GIS, montadas en la API principal. |
| `web/app.py` | Pre | 001 | `APIRouter` bajo `/api/vnr`. |

### Guiones de DIgSILENT: `tools/` (corren con su intérprete)

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `powerfactory_acceptance.py` | — | 034, 010, 015, 054, 078 | Puerta de aceptación: importa un DGS en PowerFactory, o adopta un proyecto existente, y verifica su «Caso base» frente al archivo original. |
| `casos_pf.py` | — | 011, 014, 015, 016, 025, 037, 073 | Guion de DIgSILENT: los casos «Caso base», «Sin proyecto» y «Con proyecto», cada uno con su escenario y sus variaciones. |
| `ajuste_cabecera_pf.py` | — | 006, 008, 011, 014, 015, 020, 021, 022, 025, 032, 035, 039, 041, 094, 095, 091 | Guion de DIgSILENT: ajusta un alimentador a su máxima de cabecera, en el escenario de «Sin proyecto». |
| `cargas_pf.py` | — | 004, 007, 008, 011, 016, 022, 035, 040, 054, 099 | Guion de DIgSILENT: demandas y cargas nuevas en un proyecto existente. |
| `obras_pf.py` | — | 011, 103, 016, 042, 048, 073, 098 | Guion de DIgSILENT de las obras de mejora: con `--bibliotecas`, alimentadores y tipos de las tres bibliotecas. |
| `estudios_pf.py` | — | 011, 017, 130, 131, 135, 012, 037 | Guion de DIgSILENT: un estudio en un caso, sin escalado por alimentador y sin aplicar lo que proponen los optimizadores. |
| `capacidad_pf.py` | — | 012 | Guion de DIgSILENT de la capacidad de alojamiento nodo a nodo y conjunta (`ComHostcap`), las curvas PV por alimentador con o sin contingencias… |
| `confiabilidad_pf.py` | — | 012 | Guion de DIgSILENT: con `--aplicar-datos`, el libro de la empresa en la variación «Datos de confiabilidad» (modelos `Sto*` por clase y tipo, equipos… |
| `protecciones_pf.py` | — | 049 | Guion de DIgSILENT de las protecciones: con `--capacidades`, el inventario de la versión conectada (órdenes `ComShc`, `ComShctrace` y… |
| `transferencia_pf.py` | — | 011, 104, 129, 016 | Guion de DIgSILENT: transferencia de carga entre dos alimentadores por su enlace, paso a paso en los dos sentidos, con la capacidad y el margen del… |
| `transformador_set_pf.py` | — | 017 | Guion de DIgSILENT: cargabilidad del devanado de la SET en el proyecto de transmisión, sin proyecto (el caso tal cual) y con proyecto (la carga de la… |
| `set_nueva_operacion_pf.py` | — | 063 | Diagnóstico físico de conexiones y tipos de una SET existente. |
| `pide_pf.py` | — | 024, 029, 030 | Guion de DIgSILENT: cada año del horizonte del PIDE con la demanda escalada por el `ComLdf`, diagnóstico de la norma con el alimentador y la tensión… |
| `escenarios_pf.py` | — | 024 | Guion de DIgSILENT: escenarios del gemelo en una copia del proyecto (desactivado antes de copiar), demanda escalada y tramos abiertos, resultados y… |
| `digital_twin_snapshot_pf.py` | — | 024, 098 | Guion de DIgSILENT de solo lectura: reabre el proyecto, activa el caso, ejecuta el flujo y devuelve tensiones, cargabilidad, cabeceras, pérdidas,… |
| `escanear_alimentador_pf.py` | — | 028, 098 | Escaneo de solo lectura de alimentadores en DIgSILENT: generadores con su barra, bancos, variaciones y cargas cambiadas a mano. |
| `transferencia_operador_pf.py` | — | 098 | Transferencias de carga del operador en DIgSILENT: leerlas, desactivarlas mientras se calibra con registro en disco y restituirlas con su evidencia. |
| `verificar_pf.py` | — | 008 | Guion de DIgSILENT: convergencia del proyecto con lo activo. |
| `hojas_diagrama_pf.py` | — | 022 | Hoja de cada diagrama de un proyecto de DIgSILENT frente a sus gráficos y conectores, de solo lectura. |
| `pf_proyectos.py` | — | 005 | Proyectos de la carpeta de importación de DIgSILENT y sus alimentadores. |
| `show_pf_diagram.py` | — | 005 | Abre en DIgSILENT el diagrama de un alimentador. |
| `check_pf_license.py` | — | 005, 011, 012 | Qué módulos de PowerFactory permite la licencia. |
| `run_one_study.py` | — | 005 | Trabajador de PowerFactory: importa y mide, o ejecuta un estudio. |
| `base_scenario.py` | — | 005 | Escenario base (año 0): lo construye, lo hace converger y lo diagnostica. |
| `build_system_grid.py` | — | 034 | Todos los alimentadores en una sola red, importada en PowerFactory. |
| `convertir_grupos_mdb.py` | — | 034, 021 | Varios alimentadores de una base en un DGS, importado y con flujo, a escala real por defecto. |
| `prueba_representacion.py` | — | 034 | Red, cargas y SED del TXT en una hoja de PowerFactory. |
| `run_powerfactory_gate.bat` | — | 034 | Lanza `powerfactory_acceptance.py` con el intérprete de PowerFactory. |
| `pf_servidor.py` | — | 019, 064 | Proceso que mantiene DIgSILENT abierto y atiende las órdenes de los guiones. |
| `pf_cliente.py` | — | 019, 091 | Envía un guion de DIgSILENT al proceso que se queda abierto y reescribe su salida. |
| `restitucion_pf.py` | — | 064 | Órdenes de aceptación de la restitución del servidor: copiar, alterar y fallar, leer y borrar una copia `PRUEBA064_*`. |
| `aceptar_restitucion_pf.py` | — | 064 | Aceptación nativa de la restitución por el camino de la web y el servidor, con evidencia en JSON. |
| `estadistica_ordenes.py` | — | 081 | Resumen de las órdenes de DIgSILENT por guion y día, contraste de hipótesis entre dos versiones y fallos repetidos. |

### Herramientas: operación, datos y aceptación

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `sistema_web.py` | — | 022, 025, 039 | Un sistema eléctrico de punta a punta por la web: espera lo que corre, convierte por sistema, importa en DIgSILENT, busca la máxima por barra de SET… |
| `informe_web.py` | — | 017, 105 | Un informe de la spec 017 desde la línea de órdenes: lee el `.plan.json` que la web guardó junto al Word (o un formulario con `--tipo`), lo envía a… |
| `informe_casos_guardados.py` | — | 063 | Reproduce la evaluación Word con tres casos y sus seis flujos guardados por la web. |
| `accept_three_sources.py` | — | 001, 004, 006, 011 | Aceptación universal y separada de MDB, TXT y VNR-GIS hasta ajuste, relectura y estudio nativos. |
| `accept_digital_twin_in111_ta225.py` | — | 024 | Aceptación nativa del caso dorado del gemelo digital: dos lecturas en procesos nuevos, hechos del JSON `--esperado`, comprobaciones y episodio en el… |
| `aceptacion_nativa.py` | — | 044, 045, 048, 049 | Evidencia nativa de las T4: obra aplicada por la web, relecturas en procesos nuevos de `digital_twin_snapshot_pf.py`, retiro, capacidades de… |
| `aceptar_dominio.py` | — | 065 | Preaceptación de fuente, vínculo, caso, evidencia y recursos sin conectar ni modificar el motor nativo. |
| `apply_catalog_to_model.py` | — | 034, 032 | Corrige las características eléctricas del modelo con el catálogo de fichas. |
| `build_input_catalog.py` | — | 034 | Tabla de parámetros eléctricos en `input/` y auditoría de alimentadores. |
| `suggest_line_type_aliases.py` | — | 034 | Propone alias para tipos de línea sin ficha en el catálogo. |
| `compare_schema.py` | — | 034 | Cabeceras de un DGS externo frente a un perfil de esquema. |
| `fidelidad_seleccion.py` | — | 009 | Comprueba que una selección pasa entera del TXT al DGS. |
| `linea_base_dgs.py` | — | 001, 002 | Línea base de DGS para comprobar que una reorganización no cambia nada. |
| `validar_totalidad_vnr.py` | — | 080 | Cruza con consultas propias a la base restaurada las salidas, tramos y SED de una copia VNR-GIS con lo que lista la web. |
| `cabecera_ancha.py` | — | 051 | Herramienta de la spec 051: pasa la medición de cabecera a lo ancho o las máximas mensuales al formato de la calibración, con… |
| `proyeccion_mercado.py` | — | 072 | Compara métodos de proyección anual contra lo ocurrido con el Formato 01. |
| `costos_cruce.py` | — | 072 | Mide cuánto de una red convertida encuentra costo en el SICODI público, y nombra lo que no. |
| `construir_dataset_pide.py` | — | 024 | Construye el corpus PIDE universal de una empresa con `pide_dataset`. |
| `corpus_redaccion_pide.py` | — | 072 | Revisión humana del corpus PIDE para redactar: lista lo pendiente, registra decisiones con su revisor y exporta lo aprobado sin cifras. |
| `copia_datos.py` | — | 086 | Órdenes de copia, verificación, restauración, estado de la copia e identidad de la instalación. |

### Herramientas: modelos, asistente y MADRL

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `digital_twin_entrenar.py` | — | 024, 043 | Entrena el oráculo PINN/GNN en su propio proceso (la web lo lanza): reentreno si toca o forzado, promoción por puertas, respaldo en CPU si la GPU… |
| `digital_twin_temporal_entrenar.py` | — | 043, 046, 060 | Trabajador de entrenamiento y recarga GRU, inventario de la medición y competición de pronósticos de cabecera o clientes fijos. |
| `digital_twin_auditar.py` | — | 027 | Informe de la auditoría del dataset del gemelo y del asistente, sin GPU ni DIgSILENT. |
| `digital_twin_buffer.py` | — | 024 | Búfer de episodios desde la consola: listar, mostrar, validar, registrar y rehacer el índice, sin DIgSILENT. |
| `asistente_entrenar.py` | — | 026 | Entrena el Transformer de órdenes y el clasificador de informes en su propio proceso, en la GPU. |
| `asistente_medir_ollama.py` | — | 026 | Mide los modelos locales de Ollama con las mismas órdenes (acierto, segundos, sin respuesta) y guarda el elegido para la web. |
| `asistente_modelo_provisional.py` | — | 085 | Ve, pone y retira un modelo en uso provisional por decisión del usuario, sin aprobarlo ni bajar las puertas. |
| `asistente_embeddings.py` | — | 043, 047 | Ajuste solo con train y evaluación sobre consultas reservadas del recuperador local. |
| `asistente_indice_ampliado.py` | — | 077 | Sin GPU: tamaño de los dos corpus, BM25 con el reparto `corpus` de la 076 y formación de los conjuntos nuevos. |
| `asistente_evaluar_rag.py` | — | 047 | Medición real de la recuperación en la GPU, comprobación del conjunto sin ella con `--solo-conjunto`, calibración de la abstención y su medición… |
| `asistente_qlora.py` | — | 043, 047 | Adaptador del coordinador al ajuste generativo NF4 existente y su corpus sellado. |
| `asistente_destilar.py` | — | 047 | Prepara el currículo, entrena con exclusión GPU y verifica el alumno en proceso nuevo. |
| `asistente_observar.py` | — | 061 | Incorpora y verifica informes locales del aprendizaje sin activar modelos. |
| `asistente_ordenes_reales.py` | — | 068 | Reúne las órdenes reales de las sesiones y del almacén, crea el libro de revisión e importa solo lo que el operador marque. |
| `asistente_comparar_revision.py` | — | 047 | Rol único frente a cuatro roles con los mismos casos declarados: errores, coste y latencia. |
| `preguntas_entregables.py` | — | 076 | Preguntas de metodología y criterios por entregable: verifica fuentes, cifras y nombres, reparte en corpus y sellado, exporta e importa la hoja de… |
| `llm_destilar.py` | — | 047, 060 | Prepara el corpus del alumno LLM a partir de fuentes verificadas de este proyecto. |
| `aceptar_agente.py` | — | 047 | Materializa propuestas, selecciona configuración local y evalúa las 200 sin ejecutar acciones nativas. |
| `construir_dataset_entrenamiento.py` | — | 043 | Construye el dataset de entrenamiento en una carpeta nueva y dice si está completo con los umbrales de la spec 027. |
| `reentrenar_modelos.py` | — | 043, 060 | CLI de coordinación, validación de configuración y rechazo de resultados incompletos. |
| `aprendizaje_continuo.py` | — | 050 | Congela la instantánea, ejecuta el ciclo único con las etapas de `reentrenar_modelos` sobre las copias, muestra sus fases, lo cancela y vuelve al… |
| `evaluar_evolutivos.py` | — | 043, 048 | Benchmark analítico calculado de GA, NSGA-II y DE (y los de pymoo si está) con al menos 30 semillas, el mismo presupuesto de evaluaciones reales y la… |
| `reubicar_corpus_llm.py` | — | 047, 065 | Valida o publica una nueva versión custodiada del corpus tras un traslado exacto de datos. |
| `preparar_modelos_ia.py` | — | 043 | Descarga explícita y auditoría de pesos fijados, sin activación. |
| `preparar_upstream_ia.py` | — | 043 | Prepara o verifica clones fijados sin instalar ni ejecutar sus programas. |
| `madrl_entrenar.py` | — | 074 | Entrena el control MaskablePPO del piloto y lo compara con sus referencias. |
| `madrl_obras.py` | — | 074 | Mide la escalera y NSGA-II y la fidelidad del entorno sobre una red del búfer de episodios. |
| `mcp_conversor.py` | — | 077 | Servidor MCP local, solo stdio y solo lectura, con las tres lecturas del asistente. |

### Herramientas: calidad y entrega

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `arquitectura.py` | — | 065, 002 | Guarda AST de capas, ciclos y accesos privados con deuda explícita. |
| `generar_contrato_api.py` | — | 065, 002 | Generación y comprobación determinista del contrato OpenAPI a TypeScript. |
| `estado_specs.py` | — | 033 | Estado de las specs: lee numeración, tareas, estado y citas de las pruebas, y escribe `specs/README.md`. |
| `suite_por_tandas.py` | — | 081 | La suite nocturna en un proceso separado de la web, por tandas. |
| `trazabilidad_candidato.py` | — | 065 | Matriz de requisitos, código, pruebas y ejecuciones vinculadas al candidato. |
| `verificar_candidato.py` | — | 065 | Regresión de un candidato con hashes antes/después, JUnit y matriz de trazabilidad. |
| `fijar_entorno.py` | — | 065 | Cierre reproducible de dependencias para CPython 3.12/Windows. |
| `comprobar_entrega.py` | — | 086 | Comprueba lo que se entregaría según `config/entrega.json`: términos prohibidos (perfiles excluidos, huellas con sal y lista local fuera de git),… |
| `construir_candidato.py` | — | 086 | Arma el candidato: rueda con lo de `config/entrega.json` y comentarios neutralizados, lock con huellas, Python embebido, documentos, SBOM y… |
| `instalar_candidato.py` | — | 086 | Instala, actualiza y vuelve atrás desde un candidato: huellas, sin red, puntero de versión y copia previa de los datos. |
| `build_interactive_architecture.py` | — | 009 | Página distribuible de la arquitectura C4 interactiva desde su fuente en `docs/architecture/`. |
| `verify_architecture_links.py` | — | 009 | Comprueba los enlaces públicos y locales del espacio Structurizr de la arquitectura. |
| `verify_interactive_architecture.mjs` | — | 009 | Comprobación en navegador de la página de la arquitectura C4 interactiva (Node.js). |
| `generar_arquitectura.py` | — | 090 | Genera `docs/ARQUITECTURA_CATALOGO.md` desde el repositorio: ficheros, capas, rutas, tareas del asistente y roles de su equipo. |

### Interfaz: `frontend/src/` y su compilación

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `src/api/esquema.ts` | — | 065, 002 | Tipos generados desde OpenAPI. |
| `scripts/build.mjs` | — | 065 | Compila fuera del checkout y publica `dist` completo, conservando el anterior ante cualquier fallo. |
| `scripts/runtime-paths.mjs` | — | 065 | Raíces externas de la compilación, en el volumen de `dist` y fuera del código. |
| `test/reconexion.test.mjs` | — | 086 | Pruebas de los trabajos al reconectar y de la edición en la web. |
| `scripts/README.md` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/buildPreservado.test.mjs` | — | 065 | Pruebas de la compilación y sus rutas, con y sin espacios. |
| `test/clientesCatalogo.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/equipoAsistente.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/aprendizaje.test.mjs` | — | 050 | Contrato de consulta sin trabajos y representación de fases, rechazo, versiones y errores de lectura. |
| `test/operacionSet.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/projectBinding.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `test/solicitudLeida.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |

### Sin subsistema asignado

Ficheros nuevos: asígnelos en `docs/architecture/subsistemas.json`.

| Fichero | Capa | Specs | Papel |
| --- | --- | --- | --- |
| `frontend/scripts/fronteras.mjs` | — | 002 | Regla AST y resolución TypeScript de fronteras. |
| `frontend/src/api/asistenteAceptacion.ts` | — | 047 | Contrato web de propuestas, observaciones humanas y aceptación del agente. |
| `frontend/src/api/client.ts` | — | 001, 011, 021, 022, 025, 039, 061 | Cliente tipado de la API.; conversión por sistema eléctrico y máxima por barra |
| `frontend/src/api/reconexion.ts` | — | 086 | Pone al día los trabajos de la pestaña al volver a conectar, y lista los interrumpidos por ver. |
| `frontend/src/api/types.ts` | — | 001, 011, 021, 025, 037, 039, 041, 061 | Tipos de las respuestas de la API. |
| `frontend/src/app/AcercaDe.tsx` | — | 086 | La versión de la cabecera abre sus notas y el diagnóstico de la instalación. |
| `frontend/src/app/App.tsx` | — | 001, 008, 061, 091 | Marco de la página: paneles, pestañas, resúmenes de trabajos. |
| `frontend/src/app/AvisosDatos.tsx` | — | 086 | Avisos de los datos: copia vieja, espacio dañado con su botón de restaurar, ficheros no disponibles y trabajos interrumpidos con su registro. |
| `frontend/src/app/JobBar.tsx` | — | 001 | Barra de trabajos en curso. |
| `frontend/src/app/LogPanel.tsx` | — | 001 | Registro. |
| `frontend/src/app/main.tsx` | — | 001 | Arranque de React. |
| `frontend/src/features/asistente/Aprendizaje.tsx` | — | 050 | Consulta de las siete fases del ciclo común, versiones y bloqueos. |
| `frontend/src/features/asistente/Asistente.tsx` | — | 026, 043, 061 | Pestaña «Asistente»: consola de órdenes, plan con datos, pasos, lo que falta, dudas y razonamiento, confirmar y ejecutar, corregir la tarea,… |
| `frontend/src/features/asistente/EquipoAsistente.tsx` | — | 065 | Roles, permisos y revisión de propuestas en la consola del asistente. |
| `frontend/src/features/asistente/MonitorAgente.tsx` | — | 061, 062 | Monitor del asistente conectado al contexto WebSocket, etapas, operaciones, evidencia real y retención diaria. |
| `frontend/src/features/asistente/estadoEquipoAsistente.ts` | — | 065 | Cliente tipado de permisos, acciones y revisiones del equipo. |
| `frontend/src/features/conversion/DescargaZip.tsx` | — | 065 | Descarga ZIP preparada como trabajo con progreso y cancelación. |
| `frontend/src/features/conversion/FeedersPanel.tsx` | — | 001, 022, 091 | Tabla de alimentadores y conversión.; conversión por sistema eléctrico con su zonal, aparte de unir, y el tipo de cada DGS unido |
| `frontend/src/features/conversion/InputsPanel.tsx` | — | 001 | Entrada de datos: TXT, MDB y VNR-GIS. |
| `frontend/src/features/conversion/Modules.tsx` | — | 001 | Pestañas de resultados, catálogo y sistema completo. |
| `frontend/src/features/conversion/OptionsPanel.tsx` | — | 001 | Opciones de conversión. |
| `frontend/src/features/conversion/ReconstructionPanel.tsx` | — | 001 | Diagnóstico y reconstrucción. |
| `frontend/src/features/powerfactory/AjusteCabecera.tsx` | — | 006, 008, 020, 021, 025, 035, 039, 041, 091 | Paso 2.4: ajuste a la máxima de uno o varios alimentadores. |
| `frontend/src/features/powerfactory/CargasTab.tsx` | — | 004, 005, 008, 011, 016, 042, 091 | Pestaña «Cargas en DIgSILENT» en cuatro pasos. |
| `frontend/src/features/powerfactory/CurvaCabecera.tsx` | — | 006, 021 | Paso 2.4: curva del registro del medidor de cabecera, con el mes de la máxima sombreado y zoom por tramo. |
| `frontend/src/features/powerfactory/DatosEmpresaPF.tsx` | — | 012 | Paso 4.2: libro de la empresa del proyecto (subir, plantilla, lo que trae, aplicar en DIgSILENT). |
| `frontend/src/features/powerfactory/DemandaMedida.tsx` | — | 004, 008, 013, 021, 022, 025, 035, 038, 039, 091 | Paso 2: libros de medición, máxima de cabecera (con la central térmica de un alimentador, en el mes de análisis o en un instante coincidente) y… |
| `frontend/src/features/powerfactory/EstudiosPF.tsx` | — | 011, 012, 037, 049, 091 | Paso 4.2: estudios sobre la red calibrada, límites y resultados. |
| `frontend/src/features/powerfactory/GemeloPIDE.tsx` | — | 024 | Paso 5 de «Cargas en DIgSILENT»: planificar con el PIDE (CAPEX opcional, aplicar solas las obras que funcionan), tabla de obras con prioridad, estado… |
| `frontend/src/features/powerfactory/GuionesPF.tsx` | — | 011 | Paso 4.2: guiones DPL y Python del operador, sus parámetros y su salida por caso. |
| `frontend/src/features/powerfactory/InformesPF.tsx` | — | 017, 100, 102, 104, 125 | Paso 4.4: informe de estudio eléctrico y de factibilidad y punto de diseño con lo ya guardado por la web (flujos de 4.2, obras, cargas nuevas… |
| `frontend/src/features/powerfactory/ObrasPF.tsx` | — | 011, 016 | Paso 4.1: formulario de obras de mejora (también enlace, migración desde un nodo y sección de toda la troncal), bibliotecas de tipos, obras… |
| `frontend/src/features/powerfactory/OperacionSet.tsx` | — | 063 | Panel para diagnosticar, evaluar o reforzar una SET existente, sin recrearla. |
| `frontend/src/features/powerfactory/PerfilTension.tsx` | — | 094 | Perfil de tensión que deja la calibración: barras de media por su distancia a la cabecera, la troncal y el límite del perfil de la empresa. |
| `frontend/src/features/powerfactory/TransferenciaPF.tsx` | — | 011, 104, 123 | Paso 4.3: transferencia de carga entre dos alimentadores. |
| `frontend/src/features/powerfactory/alternativas.ts` | — | 042 | Las palabras y el orden de las alternativas por alimentador, las mismas del informe |
| `frontend/src/features/powerfactory/clientesCatalogo.ts` | — | 004, 008, 025, 091 | Estado del catálogo mensual de clientes: un solo libro activo e índice vigente antes de cruzar. |
| `frontend/src/features/powerfactory/formularioOperacionSet.ts` | — | 063 | Valida el formulario de la operación de una SET y arma el cuerpo de la orden. |
| `frontend/src/features/powerfactory/solicitudLeida.ts` | — | 063 | Acumula por documento lo leído de los PDF del solicitante y detecta un alimentador distinto del de la carga. |
| `frontend/src/shared/MarcaBeta.tsx` | — | 086 | La marca y el aviso de una función en beta. |
| `frontend/src/shared/PfWarning.tsx` | — | 002, 008 | Aviso de disponibilidad de PowerFactory común a conversión y operación. |
| `frontend/src/shared/SinPantallaEnBlanco.tsx` | — | 042 | Si una pantalla falla al dibujarse, lo dice y deja recargar |
| `frontend/src/shared/context.tsx` | — | 001 | Contexto común de la aplicación. |
| `frontend/src/shared/edicion.ts` | — | 086 | Pregunta a `/api/health` qué edición corre y qué funciones están en beta. |
| `frontend/src/shared/formato.ts` | — | 002, 001 | Formateadores numéricos y tamaños compartidos, extraídos sin cambiar su cuerpo. |
| `frontend/src/shared/projectBinding.ts` | — | 005, 018, 034 | Vínculo del proyecto de DIgSILENT con su ejecución de origen: separa los bloqueos de las advertencias por cambios manuales. |
| `frontend/src/shared/styles.css` | — | 001, 021 | Tokens y estilos, modo claro y oscuro. |
| `frontend/src/shared/ui.tsx` | — | 001 | Piezas comunes: modal, avisos, casillas, ficheros. |
| `frontend/src/shared/useWorkspace.ts` | — | 001, 059 | Espacio de trabajo, Registro en vivo y trabajos por WebSocket. |
| `frontend/test/alternativas.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `frontend/test/fronteras.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `frontend/test/pideAnual.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `frontend/test/superficies.test.mjs` | — | — | Sin descripción en `CODIGO_FUENTE.md`. |
| `src/convertersmartgrid/adaptadores/__init__.py` | Ada | 002 | Adaptadores de fuentes y servicios externos. |
| `src/convertersmartgrid/adaptadores/entrada/__init__.py` | Ada | 002 | Adaptadores de entrada. |
| `src/convertersmartgrid/conjuntos_aprendizaje.py` | Apl | 050, 002 | Lectura verificada del conjunto activo para inferencia, separada de la preparación. |
| `src/convertersmartgrid/contratos_aprendizaje.py` | Dom | 050, 002 | Identidad, procedencia y tipos puros de muestras y familias. |
| `src/convertersmartgrid/digital_twin/productor_pinn.py` | Ada | 050, 002 | Vista PINN congelada, con particiones comunes. |
| `src/convertersmartgrid/dominio/__init__.py` | Dom | 002 | Paquete real de valores y reglas puras, sin lectores ni E/S. |
| `src/convertersmartgrid/dominio/numeros_medidos.py` | Dom | 002, 004 | Un único cuerpo de normalización de códigos y números finitos de medición. |
| `src/convertersmartgrid/adaptadores/fuentes_estables.py` | Ada | 034, 065 | Descriptor readonly identificado y protegido contra escritura/reemplazo durante el lector. |
| `src/convertersmartgrid/medicion_obras.py` | Dom | 087 | Cuánto mejora una versión: fila por corrida de «Con proyecto» con tiempo, recursos, obras y normas, y comparación de dos métodos o versiones. |
| `src/convertersmartgrid/modelo_obras.py` | Dom | 087 | Clasificador de árboles que decide en qué tanda se mide cada variante, con su puerta de validación por sistema. |
| `src/convertersmartgrid/obras_integrales.py` | Apl | 087, 098 | Después de la escalera: transferencia y traslado a un vecino con margen (enlace y migración), solo desde barras con maniobra, y el área del… |
| `src/convertersmartgrid/planeamiento_etapas.py` | Dom | 087 | Cuándo construir cada obra: árbol de decisión y proceso de decisión de Markov. |
| `src/convertersmartgrid/productores_aprendizaje.py` | Ada | 050, 002 | Composición real y diferida por familia, con lectores/validadores existentes. |
| `src/convertersmartgrid/pronostico_demanda.py` | Ada | 089 | Pronóstico de demanda en un módulo: libros descubiertos en cada carga, equivalencia alimentador–medidor con su clase, limpieza y sentido, cabecera,… |
| `src/convertersmartgrid/puertos_muestras.py` | Pue | 050, 002 | Puerto de productores inyectado en la preparación del ciclo. |
| `src/convertersmartgrid/seleccion_bayesiana.py` | Dom | 087 | Cuándo dejar de sortear una variante: posterior Beta de que cumpla, y la certeza con que se dice. |
| `src/vnr_etl.py` | Pre | 002 | Fachada de CLI para python -m vnr_etl y el launcher anterior. |
| `tools/medir_mejora.py` | — | 087 | Registra una corrida de «Con proyecto» y compara dos métodos o versiones con sus medidas y su contraste. |
| `tools/pronostico_demanda.py` | — | 089 | Dataset y backtest de demanda desde las carpetas que haya. |
| `tools/verificar_entrega_integral.py` | — | 065, 086 | Consolida backend, frontend, auditorías y ML sin confundir regresión con aceptación eléctrica u operativa. |

### Configuración, dependencias y entrega

| Fichero |
| --- |
| `.githooks/post-commit` |
| `.githooks/post-merge` |
| `.githooks/pre-commit` |
| `.githooks/regenerar.sh` |
| `config/costes_referenciales.example.json` |
| `config/demanda_medida_alias.example.json` |
| `config/entrega.json` |
| `config/line_type_aliases.example.json` |
| `config/modulos_permitidos.example.json` |
| `config/perfil_empresa.example.json` |
| `config/perfiles/electro_dunas.estructura.json` |
| `config/perfiles/electro_dunas.json` |
| `config/perfiles/ficticia.json` |
| `config/perfiles/plantilla.json` |
| `config/pide_universal_2017.json` |
| `config/terminos_huellas.json` |
| `config/vnr_dgs_profile.json` |
| `config/vnr_settings.example.yaml` |
| `constraints-python312-win.txt` |
| `instalador/ConverterSmartGrid.iss` |
| `requirements-complemento-ia.txt` |
| `requirements-drivers.txt` |
| `requirements-madrl.txt` |
| `requirements-mcp.txt` |
| `requirements-motores.txt` |
| `requirements-nucleo.lock` |
| `requirements.txt` |
| `run_gui.bat` |
