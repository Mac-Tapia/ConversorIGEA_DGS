# Arquitectura del conversor CYMDIST → DIgSILENT

Estado a 2026-11-02. Describe el código **tal como está**, también lo que aún no funciona. El detalle de cada
fichero está en `CODIGO_FUENTE.md`; los principios, en `docs/constitution.md`; el estado de cada spec, en
`specs/README.md`, que se genera y no se copia aquí.

## Vista general

El sistema tiene dos mitades que se comunican solo por ficheros:

1. **El motor** (Python 3.12, sin DIgSILENT): lee la red de una distribuidora, la
   reconstruye si viene incompleta, aplica las reglas comunes, comprueba que su flujo
   converge (oráculo) y escribe un `.dgs` por alimentador o uno con la red unida.
2. **Los guiones de PowerFactory** (`tools/*_pf.py`, con el intérprete de DIgSILENT):
   importan el DGS, verifican el «Caso base», calibran a la máxima de cabecera, insertan
   cargas nuevas y corren estudios sobre un proyecto existente.

La web (FastAPI + React) y el CLI son dos presentaciones del mismo motor. La web lanza los
guiones de PowerFactory como procesos aparte, con un plan JSON de entrada y un informe JSON
de salida, en un carril propio y en serie.

```text
 TXT (RED, CARGA, BD_Equipo) ─┐
 Base Access (.mdb) ──────────┼─► sources/ ─► contrato canónico ─► reconstrucción ─► reglas.py
 Paquete VNR-GIS (vnr_etl) ───┘   (adaptadores)  (source_contract)   (auditable)       (P5)
                                                                                         │
                                                                                         ▼
                                    validate ◄─ dgs.py ◄─ oráculo (pandapower) ◄─ FeederModel
                                       │        (perfil versionado de esquema)
                                       ▼
                                  out/*.dgs + batch_manifest.json
                                       │
           ────────────────────────────┼──────────── límite de proceso (plan/informe JSON)
                                       ▼
   tools/powerfactory_acceptance.py ─► «Caso base» verificado (015)
   tools/casos_pf.py               ─► «Sin proyecto» (copia) ─► «Con proyecto» (copia)
   tools/ajuste_cabecera_pf.py     ─► calibración en «Sin proyecto» (006, 014, 015)
   tools/cargas_pf.py              ─► demandas y cargas nuevas en «Con proyecto» (004, 007, 014)
   tools/estudios_pf.py, obras_pf.py, transferencia_pf.py ─► estudios y obras (011)
```

## Capas de hecho

Aún no hay paquetes por capa (spec 002), pero cada módulo de `src/` tiene su capa declarada en
`[tool.convertersmartgrid.capas.modulos]` de `pyproject.toml`. `tools/arquitectura.py` lo comprueba sobre el código sin
importarlo (capas, ciclos, accesos privados y drivers en el dominio), y `tests/test_capas.py` falla ante una violación
nueva. La deuda conocida está en `docs/implementacion065/deuda_arquitectura.json` y no puede crecer: 97 excepciones sobre
210 módulos. No detecta accesos privados sobre instancias. El reparto de partida:

| Capa (objetivo 002) | Hoy | Regla que ya se cumple |
| --- | --- | --- |
| Dominio | `model.py`, `naming.py`, `reglas.py`, `geography.py`, `coordenadas.py`, `puentes.py`, `sed_potencia.py`, `trafomix.py`, `catalog*.py`, `reconstruction*.py`, `capacidades.py` | Sin FastAPI ni `powerfactory`. |
| Lógica de PowerFactory sin DIgSILENT | `ajuste_cabecera.py`, `cargas_pf.py`, `demanda_medida.py`, `estudios_pf.py`, `obras_pf.py`, `transferencia_pf.py`, `economia.py` | Calculan planes y resultados con datos puros; se prueban sin DIgSILENT. Los guiones de `tools/` solo los ejecutan. |
| Puertos / contratos | `source_contract.py`, `sources/base.py`, `schema.py` + `schemas/`, `native_action.py`, `powerfactory_binding.py` | Un único contrato para las tres fuentes y para toda acción nativa. |
| Aplicación | `batch.py`, `combine.py`, `reconstruction_pipeline.py`, `oraculo.py`, `validate.py`, `inventory.py`, `perfil_empresa.py` | Una sola vía de conversión para CLI y web (001:RF-1, RF-2). |
| Adaptadores de entrada | `dataset.py` (TXT, dos disposiciones), `access.py`, `sources/{txt,mdb,vnr,snapshot}.py`, `src/vnr_etl/` | Reconocen la entrada por contenido (`identify.py`), no por nombre. |
| Adaptadores de salida | `dgs.py`, `export_tables.py`, `preview.py`, `powerfactory_env.py`, `powerfactory_metadata.py`, `carpeta_pf.py` | El DGS es idéntico byte a byte con 1 o N procesos (P1). |
| Presentación | `cli.py`, `web/` (FastAPI), `frontend/` (React), `tools/` | La web no calcula: `web/services.py` llama al motor o lanza un guion. |

