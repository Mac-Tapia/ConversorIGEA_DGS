# Plan — Spec 108

Lee: `docs/constitution.md`, `specs/108-estudio-de-costos-del-vad/spec.md` y, para el contexto normativo de G0,
`D:/csg/G0_PLAN_MAESTRO/D/D_FILAS_BP.md` (BP-18), `D/MATRIZ_PIDE_NORMA_FORMULA_VARIABLE.md` y
`D/D_REFERENCIAS_NORMATIVAS.md` (filas 5, 6 y 7). Decisiones: `D:/csg/G0_PLAN_MAESTRO/G1_DECISIONES_RECOMENDADAS.md`,
punto 3, recogidas en «Decisiones (2026-11-14)» de la spec.

**Iteración 1: el anexo 6, el modelo georreferenciado rural.** El anexo 5 (modelo geométrico urbano, RF-6) se
planifica aquí, pero se implementa en una tarea propia y posterior (T13). Hasta entonces, la parte urbana de un
sistema se nombra como «sin modelar (anexo 5 pendiente)» y el estudio de ese sistema no se emite como completo.

## Contexto técnico

Hoy no hay ningún flujo VAD (G0, BP-18): solo comentarios que citan el TdR (`dgs.py:1328`, `model.py:110, 366`,
`metrados.py:43`) y la lectura del VNR y del SICODI de la RCD 184-2026. Lo que el anexo 6 necesita ya existe y se
reutiliza tal cual. Todo se comprobó leyendo el código en la revisión `51895566`:

| Pieza existente | Qué se usa | Cómo |
| --- | --- | --- |
| `src/convertersmartgrid/adaptadores/entrada/vnr/` (de f9) | `models/canonical.py` (`Section.geometry`, `length_m`, `conductor_code`, `feeder_id`; `Node`, `Transformer.sn_kva`, `Load`), `gis/geometry.py` (`coords_from_geojson`, `polyline_length_m`), `discovery/fingerprint.py` (huellas) | **Solo lectura**: se importa, no se modifica. Si falta algo, se pide a f9. |
| `src/convertersmartgrid/geography.py` | `build_geography`, `GeoLine`, `make_transformer`, `exigir_crs_origen` | Trazas cuando la entrada es TXT o MDB, y reproyección **solo** para los mapas (anexo 9), nunca para el modelo. |
| `src/convertersmartgrid/troncal.py` (spec 016) | `red_de`, `troncal`, `camino_y_ramales` | Troncal por el camino más largo y derivaciones (RF-5). |
| `src/convertersmartgrid/demanda_medida.py` | `maximas`, `Cabecera`, `curva_de_registros`, `reducir_curva`, `curvas_de_clientes`, `leer_suministros` | Curvas de cabecera y de clientes para la caracterización del anexo 4 (RF-4). |
| `src/convertersmartgrid/costos_fuentes.py` (spec 072) | `leer_sicodi`, `TablaCostos`, `FuenteCostos`, `valorar_obra`, `cruzar_codigos`, `exigir_ambito`, `partir_codigo_vnr` | Costo estándar de la red **dimensionada**, con la fuente anotada en cada elemento (RF-7, RF-9). Hoy `valorar_obra` solo la usa `tools/costos_cruce.py:79`. |
| `src/convertersmartgrid/metrados.py` (spec 072) | `metrados_de_lineas`, `valorar_metrados` | Metrado por código de la red dimensionada (RF-7). |
| `src/convertersmartgrid/oraculo.py` (spec 024/082) | `red_pandapower`, `validar`, `InformeOraculo` | Motor físico para el dimensionamiento, las pérdidas y el balance (RF-7, RF-8). Sin DIgSILENT. |
| `src/convertersmartgrid/libro_informe.py` (spec 066) | `ERRORES_DE_FORMULA`, el patrón de `comprobar_libro`, y `plan_del_libro` + `rellenar_con_excel` cuando hay libro modelo | Tablas A y B en Excel (RF-11). |
| `src/convertersmartgrid/pide_dataset.py` | El vocabulario de `estado_juridico` (`vigente`, `proyecto`, `pendiente`, `derogada`, `evidencia_tecnica`) | El registro normativo del VAD usa el mismo vocabulario (RF-9). Solo se lee. |
| `src/convertersmartgrid/perfil_empresa.py` | El perfil de empresa | Empresa, grupo, CRS de origen, sector típico, moneda: nada en el código (RF-13). |
| `src/convertersmartgrid/web/jobs.py` | `JobManager.submit(..., lane='engine')`, `JobContext` | El armado es un trabajo en cola, cancelable entre sistemas (P7). |

