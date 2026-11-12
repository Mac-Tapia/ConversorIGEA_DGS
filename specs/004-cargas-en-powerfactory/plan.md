# Plan — Spec 004

Lee: `docs/constitution.md`, `specs/004-cargas-en-powerfactory/spec.md` y la revisión del
módulo de cargas del 2026-10-08 (resumida en el contexto de la spec).

## Contexto técnico

- Web: `src/convertersmartgrid/web/services.py` (`load_update_plan`, `create_plan_*`, `apply_plan`,
  `lote_plan`, `apply_lote`, `pf_projects`), `web/load_batch.py` (custodia del plan),
  `web/app.py` (rutas), `web/jobs.py` (`run_process`).
- Lectura de Excel: `convertersmartgrid/loads.py` (`read_workbook`, demandas) y
  `convertersmartgrid/loads_create.py` (`read_create_workbook`, cargas nuevas). Hoy ambos cruzan
  con el modelo de la conversión (`build_plan`, `build_create_plan`).
- DIgSILENT: `tools/aplicar_lote_cargas.py`, `tools/apply_sed_loads.py`,
  `tools/create_sed_loads.py`, `tools/pf_proyectos.py`.
- Front: `frontend/src/components/LoteTab.tsx` y, en `Modules.tsx`, `LoadsTab` y
  `NewSedTab`.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| A. Lectura sin modelo | `convertersmartgrid/cargas_pf.py` nuevo: lee los dos libros (reutiliza `read_sheet` y `read_create_sheet`), valida cada fila por sí misma, pasa coordenadas a WGS84 con el CRS del perfil y arma el plan (JSON). Sin `build_model` ni `ws.dataset` | RF-1, RF-5 |
| B. Guion único | `tools/cargas_pf.py` nuevo: proyecto → por alimentador, demandas y cargas nuevas en **una** variación nueva con nombre libre; simular sin escribir; flujo final; informe. Recoge de los guiones actuales `_escribir_carga`, la relectura, `Diagram` y el dibujo | RF-3, RF-4, RF-6 a RF-18, RF-20, RF-21 |
| C. Carga nueva en DIgSILENT | En B: barra por nombre o la más cercana por GPS (haversine sobre `GPSlat`/`GPSlon` de las `ElmTerm` del `ElmFeeder`); tipo de línea de la fila o de una `ElmLne` de la barra; tensión de la barra, BT de la fila o de un `TypTr2` del alimentador; frecuencia del proyecto; la carga escrita con la función de RF-9 | RF-10 a RF-16 |
| D. Cancelación entre alimentadores | `JobContext.run_process(..., cancel_file=)`: al cancelar crea el fichero y espera a que el guion acabe; B lo mira entre alimentadores | RF-19 |
| E. Web | `services.cargas_plan/cargas_aplicar/cargas_simular` sin `require_loaded`; `load_batch` sin ejecución fuente; rutas `/lote/*` se conservan; se retiran `load-template`, `load-plan`, `create-*` y `plans/{token}/apply` | RF-1, RF-2, RF-5, RF-17 |
| F. Front | Una pestaña «Cargas en DIgSILENT»: proyecto → alimentadores → libro de demandas y/o de cargas nuevas (o una carga en formulario) → Simular → Aplicar; resultados por alimentador. Fuera `LoadsTab` y `NewSedTab` | RF-2, RF-17, RF-20 |
| G. Limpieza | Retirar `apply_sed_loads.py`, `create_sed_loads.py`, `aplicar_lote_cargas.py` y lo que solo ellos usaban en `loads.py`/`loads_create.py` (`build_plan`, `build_create_plan`, `select_conductor`…) si nada más lo usa | P5 |