`src/vnr_etl/` es un paquete aparte con su propia arquitectura en capas
(`connectors`, `discovery`, `gis`, `models`, `validation`, `exporters`, `application`);
su diseño está en `VNR-GIS.md`. Exporta al motor por `application/cymdist_bridge.py`,
de modo que el DGS de VNR-GIS sale del mismo `dgs.py` que el de TXT y MDB.

## Flujo de conversión

1. **Lectura.** El adaptador de la fuente elegida devuelve un `CymdistDataset` (una sola
   lectura para todos los alimentadores). `sources/snapshot.py` fija la huella de los
   ficheros y `web/source_runs.py` los custodia sin mutarlos: cada carga es una ejecución
   inmutable y no se mezclan fuentes.
2. **Selección.** Un alimentador, varios o todos, por NetworkID o nombre corto; un estudio
   CYMDIST (`study.py`) puede filtrar la selección. Nada recorre una tabla entera por
   alimentador (P2): los índices se construyen una vez por dataset.
3. **Reconstrucción** (opcional, 001:RF-17 a RF-22). Si faltan nodos, tramos o parámetros
   se trabaja sobre una copia: primero el valor original, luego catálogo exacto, de
   fabricante y global; cada supuesto queda anotado. Nada bloquea salvo una red vacía.
4. **Reglas** (`reglas.py`, P5): `preparar_dataset`, `aplicar_reglas`,
   `auditar_completitud`. Las convenciones de empresa salen del perfil (P13).
5. **Modelo** (`model.py`, modo estricto): no inventa tipos `DEFAULT`; los alias de tipos
   de línea solo vienen de `config/line_type_aliases.json`.
6. **Oráculo** (`oraculo.py`): flujo con pandapower antes de escribir. Si no converge busca la causa y la corrige
   (057), y a DIgSILENT llega convergido; lo que no pueda corregir no se presenta como listo.
7. **Escritura** (`dgs.py` + perfil `schemas/pf21_dgs_1_8_4.json`): tablas, FID,
   cubículos, maniobras, capa gráfica y trazado GPS de cada línea (010).
8. **Validación** (`validate.py`) y publicación atómica (P6): nunca queda un `.dgs` a
   medias; un alimentador que falla no invalida a los demás; `batch_manifest.json` se
   escribe siempre. `batch.py` reparte en procesos (tope medido: 4).

## Flujo en PowerFactory: los tres casos de estudio

El trabajo sobre un proyecto de DIgSILENT se ordena en tres casos (specs 011, 014, 015):

| Caso | Qué es | Quién lo cambia |
| --- | --- | --- |
| «Caso base» | La red física verificada frente al archivo original: GPS, trazado, conectividad, diagrama, capacidades, grupo y tensión de los transformadores. Su flujo se prueba al importar el DGS; si no converge se reduce la demanda, sin bloquear (015). | Nadie después de verificarlo. |
| «Sin proyecto» | Copia del «Caso base». Aquí se calibra a la máxima de cabecera (006) y aquí hace el operador sus cambios manuales; si chocan, **gana lo manual** (014). Demanda y escala en su escenario, sin variaciones de la aplicación (015). | El ajuste y el operador. |
| «Con proyecto» | Copia de «Sin proyecto» con su escenario. Solo aquí nacen las cargas nuevas, una variación por carga, sin duplicados (007, 014:RF-23 a RF-28). | La inserción de cargas nuevas y las obras (011). |