**Fuera del alcance de este plan, sin ningún cambio:** `web/services.py`, `pide_economia.py`,
`adaptadores/entrada/vnr/**` y `catalog_resolution.py` son del integrador f9. La ruta de la web, si se añade, va en
`web/app.py` y se pacta antes con f9 (decisión 6 de G1); no forma parte de ninguna tarea de esta iteración.

## Diseño por partes

Paquete nuevo `src/convertersmartgrid/vad/`, con funciones puras salvo la escritura de los libros. Los contratos
transcritos del TdR van en `config/vad/` (JSON versionados, con su cita), no en el código.

| Parte | Ficheros (nuevos salvo que se diga) | Cubre |
| --- | --- | --- |
| Registro del estudio: grupo, periodo, empresa y su carpeta en el espacio, aparte del PIDE y del PIT | `vad/__init__.py`, `vad/estudio.py` (`EstudioVad`, `crear_estudio`, `cargar_estudio`); se guarda en `<espacio>/vad/<id>/estudio.json` | RF-1 |
| Registro normativo: cada anexo, fórmula y parámetro con acto, versión, estado jurídico, cita (fichero, líneas), huella, moneda e IGV | registro común `src/convertersmartgrid/registro_normativo.py` (107 T1; un solo sitio, P5), usado desde `vad/` (`exigir_vigente`); `config/vad/tdr_vad_2026.json` | RF-9, RF-10 |
| Formatos del anexo 2: contrato por tabla y campo, con unidades y periodo; validación sin relleno | `vad/anexo2.py` (`validar_tablas`); `config/vad/anexo2_formatos.json` | RF-2, RF-3 |
| Caracterización de la carga (anexo 4): factor de carga, simultaneidad y curvas MT/BT | `vad/caracterizacion.py`, sobre `demanda_medida` | RF-4 |
| Modelo georreferenciado rural (anexo 6): trazas, longitudes y SED reales, hash de vértices, troncal y derivaciones | `vad/modelo_rural.py` (`armar_modelo_rural`, `hash_vertices`), sobre el VNR canónico o `geography` y `troncal` | RF-5 |
| Modelo geométrico urbano (anexo 5), **iteración posterior** | `vad/modelo_urbano.py`; `config/vad/anexo5_*.json` | RF-6 |
| Dimensionamiento de la empresa modelo con el motor físico: conductor, transformación y pérdidas | `vad/dimensionamiento.py`, sobre `oraculo.red_pandapower` y `oraculo.validar` | RF-7 |
| Costo estándar de la red dimensionada y referencia del VNR real | `vad/costos.py`, sobre `costos_fuentes.valorar_obra` y `metrados.valorar_metrados` | RF-7, RF-9 |
| COyM técnico (anexo 7), pérdidas estándar y balance de potencia y energía por sistema y tensión | `vad/coym.py`, `vad/balance.py`; `config/vad/anexo7_coym.json` | RF-8 |
| Entregables: tablas A y B con fórmulas, mapas de densidad (anexo 9) y manifiesto de fuentes con huellas | `vad/entregables.py`; `config/vad/anexo9_estructura.json` | RF-11 |
| Observaciones del regulador con su respuesta y lo que afectan | `vad/observaciones.py` (`<espacio>/vad/<id>/observaciones.json`) | RF-12 |
| Trabajo en cola y guion | `vad/trabajo.py` (`armar_empresa_modelo(ctx, ...)`, cancelable); `tools/vad_estudio.py` con `--help` sin DIgSILENT | RF-1, RF-5, RF-7, P7 |
| Universalidad | `tests/test_vad_universal.py` | RF-13 |
| Inventario del repositorio | `CODIGO_FUENTE.md` (se añade una fila por fichero nuevo, con «108») | spec 009 |

