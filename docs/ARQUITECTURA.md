# Arquitectura del conversor IGEA/CYMDIST → DIgSILENT

Estado a 2026-10-14. Describe el código **tal como está**; la organización por capas que
fija la spec 002 está aprobada pero sin hacer (ver «Arquitectura objetivo»). El detalle
de cada fichero está en `CODIGO_FUENTE.md`; los principios, en `docs/constitution.md`.

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

Aún no hay paquetes por capa (eso es la spec 002), pero el código ya se reparte así:

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
6. **Oráculo** (`oraculo.py`): flujo con pandapower antes de escribir; el DGS que no
   converge aquí no se presenta como listo.
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

**Vínculo del proyecto** (`powerfactory_binding.py`): relaciona ejecución fuente, DGS,
inventario releído y proyecto nativo aceptado, con el estado del «Caso base» de cada
alimentador. Una modificación manual posterior es un aviso
(`PROJECT_BINDING_NATIVE_MODIFIED`), nunca un bloqueo; lo que sí bloquea la calibración
es un «Caso base» sin verificar (015:RF-13).

## Web: trabajos y carriles

- **Nada largo dentro de una petición** (P7). `web/jobs.py` encola todo lo que tarda; el
  navegador sigue el progreso por WebSocket y puede cancelar.
- **Dos carriles**, cada uno con un hilo: `engine` (motor en el proceso) y `powerfactory`
  (guiones de DIgSILENT, en serie, porque PowerFactory admite un solo proceso con el
  motor a la vez).
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

## Mapa de specs sobre la arquitectura

| Spec | Parte de la arquitectura | Estado a 2026-10-14 |
| --- | --- | --- |
| 001 | Una sola vía de entrada y conversión (CLI y web), reconstrucción auditable, retirada de Tkinter | cumplida |
| 002 | Capas, puertos, módulos externos, perfil de empresa | aprobada; T1 y T5 hechas, T2–T12 pendientes |
| 004 | Demandas, cargas nuevas y demanda medida sobre un proyecto existente | implementada |
| 005 | Carpeta de proyectos de DIgSILENT, arranque acotado de los guiones | implementada; falta T12 (DIgSILENT) |
| 006 | Ajuste a la máxima de cabecera | implementada; falta T8 (DIgSILENT) |
| 007 | Cargas nuevas sobre el ajuste | implementada; falta T11 (DIgSILENT) |
| 008 | Pestaña de cargas por pasos, varios alimentadores | implementada; falta T7 (DIgSILENT) |
| 009 | Índice del código y su prueba | implementada |
| 010 | Trazado GPS de las líneas | cumplida |
| 011 | Tres casos, estudios, obras y transferencia | implementada; falta T19 (DIgSILENT) |
| 012 | Confiabilidad y capacidad de la red | aprobada; T1–T2 hechas, T3–T13 pendientes |
| 013 | Mes de análisis y transferencia entre dos alimentadores | borrador con plan, sin tareas; RF-1 a RF-6 ya con prueba |
| 014 | Calibración en «Sin proyecto», gana lo manual | implementada; falta T9 (DIgSILENT) |
| 015 | «Caso base» verificado | implementada; falta T12 (DIgSILENT) |

## Arquitectura objetivo (spec 002)

La spec 002 llevará el código a un único paquete `igea_dgs` con las capas `dominio`,
`puertos`, `aplicacion`, `adaptadores` y `presentacion`, comprobadas por una prueba de
importaciones (sin ciclos, sin nombres privados entre módulos, sin FastAPI ni
`powerfactory` en el dominio); integrará `vnr_etl` como adaptador de entrada; definirá
los puertos `LectorDeRed`, `EscritorDeRed`, `Estudio` y `SesionPowerFactory`, con
módulos externos por entry points y lista de permitidos (P9); y dará a la API modelos
Pydantic con los tipos del front generados. Mientras no se haga, las reexportaciones
temporales de `web/sources/` siguen en su sitio y la columna «Capas de hecho» de arriba
es la referencia.