Sobre «Sin proyecto» y «Con proyecto» corren los estudios con los módulos nativos de
DIgSILENT (`estudios_pf.py`: flujo, cortocircuito, N-1, optimizadores…), las obras de
mejora (`obras_pf.py`, una variación por obra) y la transferencia de carga entre dos
alimentadores (`transferencia_pf.py`, sin dejar nada en el proyecto).

El flujo que usa un informe es el equilibrado si el desequilibrado no cuadra con la cabecera (063:RF-45). Las fases
`plinir/s/t` de una carga son dato de la red, compartido entre casos, y `plini` es de cada escenario: en SM218, 292 de
306 cargas no cuadran (+28 % en cabecera). Es una deuda abierta: el desequilibrado no vale hasta conciliarlas.

**Vínculo del proyecto** (`powerfactory_binding.py`): relaciona ejecución fuente, DGS,
inventario releído y proyecto nativo aceptado, con el estado del «Caso base» de cada
alimentador. Una modificación manual posterior es un aviso
(`PROJECT_BINDING_NATIVE_MODIFIED`), nunca un bloqueo; lo que sí bloquea la calibración
es un «Caso base» sin verificar (015:RF-13).

## Web: trabajos y carriles

- **Nada largo dentro de una petición** (P7). `web/jobs.py` encola todo lo que tarda; el
  navegador sigue el progreso por WebSocket y puede cancelar.
- **Tres carriles**, cada uno con un hilo: `engine` (motor en el proceso), `powerfactory` (guiones de DIgSILENT, en
  serie, porque admite un solo proceso con el motor a la vez) y `asistente` (órdenes en lenguaje natural).
- **Arnés de DIgSILENT** (019, 064): `pf_arnes.conectar` da el turno exclusivo a guiones y sondas; `tools/pf_servidor.py`
  conserva la conexión y restituye el estado tras cada orden.
- **Contrato de la API** (065): `tools/generar_contrato_api.py` genera `frontend/src/api/esquema.ts`, y `tests/test_contrato_api.py`
  detecta divergencias con el front.
- **Temporales** (065): `runtime_paths.py` lleva cachés y staging fuera del checkout, y `web/retencion.py` limpia a diario (062).
- **Guiones de PowerFactory.** Se lanzan con el intérprete de DIgSILENT
  (`powerfactory_env.py`), sin consola de entrada, con plan JSON y, si se cancelan,
  un fichero de cancelación que el guion lee entre alimentadores (termina el que está
  en curso y no empieza otro). Cada guion escribe su primera línea al conectar; si no
  llega en `LIMITE_ARRANQUE_PF_S` se corta con sus hijos y se dice por qué (005:RF-21).
  Antes de lanzar uno se cierran los guiones huérfanos de una sesión anterior.
- **Espacio de trabajo** (`web/workspace.py`): entradas, opciones, salidas y obras sin
  aplicar de una sesión; los ficheros de cada ejecución, inmutables (`source_runs.py`).
- **Front** (`frontend/src`): React + TypeScript, cliente tipado en `api.ts`. La pestaña
  «Cargas en DIgSILENT» sigue los pasos 1 · Proyecto, 2 · Alimentadores y calibración,
  3 · Integración de nuevas y 4 · Obras y estudios (008, 011).

## Configuración por empresa

`config/perfil_empresa.json` (local, fuera de git, puede heredar de `config/perfiles/`):
CRS de origen, patrón de SED de medición, forma de los nombres de alimentador, escala del
diagrama, carpeta de DIgSILENT. Sin perfil no se supone nada: el CRS se pide y ninguna SED
se excluye por su nombre (P13). Alias de tipos de línea en
`config/line_type_aliases.json`, también local.

## Informes (017, 063, 066)