### Flujo del armado (iteración 1)

1. `crear_estudio` fija la empresa, el grupo, el periodo y la versión del TdR (RF-1, RF-9).
2. `exigir_vigente` comprueba en el registro normativo que el TdR del grupo y del periodo está `vigente`; si no, el
   estudio se puede calcular, pero queda marcado `no_conforme` y no se emite como conforme (RF-10).
3. `validar_tablas` revisa las tablas cargadas contra el anexo 2 y devuelve los huecos por tabla y campo (RF-2, RF-3).
4. `caracterizacion` saca las curvas y los factores del anexo 4 de la medición (RF-4).
5. `armar_modelo_rural` copia las trazas, las longitudes y las SED reales del VNR, con el hash de vértices de cada
   tramo, y marca la troncal y las derivaciones (RF-5).
6. `dimensionamiento` adapta el conductor y la potencia de transformación con el motor físico, sin tocar ningún
   vértice (RF-7).
7. `costos` valora la red **dimensionada** con el SICODI y `valorar_obra`; el VNR real va solo como columna de
   referencia (RF-7, RF-9).
8. `coym` y `balance` calculan el COyM técnico, las pérdidas estándar y el balance por sistema y tensión (RF-8).
9. `entregables` escribe las tablas A y B, los mapas y el manifiesto de fuentes (RF-11).

## Regla «VNR real ≠ red óptima de la empresa modelo» (RF-5, RF-7)

- El anexo 6 dice: «Se respetarán las trazas de las líneas de acuerdo a la situación existente» y «Se adecuarán las
  potencias de los transformadores de acuerdo a la demanda en el año base y su crecimiento vegetativo…» (anexo de los
  TdR modificado por la R033-2026, copia local `output/normativa_pide_20261025/textos/fb5341703a3c….txt`,
  líneas 1981-1990). La **geometría** del modelo rural es la real. El **equipamiento** (sección del conductor y
  potencia de cada SED) es el de la empresa modelo, y sale del dimensionamiento.
- El costo estándar es un objeto aparte (`CostoEstandar`). Solo se construye a partir de un `Dimensionamiento` con
  su huella. Si se intenta construir con el inventario VNR sin dimensionar, se lanza `VadError`, y una prueba lo
  fija. El costo del VNR real se informa en la columna «VNR real (referencia)», y nunca en la de «costo estándar».
- El modelo rural nunca simplifica, reproyecta ni redondea vértices. La reproyección a WGS84 solo se hace en la capa
  de mapas (anexo 9), con `geography.make_transformer`, sobre una copia.

## Registro normativo y estado jurídico (RF-9, RF-10)

`config/vad/tdr_vad_2026.json`, con una entrada por acto y por anexo, y cada entrada con: `acto`, `anexo`, `version`,
`estado_juridico` (con el vocabulario de `pide_dataset`), `url`, `fichero_local`, `lineas`, `sha256`, `fecha_lectura`,
`moneda` e `igv` (`incluido`, `excluido` o `sin_leer`). Lo que dice G0 a fecha 2026-11-14:

| Acto | Objeto | Estado jurídico en el registro | Pendiente |
| --- | --- | --- | --- |
| RCD 174-2025-OS/CD | TdR del Estudio de Costos del VAD, nov-2026 a oct-2030 y nov-2027 a oct-2031 | `vigente` (G0: «vigente_comprobada», texto leído) | Que el grupo 1 incluya a la empresa del caso se deduce de los considerandos; no se leyó en la parte resolutiva: **NO_VERIFICADO**, T2 lo comprueba en el anexo 1 |
| RCD 033-2026-OS/CD | Modifica los TdR de la 174-2025, a raíz de las reconsideraciones | `vigente` (G0: texto leído) | — |
| Anexo de los TdR, texto modificado por la R033-2026 | Anexos 1 a 9 (líneas 142-150 de la copia local) | `vigente` para lo citado | Los anexos 2, 4, 5, 6, 7 y 9 **no se han transcrito**: cada uno se lee y se transcribe en su tarea, con la cita |
| RCD 184-2026 | VNR y SICODI | Lo que ya registra `costos_fuentes` (`FuenteCostos.resolucion`) | — |