| H. Demanda medida: lectura | `convertersmartgrid/demanda_medida.py` nuevo, con `python-calamine` (lee `.xls`, `.xlsx` y `.xlsb` con un solo lector, en Rust: abrir un `.xls` de 400 MB tarda ~1 s). Medidores por alimentador; índice de hojas de los libros de cabecera sin convertir filas; máxima por medidor con columnas por alias; suministros; clientes importantes en los dos formatos; cruce actual → anterior; Excel de salida; descubrimiento de suministros por contrato y ranking determinista | RF-22 a RF-38, RF-58, RF-59 |
| I. Demanda medida: web | `services.demanda_*`; libros por subida o ruta del servidor (carpeta para cabecera, suministros y clientes), guardados en el espacio; medidores y cruce de clientes en la petición (libros pequeños); máxima de cabecera como trabajo del carril `engine`, cancelable entre medidores; descarga del Excel | RF-23, RF-38, RF-39, RF-60, RF-61 |
| J. Demanda medida: front | Sección «Demanda medida» en la misma pestaña «Cargas en DIgSILENT» que las demandas en bloque y las cargas nuevas; suministros admite uno o varios libros y una carpeta sin nombre convencional | RF-22, RF-29, RF-36, RF-37, RF-40, RF-41, RF-61 |

## Decisiones

- Una variación por aplicación, no escenario: lo eligió el usuario (H3). La etapa de la
  variación graba también los cambios de demanda de cargas existentes. Descartado: un
  escenario por alimentador, que no pueden estar activos a la vez.
- Sin vuelta atrás automática por alimentador: lo que coincide se aplica, lo que no se
  omite y se informa (RF-7). Si el operador no quiere el resultado, desactiva o borra la
  variación. Descartado: deshacer el alimentador entero por una SED no encontrada.
- La coincidencia la decide DIgSILENT, no la web: la web solo valida el Excel. Así el
  módulo funciona con cualquier proyecto, venga de esta web o no.
- Coordenadas: el libro puede traer `Lat`/`Lon` (WGS84) o `CoordX`/`CoordY` en el CRS
  del perfil de empresa de la web; el guion recibe siempre WGS84.
- Un guion único (`tools/cargas_pf.py`) en vez de tres: los tres flujos eran lo mismo
  con distinta envoltura (P5).

- Demanda medida, lector: `python-calamine` en `requirements.txt`. Descartados `xlrd` +
  `pyxlsb` + `openpyxl` (tres lectores para lo mismo, y `xlrd` tarda decenas de segundos
  con un `.xls` de 400 MB).
- Demanda medida, hoja del medidor: código entero normalizado (sin mayúsculas, espacios
  ni `_-.`); si no hay, hojas `<código>_<sufijo>` con una sola magnitud cada una, unidas
  por fecha. Descartado el prefijo libre: `X1` encontraría `X10`.
- Demanda medida, alias de columna: genéricos en el código (nombres de los medidores,
  no de una empresa) y, si existe, `config/demanda_medida_alias.json` con los de la
  empresa, como `config/line_type_aliases.json` (P13).
- Demanda medida, cancelar: entre medidores; un medidor se lee entero.
- Demanda medida, el Excel de salida se arma con lo que manda el navegador (el
  resultado ya mostrado): sin estado guardado que se desfase.
- Cancelar la aplicación en DIgSILENT (parte D) no es error: el trabajo termina con
  el informe, que dice `cancelado` y qué alimentadores no se empezaron.
- Parte G: con la web en la vía nueva, `web/load_batch.py` (custodia del plan con
  reversión por alimentador, que la spec descarta) se retira con sus pruebas.

## Comprobación contra la constitución

- P5 una sola vía: un guion y un lector para uno o varios alimentadores.
- P7: simular y aplicar son trabajos del carril `powerfactory`.
- P13: sin 22,9 kV, 0,22 kV ni 60 Hz fijos; el CRS de `CoordX`/`CoordY` sale del perfil.
- P11: sin DIgSILENT no se prueba en real; el guion se prueba con un DIgSILENT simulado
  (como `tests/test_load_batch_powerfactory.py`) y la prueba real la hace el usuario.

## Estrategia de pruebas

- Lector: libros sorteados con varios alimentadores, filas con error, coordenadas en los
  dos sistemas; sin dataset cargado en el espacio.
- Guion: objetos de DIgSILENT simulados (`ElmLod`, `ElmTerm` con GPS, `ElmLne`,
  `IntScheme`…) para cada RF de B y C: coincidencia, omisión, ambigüedad, modo de carga y
  relectura, barra por nombre y por GPS, tipo de línea, tensiones, nombre libre de la
  variación, simular sin escribir, cancelación entre alimentadores.
- Web: rutas con un espacio sin entradas cargadas; el trabajo llama al guion con los
  argumentos esperados.