El botón «Generar informe de factibilidad» prepara los tres casos, corre sus flujos y escribe el resultado sin pasar por
otro paso: Word (`informe_docx.py`), PDF y, donde el perfil lo declare, el libro Excel (`libro_informe.py`).

- **Datos del solicitante:** de los PDF (`documentos_solicitud.py`). El formulario guardado es de una carga y se vacía al
  elegir otra; un cliente que no corresponde a la carga se avisa y queda como hueco (063:RF-48, RF-49).
- **Pérdidas reconocidas y precio:** del libro de la empresa (`libros_informe.py`). En Electro Dunas, columnas H y G de
  `Perdidas_ELDU` y `Informe!G183`, las mismas que usa el informe modelo.
- **Libro del informe:** el plano de celdas va en `config/perfiles/electro_dunas.json`; sin esa sección no hay libro (066:RF-2).
  Excel aplica el plan por COM, porque openpyxl pierde imágenes y gráficos al guardar, y después se relee y se comprueba:
  datos del modelo, errores de fórmula e importes contra el Word. En el equipo de desarrollo, `Excel.Application` y
  `Word.Application` los puede responder WPS Office, aunque diga ser Microsoft.

## Asistente y su equipo (026, 027, 047, 061, 065, 067)

Una orden del operador recorre esto. Solo el rol `operador` ejecuta, y toda escritura espera confirmación:

```text
 Asistente.tsx ─► POST /asistente ─► carril «asistente»
                                       │
      interprete.py: Transformer (conf. ≥ 0,85) ─► Ollama (≥ 0,6) ─► «ninguno»
                                       │           las reglas solo fijan ruta y periodo
                                       ▼
      plan.py + tareas.py ─► equipo.py: GobiernoEquipo.desde_plan ─► planes_guardados.py
                                       │
      consulta: responde · lectura: se ejecuta · escritura: botón ─► gobierno.confirmar
                                       ▼
      ejecutor.py: autorizar_peticion + validar_paso ─► HTTP a la propia API ─► trabajo normal
```

| Pieza | Fichero | Estado |
| --- | --- | --- |
| Intérprete, plan, tareas, salida validada | `asistente/{interprete,plan,tareas,contratos_salida}.py` | conectado y probado |
| Gobierno y permisos por rol | `asistente/equipo.py`, `web/equipo_api.py` | conectado y probado; sin uso real registrado |
| Ejecutor | `asistente/ejecutor.py` | conectado y probado; 026 T12 abierta en DIgSILENT |
| Orquestador del proyecto entero | `asistente/orquestador.py` | conectado; probado con dobles. Un clic confirma la lista de etapas que el operador ve antes |
| Planes guardados | `asistente/planes_guardados.py` | conectado y probado con reinicio simulado: siguen pidiendo confirmación y nunca se reanudan solos |
| Monitor y vigilancia | `asistente/{observacion,vigilancia}.py` | conectados y probados |
| RAG con citas | `asistente/indice.py` | conectado: BM25, y coseno si hay vectores. Sin reranker |
| Corpus ampliado y lecturas del proyecto | `asistente/{corpus_proyecto,lectura_proyecto}.py`, `tools/mcp_conversor.py` | lecturas conectadas a `pregunta` y al MCP local, solo lectura. El corpus ampliado no se sirve hasta pasar su medición (077:RF-47); sus cifras y las de la 047 no son intercambiables |
| Revisión por roles y evidencia | `asistente/revision_roles.py`, `asistente/evidencias_web.py` | conectadas y probadas con el transporte de Ollama simulado; sin revisión real registrada |

**Lo que el equipo es:** `fuentes`, `fisica`, `coste` y `riesgo` son el mismo modelo de Ollama con otro prompt de sistema, no
agentes separados, y su revisión es documental (`autoriza_ejecucion=False`). Exige evidencias en
`observacion/evidencias` del espacio, que se custodian solas cuando un informe, un estudio, un PIDE o unas obras terminan
bien, con el proyecto de su resultado y la huella de la fuente de su vínculo. Las tareas `obras_escalera` y
`optimizar_con_proyecto` van por sus rutas; mientras el Transformer en uso no las aprenda, se reconocen por su frase
literal. La optimización PNL de la spec 048 aún no tiene tarea.