**No se inventa ninguna fórmula.** Un parámetro o una fórmula entra en el registro solo con su cita (fichero y
líneas). Una entrada con `estado_juridico` distinto de `vigente`, o con `igv: sin_leer`, hace que el estudio salga
`no_conforme` y nombre la entrada. Si el TdR cambia a mitad del estudio, el estudio conserva la versión con la que se
creó. Al registrar una versión nueva, el estudio queda `desactualizado` y se nombran las tablas y los cálculos que
dependen de las entradas que cambiaron.

## Decisiones

- **Un paquete `vad/` aparte, con su carpeta en el espacio.** Descartado: ampliar la 072 (PIDE) o la 010, como
  proponía G0 en BP-18, porque el VAD tiene otro grupo, otro periodo, otra norma y otros entregables. Mezclarlo con
  el PIDE es lo que RF-1 prohíbe, y la regla de no crear specs nuevas ya la levantó el usuario el 2026-11-14 («haz
  nuevos spec»).
- **Primero el anexo 6 rural; el anexo 5 urbano, después** (G1, punto 3). Descartado: los dos a la vez, porque el
  rural reutiliza las trazas reales que ya existen (spec 010 y el VNR), mientras que el urbano necesita un modelo
  geométrico por densidad que todavía no se ha leído.
- **Costos del catálogo SICODI con `valorar_obra` y `valorar_metrados`, con la fuente en cada elemento** (G1,
  punto 3). Descartado: el libro CAPEX de la empresa (la mediana de `pide_economia.costos_por_alternativa`), porque
  no es un costo estándar y porque `pide_economia.py` es de f9. También se descarta un costo por km supuesto: lo que
  no cruza se nombra y queda fuera del total, como ya hace `valorar_obra` (072:RF-16).
- **Dimensionar con el motor físico abierto (`oraculo`, pandapower).** Descartado: DIgSILENT en esta iteración,
  porque el VAD se arma por sistema típico completo, sin licencia y en cola. DIgSILENT sigue siendo la referencia de
  los estudios eléctricos de la 011 y la 017, que no se tocan. Un conductor sin `rline` o `xline` se nombra como hueco
  y no entra con 0 Ω (G0, observación sobre `optimizacion_oraculo.py:158-179`).
- **El hash de vértices se calcula sobre las coordenadas del VNR en su CRS de origen**, serializadas con `repr` de
  cada `float` y en el orden de la polilínea (SHA-256 por tramo). Descartado: hacerlo sobre WGS84, porque la
  reproyección cambia los últimos dígitos y el hash dejaría de probar la fidelidad.
- **Las tablas A y B, con fórmulas vivas.** Se reutiliza `libro_informe`: `ERRORES_DE_FORMULA` y el patrón de
  `comprobar_libro` para verificar, y `plan_del_libro` con `rellenar_con_excel` cuando el operador da el libro modelo
  del regulador. Si no hay libro modelo, el libro se escribe con openpyxl y fórmulas vivas. Descartado: escribir
  valores sin fórmula, porque H2 pide la fórmula de cada celda.
- **El vocabulario de estado jurídico es el de `pide_dataset`.** Descartado: uno nuevo, porque dos vocabularios para
  la misma idea acabarían divergiendo.
- **Sin cableado web en esta iteración.** El trabajo en cola queda listo (`vad/trabajo.py`) y se lanza desde
  `tools/vad_estudio.py`. Descartado: tocar `web/services.py`, porque es de f9.

## Comprobación contra la constitución

- **P2 Escala variable.** El modelo rural recorre los tramos de cada sistema con índices por alimentador
  (`Section.feeder_id`), construidos una vez. No hay ningún número fijo de alimentadores ni de sistemas.
- **P5 Una sola vía.** Las trazas salen del VNR canónico o de `geography`; los costos, de `costos_fuentes` y
  `metrados`; la física, de `oraculo`. `vad/` las llama y no copia su lógica.
