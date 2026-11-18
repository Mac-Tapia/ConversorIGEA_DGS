# Arquitectura de ConverterSmartGrid

Revisado a mano el 2026-11-04, sobre `main` en `c9c4d129` (versión `1.0.0rc1`), y puesto al día el 2026-11-16 con las specs 102 y 107 a 112. Describe el código **tal como está**, también lo que aún
no funciona. **Todos los módulos, las tareas del asistente, los roles de su equipo y las cifras están en
[`ARQUITECTURA_CATALOGO.md`](ARQUITECTURA_CATALOGO.md), que se genera solo en cada commit (spec 090).** Aquí queda el porqué. Lo que
está en ramas sin integrar se cita aparte, en
[Deudas y trabajo sin integrar](#deudas-y-trabajo-sin-integrar).

Dónde está el resto: el detalle y la spec de cada fichero, en [`CODIGO_FUENTE.md`](../CODIGO_FUENTE.md); los principios, en
[`constitution.md`](constitution.md); el estado de cada spec, en [`specs/README.md`](../specs/README.md), que se genera y no se
copia aquí; las órdenes, en [`MANUAL_COMANDOS.md`](MANUAL_COMANDOS.md); el C4 navegable, en
[`architecture/workspace.dsl`](architecture/workspace.dsl) y su página interactiva.

## Vista general

ConverterSmartGrid lee la red de una distribuidora (TXT, base Access o paquete VNR-GIS), la convierte en un `.dgs`
y, sobre el proyecto importado en DIgSILENT PowerFactory, la verifica, la calibra, proyecta obras y cargas nuevas, corre estudios
y escribe informes y entregables de planeamiento. Corre entero en la máquina del operador.

El sistema tiene dos mitades que se comunican solo por ficheros:

1. **El motor** (Python 3.12, sin DIgSILENT): lee, reconstruye si hace falta, aplica las reglas comunes, comprueba el flujo con su
   oráculo y escribe un `.dgs` por alimentador o uno con la red unida. También calcula, con datos puros, todos los planes y
   resultados que los guiones ejecutan o leen.
2. **Los guiones de PowerFactory** (`tools/*_pf.py`, con el intérprete de DIgSILENT): importan, verifican, calibran, insertan
   cargas, aplican obras y corren estudios sobre un proyecto existente.

La web y el CLI son dos presentaciones del mismo motor. La web lanza los guiones como procesos aparte, con un plan JSON de
entrada y un informe JSON de salida.

```text
 Operador ─► Navegador ─► web/seguridad ─► web/app (FastAPI) ─► web/services ─► web/jobs (5 carriles)
                                                                                 │
   ┌─────────────────────────────┬───────────────────────────────┬───────────────┴──────────┐
   ▼ engine                      ▼ powerfactory                  ▼ asistente                ▼ control
 motor de conversión           guiones *_pf.py                 interpreta, planifica,     solo cancela
 sources ► reglas ► model      ─ pf_arnes (turno exclusivo)    espera confirmación y
 ► oráculo ► dgs ► validate    ─ pf_servidor (conexión viva)   encola en los otros
   │                             │                               │
   ▼                             ▼                               ▼
 out/*.dgs                     DIgSILENT PowerFactory 2024     Ollama local, modelos en GPU
 batch_manifest.json             │
                                 ▼
                         informe JSON ─► vínculo ─► episodio del gemelo ─► informes y entregables
```

## Procesos y despliegue

Todo es local, en Windows. La web solo atiende a esta máquina.

| Proceso | Qué corre | Cómo se comunica |
| --- | --- | --- |
| Web | `convertersmartgrid-web` (o `run_gui.bat`, o el acceso directo), `127.0.0.1:8765`; sirve `frontend/dist` | HTTP y WebSocket con token de sesión |
| Hilos de carril | Uno por carril, dentro de la web | Colas de `web/jobs.py` |
| Lote de conversión | Hasta 4 procesos de `batch.py` (tope medido) | Resultado por proceso; DGS idéntico con 1 o N |
| Guion de DIgSILENT | `tools/*_pf.py` con el intérprete de PowerFactory | Plan e informe JSON, fichero de cancelación |
| Servidor de DIgSILENT | `tools/pf_servidor.py`, se cierra a los 2 minutos sin órdenes | `tools/pf_cliente.py`; repone el estado si una orden falla |
| Entrenamientos | `tools/digital_twin_*`, `tools/asistente_*`, con guardia de GPU | Informe JSON atómico |
| Ollama | Modelo local, opcional | Solo direcciones de la máquina |
| SQL Server Express | Restaura copias `.bak` de VNR-GIS | `connectors/sqlserver_vnr.py` |
| MCP local | `tools/mcp_conversor.py`, opcional | stdio, solo lectura; ver [`MCP_CONVERSOR.md`](MCP_CONVERSOR.md) |

**Dónde queda cada dato:**

| Lugar | Contenido |
| --- | --- |
| `output/web/<espacio>/` | Entradas, opciones, ejecuciones inmutables, DGS, informes y planes de un espacio |
| `output/web/_asistente/` | Órdenes, señales, modelos, `model_registry`, índice, datasets y observación |
| `output/web/_digital_twin/` | Episodios (JSON por huella, `episodios.sqlite3`), objetos y modelos del oráculo |
| `CSG_DATOS_HOME` | Datos de un programa instalado; sin ella, la carpeta del usuario |
| `CSG_RUNTIME_HOME`, `CSG_CACHE_HOME`, `CSG_TEMP_HOME` | Cachés y staging fuera del checkout (`runtime_paths.py`) |
| `~/.convertersmartgrid/` | `tessdata` y las dependencias aparte `madrl_deps` y `motores_deps` |
| `config/perfil_empresa.json`, `config/line_type_aliases.json` | Convenciones locales de la empresa, fuera de git |
| `external/` | Solvers (`ipopt`, `llama`) y clones fijados de terceros (`llama_cpp`, `neuralforecast`, `peft`, `powerflownet`, `pyg`) |

Los datos de una distribuidora nunca entran en git. Cada fuente se carga por su ruta.

**Dependencias por archivo:** `requirements.txt` con `constraints-python312-win.txt` es el desarrollo; `requirements-nucleo.lock`
es el núcleo de la entrega, con huellas; `requirements-complemento-ia.txt`, el complemento de IA de la entrega. Aparte y fuera del
`.venv` común: `requirements-drivers.txt` (VNR-GIS), `requirements-motores.txt` (083), `requirements-madrl.txt` (074) y
`requirements-mcp.txt` (077).

## Capas

Cada módulo vive en el paquete de su capa (002 T7): `dominio/`, `puertos/`, `aplicacion/`, `adaptadores/` (con `entrada/`
para lo que se lee, `vnr/` incluido, `salida/` para lo que se escribe y `nube/` para las cuentas) y `presentacion/`; su capa
sigue declarada en `[tool.convertersmartgrid.capas.modulos]` de `pyproject.toml` y `tests/test_capas.py` exige que paquete y
capa coincidan. Las rutas de antes, que siguen en los conjuntos sellados y los documentos fechados, se leen con
`docs/architecture/rutas_antes_002.json`. `tools/arquitectura.py` lo comprueba sobre el código sin importarlo
(capas, ciclos, accesos privados y drivers en el dominio), y `tests/test_capas.py` falla ante una violación nueva. La deuda está en
`docs/implementacion065/deuda_arquitectura.json`, no puede crecer y una excepción retirada también falla; cuántas quedan lo dice el
catálogo. No detecta accesos privados sobre instancias.

| Capa | Qué contiene | Regla |
| --- | --- | --- |
| Dominio | Modelo, nombres, perfil, contratos y cálculos sin dependencias | Sin FastAPI, `powerfactory` ni drivers |
| Puertos | `sources/base.py`, `puertos.py` | Un único contrato para las fuentes y los módulos |
| Aplicación | Lote, reglas, calibración, obras, estudios, PIDE, gobierno y asistente | Una sola vía de conversión para CLI y web (001:RF-1, RF-2) |
| Adaptadores | Lectores, DGS, DIgSILENT, informes, gemelo y `vnr_etl` | Reconocen la entrada por contenido; DGS idéntico con 1 o N procesos (P1) |
| Presentación | `cli.py`, `web/`, CLI de `vnr_etl` | La web no calcula: `web/services.py` llama al motor o lanza un guion. |

`tools/` y `frontend/` quedan fuera de esa tabla: son presentación de hecho.

**Módulos enchufables (002):** un paquete declara un objeto `Modulo` en el grupo de entry points `convertersmartgrid.modulos`, y
`registro_modulos.py` comprueba su versión y sus métodos. Hoy van por esa vía `escritor-dgs` y los lectores `lector-txt`,
`lector-mdb` y `lector-vnr`. `config/modulos_permitidos.json` limita los que se cargan.

`src/convertersmartgrid/adaptadores/entrada/vnr/` contiene el adaptador VNR-GIS (`connectors`, `discovery`, `gis`, `models`, `validation`,
`exporters`, `application`); su diseño está en [`VNR-GIS.md`](../VNR-GIS.md). Exporta al motor por `application/cymdist_bridge.py`,
de modo que su DGS sale del mismo `dgs.py`. La fachada `src/vnr_etl.py` conserva únicamente
`python -m vnr_etl` y el entry point anterior `vnr_etl.cli:main`; los consumidores usan la ruta canónica.
La comparación final de fuentes reales y aceptación nativa de la migración 002 sigue pendiente.

**Custodia histórica (076:RF-4).** En la revisión `10fd3e1d`, anterior a esta migración,
la descripción era «`src/vnr_etl/` es un paquete aparte». Esa frase queda como ancla
de los conjuntos fechados 076/077, cuyas citas y etiquetas se conservan. Describe
aquella revisión; la ubicación operativa actual es el adaptador indicado arriba.

## Flujo de conversión

1. **Lectura.** El adaptador de la fuente elegida devuelve un `CymdistDataset`, una sola lectura para todos los alimentadores.
   `sources/snapshot.py` fija la huella de los ficheros y `web/source_runs.py` los custodia: cada carga es una ejecución
   inmutable y no se mezclan fuentes.
2. **Selección.** Un alimentador, varios, todos o un sistema eléctrico (`estructura.py`). Un estudio CYMDIST (`study.py`) puede
   filtrarla. Nada recorre una tabla entera por alimentador (P2): los índices se construyen una vez por dataset.
3. **Reconstrucción** (001:RF-17 a RF-22). Si faltan nodos, tramos o parámetros se trabaja sobre una copia: primero el valor
   original, luego catálogo exacto, de fabricante y global, y el catálogo crece con cada código nuevo (053). Cada supuesto queda
   anotado. Nada bloquea salvo una red vacía.
4. **Reglas** (`reglas.py`, P5): `preparar_dataset`, `aplicar_reglas`, `auditar_completitud`. Las convenciones de empresa salen del
   perfil (P13). Las fases reales de tramos y SED se resuelven aquí (054, `fases_red.py`, `comprobacion_fases.py`).
5. **Modelo** (`model.py`, modo estricto): no inventa tipos; los alias solo vienen de `config/line_type_aliases.json`.
6. **Red unida** (`combine.py`, `enlaces.py`, 022): cuelga los alimentadores de sus SET con barra por tensión e interruptor de
   cabecera, y deja la red radial con las aperturas que indica.
7. **Escritura** (`dgs.py` con `schemas/pf21_dgs_1_8_4.json`): tablas, FID, cubículos, maniobras, capa gráfica y trazado GPS.
   `preflight_contract.py` fija el modelo efectivo junto al DGS.
8. **Validación** (`validate.py`) y publicación atómica (P6): nunca queda un `.dgs` a medias; un alimentador que falla no invalida a
   los demás; `batch_manifest.json` se escribe siempre.
9. **Oráculo** (`oraculo.py`, 057, 082): flujo con pandapower sobre la misma red, en la conversión unida y como comprobación previa
   al importar (`web/services.py`, con el modelo fijado al DGS). Si no converge por una demanda de relleno o mayor que su SED,
   busca el factor con que converge; `reglas.py` aplica esa corrección y la anota. Es consultivo: sus avisos no omiten el DGS.

## Flujo en PowerFactory

### Los casos de estudio

| Caso | Qué es | Quién lo cambia |
| --- | --- | --- |
| «Caso base» | La red física verificada frente al archivo original: GPS, trazado, conectividad, diagrama, capacidades, grupo y tensión de los transformadores. Se importa con los datos originales (032) y llega convergido (057); si no, `resolver_convergencia.py` dice su causa y corrige lo reconstruible. | Nadie después de verificarlo. |
| «Sin proyecto» | Copia del «Caso base». Aquí se calibra (006, 015, 025) y aquí hace el operador sus cambios, y si chocan **gana lo manual** (014). | El ajuste y el operador. |
| «Cargas nuevas» | Caso de diagnóstico: con las cargas nuevas y sin obras (025:RF-61, 037). Se mide y se presenta, pero no está entre los tres que decide `tres_casos`. | La inserción de cargas. |
| «Con proyecto» | Copia de «Sin proyecto» con su escenario. Aquí nacen las cargas nuevas, una variación por carga, sin duplicados (007, 040), y las obras (011). | Cargas y obras. |

Con el año de medición (025) y los del PIDE (030), cada caso se repite por año y no se mezclan. Las maniobras manuales del operador
son intencionales: se avisa (`PROJECT_BINDING_NATIVE_MODIFIED`), nunca se bloquea.

**Vínculo del proyecto** (`powerfactory_binding.py`): relaciona ejecución fuente, DGS, inventario releído y proyecto nativo aceptado,
con el estado del «Caso base» de cada alimentador. Lo único que bloquea la calibración es un «Caso base» sin verificar (015:RF-13).

### Calibración

1. **Escaneo** (`escaneo.py`, `tools/escanear_alimentador_pf.py`, 028): de quién es cada generador, banco y variación.
2. **Objetivo** (`demanda_medida.py`, `cabecera_ancha.py`, `libros_por_anio.py`): la máxima de cabecera del alcance elegido:
   hasta 3 alimentadores, una SET o un sistema con sus barras de 60 kV (028, 039). Con central térmica, por zonas (021).
3. **Reparto** (`ajuste_cabecera.py`): fijas de la tabla en el instante; las escaladas por kVA con FP 0,98 y un escalar, en
   probabilidad (035, 041).
4. **Arranque con el oráculo** (`oraculo_calibracion.py`, 083): los factores iniciales, sin gastar flujos de DIgSILENT, que sigue
   siendo la referencia.
5. **Cuadre conjunto** (`tools/ajuste_cabecera_pf.py`): todos los alimentadores del proyecto en los mismos flujos, con bancos,
   transformadores nuevos de las SED sobrecargadas (`trafos_sed.py`, 020) y la consigna de la fuente.
6. **Valle** (`valle.py`, 073): su instante y duración salen de la medición; los bancos y proyectos se comprueban en máximos y en
   valle. `comprobacion_flujo.py` contrasta lo que el flujo dijo con lo que pasó (081).

El flujo que usa un informe es el equilibrado si el desequilibrado no cuadra con la cabecera (063:RF-45). Las fases `plinir/s/t` de
una carga son dato de la red, compartido entre casos, y `plini` es de cada escenario.

### Obras y cargas nuevas

| Paso | Módulo | Qué hace |
| --- | --- | --- |
| Punto de conexión | `troncal.py`, `tools/cargas_pf.py` (016) | Camino más largo y punto más cercano; parte el tramo o usa la barra |
| Escalera | `escalera_optima.py` (042, 063, 073) | `bancos`, `seccion`, `terna`, `regulador`, y sus combinaciones; sorteos con semilla sobre la curva de cabecera y costo anual |
| Filtro del oráculo | `optimizacion_oraculo.py` (052) | Ordena candidatos con el flujo del gemelo |
| Aplicación | `tools/obras_pf.py`, `obras_pf.py` (011, 016) | Una variación por obra; enlace y migración solo en «Con proyecto» |
| Confirmación | `digital_twin/evolutivo.py:verificar_top_k`, `evaluacion_modelos.py` (044) | Relee tras reabrir y compara con el oráculo; lo que no pasa se avisa y no se acepta |
| SET nueva | `set_nueva.py`, `sitio_set.py`, `vias.py` (042, 084) | Para lo que no cabe: potencia de diseño, módulo del CAPEX, Weber y sitio libre |
| Ternas | `instalacion_ternas.py` (084) | Por ducto o en configuración, con la capacidad del fabricante |

**Toda obra se confirma con los módulos nativos de DIgSILENT, que manda si discrepa.**

### Estudios

`tools/estudios_pf.py` corre un estudio en un caso con los módulos nativos: flujo, desequilibrado, contingencias, troncal, punto de
apertura, perfil de tensión y balance de fases (011). Los de la 012 van por `tools/confiabilidad_pf.py` (`ComRel3`, `ComOpri`) y
`tools/capacidad_pf.py` (`ComHostcap`, `ComPvcurves`, `ComCapo`), según la licencia y el libro de la empresa. La transferencia de
carga (`tools/transferencia_pf.py`, 013) no deja nada en el proyecto. Los guiones DPL y Python del operador corren con `--guion`.

### Arnés de DIgSILENT (019, 064)

El motor admite un solo proceso a la vez. `pf_arnes.conectar` da el turno exclusivo, que es de la máquina y no de la sesión: un fichero creado
en exclusiva que dice qué proceso lo tiene y se libera si su dueño murió. `tools/pf_servidor.py` conserva la conexión, y
`pf_estado.py` fotografía el estado antes de una orden y lo repone si falla. Cada guion escribe su primera línea al conectar; si no
llega en `LIMITE_ARRANQUE_PF_S` se corta con sus hijos (005:RF-21). Antes de lanzar uno se cierran los huérfanos de una sesión
anterior. `estadistica_ordenes.py` registra cada orden para contrastar versiones (081).

## Web

- **Nada largo dentro de una petición** (P7). `web/jobs.py` encola; el navegador sigue el progreso por WebSocket y puede cancelar.
- **Cinco carriles**, cada uno con un hilo: `engine` (motor en el proceso),
  `powerfactory` (guiones de DIgSILENT, en serie), `asistente` (solo
  espera: sus pasos encolan en los otros dos), `control` (solo cancela, para poder parar lo que corre con el asistente ocupado,
  070:RF-33) y `correo` (envío de informes por correo, que espera a la red y no al motor ni a DIgSILENT; sin relanzar tras
  un reinicio, 110:RF-9).
- **Puerta** (`web/seguridad.py`, 086:RF-17 a RF-21): un solo middleware ASGI comprueba Host, Origin y token, también en el
  WebSocket, y pone la política de contenido, de modo que una ruta nueva nace cerrada. En el navegador el token va en una cookie
  `HttpOnly`; los programas locales lo mandan en cabecera (`sesion_web.py`). Ver [`SEGURIDAD_Y_PRIVACIDAD.md`](SEGURIDAD_Y_PRIVACIDAD.md).
- **Contrato** (065): `tools/generar_contrato_api.py` genera `frontend/src/api/esquema.ts` desde `web/api_contract.py`, y
  `tests/test_contrato_api.py` detecta divergencias.
- **Espacio de trabajo** (`web/workspace.py`): entradas, opciones, salidas y obras sin aplicar de una sesión, con versiones y
  migración; lo no disponible y lo dañado se dicen en `AvisosDatos.tsx`.
- **Retención** (`web/retencion.py`, 062): cada 60 s comprueba si venció el plazo de 24 horas, cuya fecha persiste, y retira lo que
  no tiene referencias y pasa de siete días. Mantenimiento y admisión de trabajos son excluyentes: un trabajo pendiente la aplaza sin
  cancelarlo. Rechaza redirecciones, enlaces simbólicos y junctions; un enlace duro solo pierde la entrada de esa ejecución.
- **Arranque y cierre** (`web/__main__.py`, `web/cierre.py`, `web/runtime.py`): con el puerto ocupado reutiliza, reemplaza o cambia;
  registra cada cierre y avisa si el anterior cayó.

**Mapa de la API** (rutas de `web/app.py`, casi todas bajo `/api/workspaces/{id}/`; cuántas tiene cada una, en el catálogo):

| Familia | Para qué |
| --- | --- |
| Espacio (`inputs`, `inputs-auto`, `load`, `options`, `runs`, `no-disponibles`, `restaurar-copia`, `copia-datos`, `files`, `events`, `ws`) y `nube` | Cargar y custodiar la fuente, también desde la nube, y seguir los trabajos |
| Conversión (`feeders`, `convert`, `diagnose`, `reconstruct`, `catalog`, `system`, `estructura`, `lote`, `outputs`, `outputs.zip`, `vnr`, `source-scope`) | Convertir y descargar |
| `demanda` | Libros, máximas, clientes y curvas |
| `pf`, `powerfactory`, `cargas`, `obras`, `plano` | Proyectos, calibración, casos, estudios, obras y variaciones sobre el plano |
| `informes` | Informes, formularios y sus libros |
| `pide`, `vnr/estudio` y `/api/pit/` | PIDE, estudio de planeamiento, Estudio VNR y PIT |
| `digital-twin`, `modelos` | Gemelo, pronóstico y modelos en uso |
| `asistente`, `agente` | Órdenes, planes, revisión y monitor |
| Generales (`jobs`, `sistema`, `health`, `/api/nube/proveedores`, `/api/copia-datos/`) y la página | Trabajos, datos de la instalación y `frontend/dist` |
| `correo` | Vista previa, confirmación y diario de los envíos de informes |
| Fuera de `/api/`: `/nube/retorno` y `/nube/selector/{proveedor}` | Vuelta de OAuth y página del selector del proveedor |

**Interfaz** (`frontend/src`): pestañas Resultados, Cargas en DIgSILENT, Catálogo de parámetros, Sistema completo, Estudio VNR y Asistente.
«Cargas en DIgSILENT» sigue los pasos 1 · Proyecto, 2 · Alimentadores y calibración, 3 · Integración de nuevas, 4 · Obras y estudios
y 5 · PIDE. La web se prueba en el navegador real.

## Configuración por empresa

`config/perfil_empresa.json` (local, puede heredar de `config/perfiles/`): CRS de origen, patrón de SED de medición, forma de los
nombres, escala del diagrama, carpeta de DIgSILENT, fichas, centrales y el plano de los libros. Su esquema está en
`schemas/perfil_empresa_v1.schema.json`, y `perfil_esquema.py` lo valida sin bloquear. Sin perfil no se supone nada: el CRS se pide y
ninguna SED se excluye por su nombre (P13). Ver [`PERFIL_EMPRESA.md`](PERFIL_EMPRESA.md).

**Casos de prueba:** los nombres de empresas, clientes y proyectos de ejemplos, pruebas y documentos son casos de prueba del
conversor, no valores por defecto (072:RF-20).

## Informes (017, 063, 066)

El botón «Generar informe de factibilidad» prepara los casos, corre sus flujos y escribe el resultado sin otro paso: Word
(`informe_docx.py`), PDF e imágenes (`mapa_informe.py`) y, donde el perfil lo declare, el libro Excel (`libro_informe.py`). El informe
se arma con lo que guardaron calibración y obras al correr desde la web, nunca con una ejecución aparte.

- **Datos del solicitante:** de los PDF (`documentos_solicitud.py`), con OCR si hace falta. El formulario guardado es de una carga y
  se vacía al elegir otra; un cliente que no corresponde se avisa y queda como hueco (063:RF-48, RF-49).
- **Pérdidas y precio:** del libro de la empresa (`libros_informe.py`).
- **Libro del informe:** el plano de celdas va en el perfil; sin esa sección no hay libro (066:RF-2). Excel aplica el plan por COM,
  porque openpyxl pierde imágenes y gráficos al guardar, y después se relee y se comprueba. En el equipo de desarrollo,
  `Excel.Application` y `Word.Application` los puede responder WPS Office, aunque diga ser Microsoft.

## Estudio de planeamiento: PIDE y largo plazo (024, 030, 072)

Estado: **conectado a la web, sin aceptación real** (072 T3, T9 y T11 abiertas).

| Entregable | Horizonte | Casos | Salidas |
| --- | --- | --- | --- |
| Largo plazo | 20 años | Años 04, 08, 12, 16, 20 | Mercado, densidad, diagnóstico, alternativas, plan de obras, F01-F07 |
| PIDE | Años 04-07 | Alternativas con y sin proyecto | Fichas, costos, VAN, TIR, priorización, F08-F15 |

- **Años** (`estudio_planeamiento.py`): el estudio declara su año de presentación, cada 4 años; el año 00 es el anterior. Ningún año
  va fijo en el código.
- **Flujo:** caso base → proyección de mercado (`proyeccion_mercado.py`) → cada caso por año (`tools/pide_pf.py`, 030) → obras
  acumuladas → evaluación (`pide.py`, `pide_economia.py`) → entregables (`formatos_pide.py`, `informes_planeamiento.py`).
- **Costos públicos** (`costos_fuentes.py`, `metrados.py`): el SICODI está leído y cruzado por código. Falta el adaptador de módulos
  estándar de transmisión (T3). Cada costo lleva resolución, año y huella; no se mezclan ni llevan factores sin sustento.
- **Modelos:** el oráculo aporta el flujo; los evolutivos, las alternativas (`afinar_bancos_pide`); DIgSILENT confirma. El asistente
  orquesta los mismos pasos; los entregables históricos le sirven de corpus (`pide_dataset.py`, `ejemplos_pide.py`), nunca como verdad
  eléctrica.

## Asistente y su equipo (026, 027, 047, 061, 065, 067, 070, 076, 077)

Una orden recorre esto. Solo el rol `operador` ejecuta, y toda escritura espera confirmación:

```text
 Asistente.tsx ─► POST /asistente ─► carril «asistente»
                                       │
      interprete.py: Transformer (conf. ≥ 0,85) ─► Ollama (≥ 0,6) ─► «ninguno»: pregunta
                                       │           las reglas solo fijan ruta, periodo y número
                                       ▼
      plan.py + tareas.py ─► web/asistente_operacion.py ─► equipo.py ─► planes_guardados.py
                                       │
      consulta: responde · lectura: se ejecuta · escritura: botón ─► gobierno.confirmar
                                       ▼
      ejecutor.py: autorizar_peticion + validar_paso ─► HTTP a la propia API ─► trabajo normal
```

| Pieza | Fichero | Estado |
| --- | --- | --- |
| Intérprete, plan, tareas, salida validada; un modelo calibrado trae su umbral en lugar del 0,85 | `asistente/{interprete,plan,tareas,contratos_salida}.py` | conectado y probado |
| Requisitos y consultas de cada tarea | `web/asistente_{operacion,consultas}.py` | conectados; 070 T9 a T11 abiertas en la web real y DIgSILENT |
| Gobierno y permisos por rol | `asistente/equipo.py`, `web/equipo_api.py` | conectado y probado; sin uso real registrado |
| Ejecutor | `asistente/ejecutor.py` | conectado y probado; 026 T12 abierta en DIgSILENT |
| Orquestador del proyecto entero | `asistente/orquestador.py` | conectado; probado con dobles. Un clic confirma la lista de etapas que el operador ve antes |
| Planes guardados | `asistente/planes_guardados.py` | sobreviven a un reinicio: siguen pidiendo confirmación y nunca se reanudan solos |
| Monitor y vigilancia | `asistente/{observacion,vigilancia}.py`, `MonitorAgente.tsx` | conectados y probados |
| Conocimiento con citas | `asistente/{indice,reranker,evaluacion_rag}.py` | conectado: BM25 y vectores. Sin reranker adoptado por la evaluación sellada, queda ese orden. Las puertas de abstención medidas no se cumplen enteras (`cumple_todos: false` en `EVALUACION_ABSTENCION_047.json` y `_077.json`) |
| Lecturas del proyecto | `asistente/{lectura_proyecto,corpus_proyecto}.py`, `tools/mcp_conversor.py` | conectadas a `pregunta` y al MCP, solo lectura: con LLM local, todo salvo secretos, lo sellado y el examen humano; el MCP, restringido salvo `--datos-locales`. El corpus ampliado no se sirve hasta pasar su medición (077:RF-47) |
| Revisión por roles y evidencia | `asistente/{revision_roles,evidencias_web}.py` | conectadas y probadas con el transporte de Ollama simulado; sin revisión real registrada |
| Mejoras e internet | `asistente/{mejoras,internet}.py` | mejoras en rama aparte, nunca fusiona ni sube; búsquedas filtradas y registradas; activas en las dos ediciones, con la salida a internet apagada por defecto en producto (086:RF-22) |

**Lo que el equipo es:** `fuentes`, `fisica`, `coste` y `riesgo` son el mismo modelo de Ollama con otro prompt de sistema, no agentes
separados, y su revisión es documental (`autoriza_ejecucion=False`). Exige evidencias en `observacion/evidencias` del espacio, que se
custodian solas cuando un informe, un estudio, un PIDE o unas obras terminan bien.

**Con las specs 107 a 112:** el asistente prepara el correo de un informe, la publicación, el compartir, la importación y la
conexión de una cuenta, y deja en su panel una tarjeta con lo exacto que saldrá (`TarjetaOperador.tsx`). Lo envía, publica,
comparte, importa o conecta el clic del operador en ella, que el navegador manda por la ruta de siempre: el ejecutor solo lee la
nube y pide previas (`salidas_red.lectura_de_la_nube`), y un documento importado no prepara nada (070:RF-79 a RF-83). Hace
también el diagnóstico y el expediente del PIT: sube al espacio el libro de la red y la proyección que nombra la orden
(`/api/pit/entradas`) y pide el trabajo por las rutas del PIT; y crea el estudio del VAD y arma su empresa modelo por
`web/vad_api.py` (070:RF-86); y abre o cierra una maniobra en una variación del plano y la estudia, por `web/plano_api.py`,
sin tocar el caso base; y genera el benchmark anonimizado de la fuente TXT cargada con `tools/benchmark_anonimo.py`.

## Modelos (024, 026, 043, 045, 046, 060, 069, 075, 079, 085)

Un modelo «en uso» es el que apunta `promovido.json`. El registro (`model_registry.py`) guarda candidatos y decisiones, y
`asistente/modelos_en_uso.py` es lo único que lleva un candidato aprobado a ese puntero. Punteros leídos el 2026-11-04 en `output/web`:

| Modelo | Fichero | Para qué | Estado |
| --- | --- | --- | --- |
| Intérprete de órdenes | `asistente/{codificador_ordenes,afinado_ordenes,validacion_cruzada}.py` | Texto a tarea y datos | **provisional:** `prov-8fd8a405a322c80c` (`codificador_afinado_v1` sobre `multilingual-e5-base`, umbral 0,95), en uso desde el 2026-11-04 por decisión del usuario. **No pasa las puertas** y sigue rechazado (085:RF-26 a RF-33) |
| Transformer por caracteres | `asistente/transformer.py` | El anterior, y la carga de lo que esté en uso | `20261024-150042-37ce`, anterior en el puntero (acierto 0,981) en su prueba fija, sin fichero que lo respalde; 0,17 en la prueba sellada y deja pasar el 67 % de lo que no es una orden |
| Clasificador de informes | `asistente/clasificador.py` | Tipo y subtipo de documento | en uso: `20261024-150047-b3c4` (subtipo 0,987) |
| LLM por Ollama | `asistente/ollama.py` | Órdenes y revisor | en uso: `llama3.1:8b` (75,9 % en 54 órdenes, medido el 2026-10-24) |
| LLM alumno (QLoRA a GGUF) | `asistente/{llm_destilacion,llm_runtime}.py` | Modelo propio | **no activado:** el último candidato del registro quedó en `ERROR_ENTORNO` |
| Embeddings y reranker | `asistente/{embeddings,reranker}.py` | Recuperación | encoder solo por CLI; reranker en GPU, descargado tras cada respuesta |
| PINN/GNN del gemelo | `digital_twin/oraculo.py` | Grafo y cargas a V y θ, conjunto de 3 | en uso: `20261028-114528-e6f5` (mae 0,002435). Filtra candidatos; DIgSILENT decide. Exige GPU también para predecir: sin ella, error dicho (`SinGPU`) |
| PowerFlowNet con PyG | `digital_twin/adaptador_pyg.py` | Arquitectura alternativa | solo como referencia de `benchmark_fisico.py` |
| Flujo físico propio | `digital_twin/{flujo,motores_flujo}.py` | Comprobación sin pesos | conectado. Z-bus por defecto; Anderson, Newton, power-grid-model y OpenDSS con sus dependencias aparte (083) |
| GRU | `digital_twin/temporal.py` | Serie a reconstrucción un paso adelante, y multihorizonte para competir | conectada: entrena en cada trabajo |
| Pronóstico multihorizonte | `digital_twin/{pronostico,temporal_entrenamiento,series_causales,evaluacion_temporal,adaptador_neuralforecast}.py` | Compite ingenuo, estacional semanal, GRU, N-HiTS, TFT y PatchTST | conectado por la tarea `pronostico`. Deja candidatos con `promovido: false`: ningún pronóstico se pone en uso solo |
| Dataset y backtest de demanda | `pronostico_demanda.py`, `tools/pronostico_demanda.py` | Módulo único (089): descubre los libros en cada carga, limpia una copia, da cabecera, clientes y escaladas, elige entre perfiles y hace competir 11 modelos a 15 minutos con su puerta | por CLI, sin panel; no alimenta calibración ni obras. Sin modelos entrenados aún |

Ninguna de estas cifras se volvió a medir para este documento: las de los punteros son las que guardan sus ficheros.

**Aprendizaje:** `tools/construir_dataset_entrenamiento.py` arma el dataset y dice qué falta (043). «Reentrenar» desde la web registra
el candidato y lo pone en uso solo si el registro lo aprobó por sus puertas, incluida la comparación con el modelo en uso. Sin informes
reales en su prueba, el clasificador queda `BLOQUEADO_POR_DATOS`. `tools/aprendizaje_continuo.py` lleva el ciclo conjunto sobre
`training_coordinator.py` (050 abierta). Entrenar exige CUDA y una sola guardia de GPU para toda la máquina (071): sin GPU se dice el
error. Sin 200 órdenes humanas, `asistente/ordenes_maestro.py` dice qué conjunto decide la puerta (085).

### Contratos de aprendizaje corregidos (spec 060, 2026-11-01)

Corrigen lo que la auditoría de alumnos encontró, con los lectores, el coordinador y el registro que ya existían; no se añadió otro
servidor ni otro registro. La parada temprana y la calibración usan familias apartadas antes del ajuste, con sus identificadores
persistidos. Un warm-start exige la genealogía de lo visto, y si falta o contamina las reservas se ajusta desde cero. El corpus lleva
una copia verificada de su política. Las medianoches de la medición no se desplazan y cada error temporal dice su hoja y su fila. Los
modelos heredados se consultan con su versión y una advertencia, sin promoverlos ni cargar Torch. Evidencia en
[`CORRECCIONES_ALUMNOS_2026-11-01.md`](CORRECCIONES_ALUMNOS_2026-11-01.md).

## Gemelo digital (024, 045)

Cada acción nativa aceptada se captura (`digital_twin/integration.py`) como un episodio inmutable (`episode.py`, esquema v2 con los
cuatro casos) en el búfer (`buffer.py`). Lo que falta, es de otro proyecto o cambió a mano va a cuarentena sin repetir la acción
(`capture.py`). `contratos_fisicos.py` dice qué física representa el grafo y por qué rechaza una red, y `benchmark_fisico.py` comprueba
el dominio antes de inferir. Los escenarios corren sobre copias de proyectos importados y se borran al terminar
(`tools/escenarios_pf.py`).

## Optimización (025, 042, 044, 048, 052, 074)

| Técnica | Fichero | Dónde se usa | Estado |
| --- | --- | --- | --- |
| Escalera de obras | `escalera_optima.py` | Paso de obras, evaluada en DIgSILENT | conectada; enumeración por variantes |
| Búsqueda bayesiana (Optuna TPE) | `optimizacion_oraculo.py` | Optimización de «Con proyecto» | conectada; probada con doble. 052 T4 abierta |
| NSGA-II de Pareto, propio | `optimizacion_oraculo.py`, `digital_twin/evolutivo.py` | Igual | igual |
| Markov y Shapley, propios | `optimizacion_oraculo.py` | Igual | igual |
| GA y NSGA-II de bancos, propios | `digital_twin/evolutivo.py` | Propuestas del PIDE | conectados y probados |
| Evolución diferencial, reconfiguración y consigna | `digital_twin/evolutivo.py` | Solo `tools/evaluar_evolutivos.py` y pruebas | sin conectar a la web |
| MADRL (GATv2, PPO) y control con pymoo | `madrl_obras.py`, `madrl_politica.py` | Solo `tools/madrl_*.py` | **piloto sin entrenar en redes reales:** la fidelidad no pasa (074 T5, T7, T8) |
| **PNL (Pyomo e Ipopt)** | ninguno | Ninguno | **solo especificada** (048): Ipopt está en `external/solvers` y nada lo usa |
| **Optimización mixta** | ninguno | Ninguno | **solo especificada** (048) |

El oráculo solo ordena y filtra: **toda obra se confirma con DIgSILENT**.

## Pronóstico y evaluación (029, 044, 046, 089)

- **Crecimiento por alimentador** (`crecimiento.py`, 029): tasa desde la medición de cabecera; conectado.
- **Multihorizonte con cuantiles** (046): ver la tabla de modelos. Particiones por día y ventanas causales (`series_causales.py`),
  política predeclarada, pinball y cobertura (`evaluacion_temporal.py`).
- **Particiones y puertas** (`evaluacion_modelos.py`, 044): conectadas, también en la PINN. `verificar_top_k` exige la medición nativa
  completa, y decide si se acepta lo aplicado en la 052. Probado con un doble; en DIgSILENT es de la 044 T4.

## Operación comercial y entrega (086)

- **Ediciones** (`edicion.py`): las dos ofrecen las mismas funciones, también entrenar, el gemelo, la revisión por roles, las mejoras y
  `pregunta` (usuario, 2026-11-13: «nada debería estar apagado ni bloqueado»). El programa instalado siempre es de producto, y
  `CSG_EDICION` solo puede forzar «producto». Las funciones en beta llevan marca, activas por defecto, y el operador las puede apagar;
  el front pregunta en `/api/health` cuáles.
- **Salidas a la red** (`salidas_red.py`): cada una declarada con su interruptor, apagadas en producto. Una prueba recorre el código.
- **Candidato:** `config/entrega.json` es el único fichero que dice qué entra. `tools/comprobar_entrega.py` lo comprueba,
  `tools/construir_candidato.py` lo arma y `tools/instalar_candidato.py` instala, actualiza y vuelve atrás sin red. Ver
  [`MANUAL_INSTALACION.md`](MANUAL_INSTALACION.md).
- **Instalador:** `instalador/ConverterSmartGrid.iss`, por usuario y sin administrador. **Sin probar en una compilación real.**
- **Soporte:** `web/doctor.py` (qué falta y cómo arreglarlo), `web/soporte.py` (paquete sin datos del cliente), `registro_rotativo.py`
  y `web/copia_datos.py` con `tools/copia_datos.py`.

## PIT y VAD sobre el registro normativo (107, 108)

- **Registro normativo** (`registro_normativo.py`, `config/normativa/`): cada norma lleva su acto, título, URL, fechas, huella del
  texto leído, estado jurídico (`vigente_comprobada`, `modificada`, `prepublicada`, `no_verificada` o `derogada`) y sus relaciones.
  Cada regla lleva clave, valor, unidad, artículo o anexo, página y cita literal. El PIT y el VAD leen de aquí sus valores: ningún
  número de un área, una empresa o un periodo está en el código (107:RF-11). Una regla que falta o es ambigua se dice como motivo,
  sin suponerse.
- **PIT** (`pit/`): producto aparte del PIDE (107:RF-1), con su norma, horizonte, formatos y expediente, aunque comparte con él la
  red, los motores y los costos. Sus rutas van en un `APIRouter` propio (`web/rutas_pit.py`, `/api/pit/…`). El diagnóstico, las
  alternativas y el expediente son trabajos en cola: `engine` con el motor abierto, `powerfactory` con DIgSILENT. Lo que se puede
  comprobar antes de encolar (rutas, área, libro de la red y alternativas) da 422 sin encolar.
- **VAD** (`vad/`): estudio de costos con la empresa modelo eficiente, aparte del PIDE y del PIT (108:RF-1). Su registro vive en
  `<espacio>/vad/<id>/estudio.json` y nunca toca las carpetas de los otros dos. El armado (`vad/trabajo.py`) es un trabajo del carril
  `engine`, cancelable entre sistemas, por `web/vad_api.py` (crear el estudio y armar con el caso subido; 070:RF-86). El
  paquete se importa sin pandapower ni openpyxl, y cada submódulo tiene su capa.
- **VNR según la Guía** (RCD 232-2017-OS/CD; 108:RF-20 a RF-25): `tools/normativa/generar_guia_vnr_232.py` comprueba la huella
  del PDF y escribe, reproducible, la regla citada en `config/normativa/rcd_232_2017.json` y sus anexos en `config/vnr/`
  (equivalencias, códigos VNR y formatos; la tabla que es imagen sale por OCR y se coteja). `vad/vnr_guia.py` zonifica, adapta,
  codifica y valoriza (art. 17.2); `vad/vnr_estudio.py` lo corre sobre el inventario VNR-GIS y el SICODI, y `vad/vnr_formatos.py`
  escribe los formatos del Anexo 5. La pestaña «Estudio VNR» (`features/vnr/EstudioVnr.tsx`) lo encola por
  `web/vnr_api.py` como trabajo del motor. Una regla sin dato deja un hueco nombrado, nunca un valor inventado. El VNR real va
  a la TIR y a contrastar con la empresa modelo; el aVNR del VAD sigue saliendo de la empresa modelo.
- **La norma del PIT, desde el registro** (`pit/norma.py`; 107:RF-20): los años de la programación, el horizonte de las
  alternativas, el factor de potencia de las barras de MT y el umbral del N-1 se leen de la norma, no de la entrada; las reglas
  de la comparación se citan en el expediente. Sin la regla, el cálculo sigue como antes y lo dice.
- **Línea del VAD** (`vad/linea.py`; 108:RF-26): tras la empresa modelo encadena el modelo rural desde la red del espacio, el
  dimensionamiento, el costo estándar, los resultados, el PIDE, la calidad, la explotación, las tablas y los informes; cada paso
  sin entrada lo nombra. Orquesta adaptadores, y por eso es de esa capa.
- **Biblioteca normativa general** (`biblioteca_normativa.py`, `web/normativa_api.py`, pestaña «Biblioteca normativa»): el
  registro de la entrega más la capa del usuario, fuera del paquete, que añade normas o sustituye una del programa; actualizable
  sin perder las versiones anteriores. El asistente la lee por su API (`asistente/corpus_normativo.py`, 077:RF-78 a RF-80): una
  regla es un fragmento de su índice, la cita se comprueba contra la biblioteca y `consultar_norma` es una lectura más.
- **Forma oficial**: el PIT, el VAD y el PIDE se entregan con la forma de los formatos de Osinergmin, leída de la norma, y para
  cualquier distribuidora. La empresa sale del perfil (P13).

## Módulos regulatorios y de planeamiento sobre el mismo espacio (109:RF-25, RF-26; ADR-010, ADR-011, ADR-012)

Un solo conversor y una sola empresa por espacio: el VNR, el PIT, el VAD, el corto plazo, el PIDE y el largo plazo son
vistas de la misma red convertida y de los mismos libros de la empresa, no productos con sus propias cargas.

```
 Entrada de datos ──► conversor (TXT · MDB · VNR-GIS) ──► red del espacio (derivados/red.json, canonical.json)
                                                                  │
 Fuentes de la empresa (fuentes/: SICODI, PIT, VAD, TdR, PIDE,    │   cada módulo: compartidas del espacio
 perfil, catálogo, .pfd, medición, demanda…; por periodo y huella)│   + sus propias entradas + sus entregables
          │                                                       ▼
          ├──► VNR (Guía 232-2017) ──────────────► VNR real ──► TIR del VAD (LCE arts. 70, 71 y 77)
          ├──► VAD (empresa modelo, TdR) ◄──────── inversiones del PIDE (anualidad; DL 1208 y TdR del PIDE)
          ├──► PIDE y largo plazo ◄─────────────── lo que el VAD ya reconoce (sin duplicar; TdR del PIDE)
          ├──► PIT (Norma Tarifas, por área de demanda) ◄── perfil, demanda y proyección compartidas con el PIDE
          └──► corto plazo (obras en DIgSILENT; decisión de producto: escalera de obras de las specs 017 y 072)
```

- **Fuentes de la empresa** (`fuentes_empresa.py`, `web/fuentes_api.py`, `shared/ElegirFuente.tsx`): cada libro una vez, con su
  clase, su periodo y su huella; la nueva de su clase y periodo vigente y las anteriores conservadas. Cada módulo toma la
  vigente por defecto (`fuente_o_subida`), otra a elección o una subida, que queda para todos (ADR-010).
- **Red del espacio**: la carga deja la red convertida con su fuente, su empresa y sus alimentadores; el estudio VNR la usa sin
  pedir el inventario, y los módulos avisan si la empresa de la red no es la del perfil.
- **Matriz de vínculos** (`config/modulos/vinculos.json`): por módulo, compartidas, propias, entregables y lo que consume de
  otro, cada vínculo con su cita (registro normativo, artículo, evidencia de práctica con huella o decisión de producto). Una
  prueba la coteja con el registro (ADR-011). Los criterios del PIDE (RM 428-2017) siguen como proyecto y se dicen así.
- **Carril «red»**: lo que solo espera a internet no bloquea la entrada (ADR-012).

## Nube, selector único y correo (109, 110)

- **Cuentas** (`adaptadores/nube/`): Google Drive y OneDrive con OAuth 2.0, PKCE y `state` de un solo uso (`oauth.py`). El cliente
  OAuth lo registra el usuario con su cuenta ([`NUBE_REGISTRO_OAUTH.md`](NUBE_REGISTRO_OAUTH.md)) en `config/nube.json`, que no
  entra en git. El token de refresco va al cofre DPAPI del espacio, y el de acceso solo vive en memoria (`cuentas.py`). Se piden los
  permisos mínimos (`drive.file`; `Files.Read`, y `Files.ReadWrite` solo al publicar). Sin registro, la web dice «Sin cuenta
  conectada» y todo lo local sigue igual.
- **Copia fija**: un fichero traído de la nube se guarda con su huella SHA-256 y entra por el mismo camino que una subida
  (`web/nube_api.py` recibe `asignar_entrada` y `validar_entrada` de la web: no copia su lógica, 109:RF-4). Los vínculos comprueban
  versiones y traen la nueva solo con confirmación (`web/nube.py`).
- **Selector único** (109:RF-21 a RF-24): cada entrada de la web tiene un solo «Elegir archivo» (`FileDrop`), con el equipo como
  origen siempre y la nube solo con una cuenta conectada (`shared/origenes.ts`, `shared/nubeEntradas.ts`, `app/NubeEnEntradas.tsx`).
  Un tipo que la entrada no admite no se carga, y se dice su nombre y los tipos admitidos. Las salidas se guardan en una carpeta del
  equipo y, con cuenta, se publican también (`GuardarSalida`). El selector del proveedor corre en una página propia con su CSP
  (`web/nube_selector.py`); su token de acceso es transitorio y no se guarda en ningún sitio. La de la web no se relaja.
- **Correo** (`correo/`, `web/correo_api.py`): Gmail y Outlook con las mismas cuentas. La vista previa guarda un borrador y su firma
  SHA-256 (`borrador.py`). «Confirmar y enviar» manda esa firma, y el trabajo la recalcula con los adjuntos del disco: si no
  coincide, no sale nada (110:RF-4, RF-5). Cada envío reserva su clave en el disco antes de llamar al proveedor (`envios.py`), así
  que un doble clic no envía dos veces. Un envío «desconocido» nunca se reenvía solo: lo resuelve el operador (110:RF-9). El
  asistente prepara el borrador y lo deja en su tarjeta; lo envía el clic del operador. Su carril es `correo`.
- **Copia de los datos** (`web/copia_datos_api.py`, 086:RF-85 y RF-86): la previa dice lo que ocupará, lo libre y las copias que ya
  hay, sin escribir nada. La copia solo se encola confirmada, con progreso y cancelación.

## Plano de la red (111)

- **Identidad** (`plano_red.py`): cada barra, tramo, SED y maniobra va por su código de la fuente, con el nombre que le da el DGS
  (`dgs.nombre_en_pf`, sin copiar la regla). La revisión de la red es la huella de la ejecución de la fuente y de sus manifiestos de
  geografía: un resultado de otra revisión no se pinta.
- **Variaciones** (`variacion_plano.py`): un diario de ediciones con versión, guardado en `<espacio>/variaciones_plano/` con la
  escritura atómica (P6). La fuente, el DGS y la geografía nunca se escriben. Toda regla eléctrica vive en el servidor
  (`web/plano_api.py`, 111:RF-15): dos tramos solo se unen por un nodo o un equipo comunes, y un ajuste a un nodo cercano es una
  propuesta que se confirma.
- **Estudio** (`resultados_plano.py`): DIgSILENT si hay licencia y el proyecto está vinculado a la red que se ve; si no, el motor
  abierto sobre una copia derivada del modelo. El resultado dice siempre qué motor lo calculó (111:RF-17, RF-18). Un incumplimiento
  lleva texto, icono, valor y umbral, no solo color.
- **Página** (`pagina_plano.py`): Leaflet en lienzo, con capas encendibles y todos los vértices de la fuente. Va aislada como toda
  página generada (086:RF-21) y habla con la pestaña solo por `postMessage`, con un esquema cerrado. Sin la salida «teselas» no hay
  fondo, y se dice.

## Benchmarks anonimizados (112)

`benchmarks/` genera en local conjuntos de referencia que no revelan a la empresa: seudónimos, un trazado sintético por el grafo,
longitudes perturbadas y solo las columnas de una lista cerrada. `generar_benchmark` es la única vía de emisión: reproduce el
estudio, pasa el control de reidentificación con el manifiesto escrito y solo entonces publica con `os.replace`. La semilla de los
seudónimos se queda en el equipo.

## Paquetes sin sección propia

- `dominio/`: reglas y valores puros del dominio eléctrico, sin lectura ni escritura (002).
- `evaluacion_harness/`: la evaluación integral local; importarlo no carga modelos ni motores.
- `recursos/`: lo que viaja con el paquete sin ser código, como el Leaflet propio de las páginas generadas y las notas de
  versión.

## Calidad: qué lo comprueba

| Comprobación | Dónde | Qué evita |
| --- | --- | --- |
| Inventario | `tests/test_inventario.py` (009) | Un fichero sin índice, una herramienta sin `--help`, una función sin uso, un RF sin prueba |
| Trazabilidad de specs | `tools/estado_specs.py` (033) | `specs/README.md` y la tabla de `CLAUDE.md` distintos del estado real |
| Capas | `tools/arquitectura.py`, `tests/test_capas.py` (065) | Violaciones nuevas y deuda que crece |
| Contrato de la API | `tests/test_contrato_api.py` (065) | Front y API divergentes |
| Regresiones | `docs/regresiones/`, `comprobacion_*.py` (081) | Que un fallo real se repita |
| Línea base del DGS | `tools/linea_base_dgs.py`, una por fuente | Una reorganización que cambie el DGS |
| Suite | `tools/suite_por_tandas.py`; solo vale con las variables `CSG_*` y ninguna omitida | Una suite que pasa sin probar lo real |
| Aceptación nativa | `tools/powerfactory_acceptance.py`, `tools/accept_*.py`, `tools/sistema_web.py` | Lo que solo se ve en DIgSILENT real |
| Candidato | `tools/verificar_candidato.py`, `tools/trazabilidad_candidato.py` | Entregar con evidencia de otra revisión |
| Puerta de calidad | `tools/puerta_calidad.py`, sus ganchos y GitHub Actions (102) | Un commit o una subida con la suite en rojo; una subida a `main` sin la suite fresca |

## Deudas y trabajo sin integrar

**Deudas conocidas**

1. El flujo desequilibrado no cuadra hasta conciliar las fases con `plini`: en SM218, 292 de 306 cargas no cuadran (+28 % en cabecera).
2. Solo especificados, sin código: PNL y optimización mixta (048) y protecciones nativas (049).
3. El intérprete de órdenes en uso no pasa sus puertas (085), y el dataset sigue sin sus 200 órdenes humanas.
4. `web/services.py` sigue siendo un solo fichero enorme: su partición y la migración de paquetes siguen pendientes (002).
5. El instalador no se ha compilado de verdad, y faltan las corridas de la 086 en máquina limpia.
6. Quedan excepciones de capas; las reexportaciones de `web/sources/` las retira 002:RF-21.
7. La nube y el correo se prueban con un proveedor simulado (`tests/nube_simulada.py`); con una cuenta real hace falta registrar
   antes el cliente OAuth en `config/nube.json`.
8. La puerta corre la suite en una sola sesión hasta que su T20 compare uno, dos y tres procesos y mida el pico de memoria.

**En ramas, fuera de esta descripción** (anotadas el 2026-11-04; el 2026-11-16 ninguna de las tres existe ya: lo que traían se
integró o se retiró, y su estado está en `specs/README.md`):

| Rama | Worktree | Qué trae |
| --- | --- | --- |
| `entrega/087-conjunto` | `.worktrees/entrega-087q` | Spec 087, sin commit: transferencia y traslado, confirmación conjunta, costos con cita |
| `entrega/042-nivel-rebase` | `.worktrees/entrega-042e` | 042, sin medida en DIgSILENT; base de la 087 |
| `fix/088-q-desde-fp` | `.worktrees/q-fp-088` | Spec 088, sin commit: Q de cabecera desde el FP |

## Correcciones a versiones anteriores

Lo que este documento decía el 2026-11-02 y dejó de ser cierto. Se conserva literal porque las preguntas de la 076 y los conjuntos de la
077 citan estas frases: son contradicciones que anotaron, ya resueltas aquí, y sus filas siguen pendientes de revisar (090:RF-16).

| Decía | Hoy |
| --- | --- |
| `97 excepciones sobre` 210 módulos | Bajaron; la cifra vigente está en el catálogo |
| `**Tres carriles**` | Cuatro, con `control` |
| `Estado a 2026-11-02: **aprobada, sin implementar**.`, del planeamiento | Conectado a la web, sin aceptación real |
| `**Multihorizonte con cuantiles** (046): **solo especificado**` | Tiene código y va por la tarea `pronostico` |
| `Sin reranker`, del RAG | `asistente/reranker.py` existe; actúa solo si su evaluación sellada lo adoptó |
| N-HiTS, TFT, PatchTST | Solo especificados en la versión anterior; hoy, en `digital_twin/adaptador_neuralforecast.py` |