## Modelos (024, 043, 045, 046, 060)

Un modelo «en uso» es el que apunta `promovido.json`. El registro (`model_registry.py`) guarda candidatos y decisiones, y
`asistente/modelos_en_uso.py` es lo único que lleva un candidato aprobado a ese puntero, salvo el camino antiguo por CLI sin
`--integral`. Medido en el equipo de desarrollo el 2026-11-02:

| Modelo | Fichero | Para qué | Estado |
| --- | --- | --- | --- |
| Transformer de órdenes | `asistente/transformer.py` | Texto a tarea y datos | en uso: `20261024-150042-37ce` (acierto 0,981). Los candidatos posteriores no pasaron sus puertas |
| Transformer de informes | `asistente/clasificador.py` | Tipo y subtipo de documento | en uso: `20261024-150047-b3c4` (subtipo 0,987) |
| LLM por Ollama | `asistente/ollama.py` | Órdenes y revisor | en uso: `llama3.1:8b` (75,9 % en 54 órdenes). `qwen3:8b` no aprobó sus puertas |
| LLM alumno (QLoRA a GGUF) | `asistente/llm_destilacion.py`, `llm_runtime.py` | Modelo propio | solo por CLI, **sin entrenar y no activado** |
| PINN/GNN del gemelo | `digital_twin/oraculo.py` | Grafo y cargas a V y θ, por conjunto de 3 | en uso: `20261028-114528-e6f5` (mae 0,002435). Filtra candidatos; DIgSILENT decide. Exige GPU también para predecir |
| PowerFlowNet con PyG | `digital_twin/adaptador_pyg.py` | Arquitectura alternativa | solo código; nada la selecciona |
| Flujo físico propio | `digital_twin/flujo.py` | Comprobación sin pesos | conectado y probado |
| GRU | `digital_twin/temporal.py` | Serie a **reconstrucción un paso adelante**, no pronóstico | conectada: entrena en cada trabajo, sin pesos guardados. Solo por orden del asistente |
| GRU candidata | `digital_twin/temporal_entrenamiento.py` | Candidato persistente | solo por CLI, no promovida |
| Embeddings entrenables | `asistente/embeddings.py` | Encoder versionado | solo por CLI, **sin encoder entrenado** |
| N-HiTS, TFT, PatchTST | `tools/reentrenar_modelos.py` | Pronóstico | **solo especificados**: devuelven `ERROR_ENTORNO` |

**Aprendizaje:** `tools/construir_dataset_entrenamiento.py` arma el dataset y dice qué falta (043). El último tiene 2 056
registros, sin fugas entre particiones, y está **incompleto**: 5 órdenes humanas de 200. «Reentrenar» desde la web registra
el candidato y lo pone en uso solo si el registro lo aprobó por sus puertas, incluida la comparación con el modelo en uso;
si no, sigue el actual. El clasificador va por la misma vía, y sin informes reales en su prueba queda `BLOQUEADO_POR_DATOS`
sin entrenarse. El ciclo conjunto de `training_coordinator.py` no ha corrido nunca completo (050 abierta). Entrenar exige
CUDA: sin GPU se dice el error. El Transformer de órdenes en la web cede a Ollama y el plan dice el motivo y quién respondió.

## Optimización (025, 042, 044, 048, 052)

| Técnica | Fichero | Dónde se usa | Estado |
| --- | --- | --- | --- |
| Escalera de obras: bancos, sección, combinación, terna y regulador | `escalera_optima.py` | Paso de obras de la web, evaluada en DIgSILENT | conectada y probada; es enumeración por variantes |
| Búsqueda bayesiana (Optuna TPE) | `optimizacion_oraculo.py` | Optimización de «Con proyecto» | conectada; probada con doble. 052 T4 abierta |
| NSGA-II de Pareto, propio | `optimizacion_oraculo.py` | Igual | igual |
| Markov y Shapley, propios | `optimizacion_oraculo.py` | Igual | igual |
| GA y NSGA-II de bancos, propios | `digital_twin/evolutivo.py` | Propuestas del PIDE | conectados y probados |
| Evolución diferencial, reconfiguración y consigna | `digital_twin/evolutivo.py` | Nadie fuera de pruebas | solo código |
| **PNL (Pyomo e Ipopt)** | ninguno | Ninguno | **solo especificada** (048): las dependencias están instaladas y nada las usa |
| **Optimización mixta y pymoo** | ninguno | Ninguno | **solo especificadas** (048) |