- **P6 Independencia.** Un sistema que falla no invalida a los demás. El manifiesto del estudio dice OK o FAIL de
  cada sistema y se escribe siempre, también al cancelar.
- **P7 Nada largo en una petición.** `armar_empresa_modelo` corre en el carril `engine` y comprueba la cancelación
  entre sistemas.
- **P9 Datos.** El caso real (los datos de la empresa) se lee de una ruta local que dan las variables de entorno y
  nunca entra en git ni en las pruebas.
- **P10 Idioma.** Todo en español, con el porqué en los comentarios.
- **P12 La spec manda.** Cada prueba cita `108:RF-n`.
- **P13 Universal.** Empresa, grupo, CRS, sector típico, moneda y códigos vienen del perfil y de la entrada. La
  prueba de universalidad falla si `vad/` o `tests/test_vad_*` contienen el nombre o un código de una empresa.

## Estrategia de pruebas

- **Dos empresas sintéticas**, con perfiles distintos en CRS de origen, sector típico, moneda y prefijos de código.
  La red se sortea (`seed`): para el VNR se usan objetos canónicos sintéticos (`Section` con geometría GeoJSON y
  `Transformer` con `sn_kva`); para la vía TXT, `ExportSpec(seed=…)` en las dos disposiciones, solo donde se usa
  `geography`. Una tabla SICODI sintética, escrita con el formato que lee `leer_sicodi`, en `tmp_path`.
- **Hash de vértices**: para cada semilla y cada empresa, el hash de cada tramo del modelo rural es igual al del VNR
  de entrada. Una prueba negativa mueve un vértice 1e-9 y comprueba que el hash cambia y que el modelo lo rechaza.
- **Regla VNR ≠ óptima**: construir un `CostoEstandar` sin un `Dimensionamiento` lanza `VadError`. En una red
  sorteada con SED sobredimensionadas, el dimensionamiento cambia su potencia y no cambia ningún vértice.
- **Sin relleno**: una tabla del anexo 2 sin un campo, o con otra unidad, produce un hueco con su tabla y su campo, y
  no un valor.
- **Registro normativo**: un TdR `proyecto` o `pendiente`, o un `igv: sin_leer`, deja el estudio `no_conforme`. Un
  cambio de versión a mitad del estudio deja `desactualizado` con la lista de lo afectado.
- **Casos límite de la spec**: un sistema mixto (en la iteración 1, la parte urbana queda nombrada y sin modelar), BT
  sin geometría (los tramos se nombran y se excluyen del hash, sin inventar vértices), un cambio del TdR y una SED
  sin medición (el hueco se nombra; solo se asigna una curva si el anexo 4 transcrito lo prevé, y con su cita).
- **Sin DIgSILENT y sin datos reales en la suite.** El caso de prueba real (grupo 1) es una aceptación aparte (T14),
  con la ruta en `CSG_VAD_CASO` y el nombre de la empresa solo en el perfil local.
- Cada prueba cita su requisito: `"""108:RF-n — …"""`. Ficheros: `tests/test_vad_*.py`.

## Riesgos

- **Los anexos no transcritos pueden pedir datos que el conversor no tiene** (por ejemplo, estructuras o sector
  típico por tramo). Se detecta en las tareas de transcripción (T2 a T4). Lo que falta se nombra como hueco del
  anexo 2 y no se supone.
- **El VNR de f9 puede cambiar de forma** mientras corrige H1-H14. `vad/` solo depende de `models/canonical.py` y de
  `gis/geometry.py`, y la prueba del hash se rompería ante un cambio de la geometría.
- **El SICODI puede no cruzar con los códigos de la red dimensionada.** `valorar_obra` deja lo que no cruza fuera del
  total y lo nombra, y el estudio no se emite como completo.
- **El estado jurídico puede cambiar** (una nueva modificación del TdR). El registro tiene versión y huella, y RF-10
  impide emitir como conforme.
- **Que se presente como «modelo del anexo 6» algo que no lo es** (riesgo de BP-18). El manifiesto de cada estudio
  lleva la versión del TdR y el estado `conforme`, `no_conforme` o `desactualizado`, y nunca dice «aprobado»
  (fuera de alcance).