- Front: `tsc` y `build`; contrato de que no quedan llamadas a las rutas retiradas.
- Demanda medida: libros sintéticos escritos en la prueba (`.xlsx` con openpyxl; el
  lector es el mismo para `.xls` y `.xlsb`), con columnas en orden sorteado, medidor
  partido en hojas, registros vacíos, empate de máximos, los dos formatos de clientes y
  códigos número/texto. Con datos reales, `CSG_DEMANDA_DIR` apunta a la carpeta con las
  cuatro subcarpetas; sin ella, la prueba se omite.

## Riesgos

- La API de DIgSILENT no se puede ejecutar en las pruebas: un atributo mal nombrado solo
  aparece en la prueba real. Se usan los nombres que ya funcionan en los guiones actuales.
- Que la variación grabe los cambios de demanda de cargas existentes depende de
  DIgSILENT (manual, cap. 16: las etapas registran cambios de objetos existentes). Se
  comprueba en la prueba real; si no, la demanda iría en un escenario guardado.

## Ubicación antes de conectar (RF-72 a RF-80, 2026-11-12)

- `cargas_pf.py`: `ZonaAlimentador` con los nodos de media de un alimentador (nombre, lat, lon), su centro y su radio (la
  mayor distancia de un nodo al centro); `verificar_ubicaciones` mide cada fila con coordenadas contra la zona de su
  alimentador, deja en la fila su `ubicacion` (nodo, distancia, radio) y aparta las que quedan fuera con su error y sus
  `propuestas`. `CargaNueva` guarda `coord_x`/`coord_y` tal como se escribieron, para proponer sobre ellas y no sobre el
  GPS ya convertido. El tope es el radio del alimentador más otro radio (`MARGEN_ZONA`); el del perfil
  (`cargas_nuevas.distancia_max_al_nodo_m`) manda. Descartado un margen fijo en metros: dependería de la empresa (P13).
  Descartado el radio solo: en un alimentador corto rechazaba un cliente a un km, y un error de dígito mueve el punto
  cientos de km.
- Propuestas (RF-74): cada dígito que falta o sobra en la parte entera de X o de Y (insertar 0–9 en cada posición, o
  quitar uno), X e Y intercambiadas, y Lat y Lon intercambiadas. Se pasan a GPS de una vez con el CRS del perfil y se
  queda la que cae dentro de la zona más cerca de un nodo. Nunca se aplica: el error la propone y el operador decide.
- `web/services.py`: la geografía del alimentador sale del DGS con que se aceptó el proyecto (`_dgs_aceptados`, el
  `<alimentador>_geography.json` a su lado; en una red unida sin el suyo, la de la red entera, y se dice). Sin geografía,
  no se mide en la web y lo hace el guion (RF-75).
- `tools/cargas_pf.py`: sin `ubicacion` en la fila, `resolver_nuevas` arma la zona con las barras de media con GPS del
  alimentador y rechaza igual; la propuesta allí es solo Lat/Lon intercambiadas (el guion no tiene las X/Y). RF-76:
  `cambios_de_la_carga` compara la fila con la huella que deja `crear_carga` en `desc` de la carga (coordenadas, kW, kVAR,
  kVA, barra) o, en una carga de antes sin huella, solo con su GPS (la potencia leída depende del escenario y de los
  retoques del operador, y se sigue avisando con 014:RF-28); si algo cambió, la variación anterior va a
  `eliminar` de la resuelta y se crea de nuevo. RF-78, RF-79: la resuelta lleva el radio y la longitud de la línea;
  `_crearian` y `crear_carga` la dan, y el aviso sale al resolver, también al simular.
- Front (`CargasTab.tsx`): `ubicaciones_rechazadas` del plan junto al formulario de 3.2, con un botón que copia la
  propuesta en el campo, y en el plan del libro; la columna «Ubicación» de las cargas del plan y la línea en la conexión.
- Pruebas: `tests/test_cargas_pf_ubicacion.py`, sintéticas (un dígito de menos en Y, X/Y y Lat/Lon intercambiadas, un
  punto bueno, el tope del perfil, la reutilización con y sin cambios con `tests/fake_pf.py`). La fila real de SE0001 se
  comprueba en solo lectura con la geografía de PA217 del espacio del usuario; sus cifras no van a git.