El oráculo solo ordena y filtra: **toda obra se confirma con los módulos nativos de DIgSILENT**, que manda si discrepa.

## Pronóstico y evaluación (029, 044, 046)

- **Crecimiento por alimentador** (`crecimiento.py`, 029): tasa aritmética desde la medición de cabecera; conectado.
- **Series causales** (`digital_twin/series_causales.py`, 046): preparación; solo por CLI.
- **Multihorizonte con cuantiles** (046): **solo especificado**, no hay código.
- **Particiones y puertas** (`evaluacion_modelos.py`, 044): conectadas. La verificación nativa del top-k, solo especificada.

## Deudas conocidas

1. El flujo desequilibrado no cuadra hasta conciliar las fases con `plini`.
2. PNL, optimización mixta y pronóstico multihorizonte están especificados y sin implementar.
3. La partición de `web/services.py` y la migración de paquetes de la spec 002 siguen pendientes.

## Retención diaria de ejecuciones (spec062)

`web/retencion.py` comparte la raíz de WorkspaceStore y el control de admisión de
JobManager. El lifespan inicia una tarea asíncrona con el trabajo de archivos en
`asyncio.to_thread`; cada60 segundos comprueba si venció el plazo de24 horas,
cuya fecha queda persistida. La tarea se detiene cooperativamente al apagar.
El mantenimiento y la admisión de nuevos trabajos son excluyentes; cualquier
trabajo pendiente aplaza la limpieza sin cancelarlo.

Las referencias de todos los espacios y sus estados en memoria protegen las
ejecuciones utilizadas. Los árboles se validan antes de retirar y se rechazan
redirecciones, enlaces simbólicos y junctions. Los enlaces duros solo pierden
la entrada de una ejecución obsoleta: la fuente externa conserva su nombre.
La respuesta del monitor incluye política y resumen; no se añade sondeo en la web.

## Estudio de planeamiento: PIDE y largo plazo (spec 072)

Estado a 2026-11-02: **aprobada, sin implementar**. Hoy el código diagnostica por años (`tools/pide_pf.py`, spec 030) y da una
propuesta parcial de obras; no genera los entregables. Lo calibrado hasta ahora es el caso base o año cero.

| Entregable | Horizonte | Casos | Salidas |
| --- | --- | --- | --- |
| Largo plazo | 20 años | Años 04, 08, 12, 16, 20 | Mercado, densidad, diagnóstico, alternativas, plan de obras, F01-F07 |
| PIDE | Años 04-07 | Alternativas con y sin proyecto | Fichas, costos, VAN, TIR, priorización, F08-F15 |

- **Años:** el estudio declara su año de presentación, cada 4 años; el año 00 es el anterior. Con presentación 2027, año 00 = 2026.
  Ningún año va fijo en el código.
- **Flujo:** caso base → proyección de mercado (031/046) → cada caso por año (030) → obras acumuladas → evaluación → entregables.
  El PIDE consume el largo plazo.
- **Costos públicos de Osinergmin, Procesos Regulatorios:** SICODI para distribución, módulos estándar para transmisión y VNR
  aprobado de cada empresa, cada uno con resolución, año y huella. No se mezclan ni llevan factores sin sustento.
- **Modelos:** el pronóstico aporta la demanda; el oráculo, el flujo; los evolutivos, las alternativas; DIgSILENT confirma. El
  asistente orquesta los mismos pasos y redacta; los entregables históricos le sirven de corpus, nunca como verdad eléctrica.
- **Casos de prueba:** los nombres de empresas, clientes y proyectos de ejemplos, pruebas y documentos son casos de prueba del
  conversor, no valores por defecto (072:RF-20).
