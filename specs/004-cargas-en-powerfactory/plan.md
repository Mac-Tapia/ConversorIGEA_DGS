# Plan — Spec 004

Lee: `docs/constitution.md`, `specs/004-cargas-en-powerfactory/spec.md` y la revisión del
módulo de cargas del 2026-10-08 (resumida en el contexto de la spec).

## Contexto técnico

- Web: `src/convertersmartgrid/presentacion/web/services.py` (`load_update_plan`, `create_plan_*`, `apply_plan`,
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
  comprueba en solo lectura con la geografía de PA297 del espacio del usuario; sus cifras no van a git.

## Importar y diagnosticar un `.pfd` (RF-81 a RF-107, 2026-11-14)

- `tools/pfd_diagnostico.py` (T27), guion de DIgSILENT que corre en su propio proceso (`pf_arnes.GUIONES_EN_SU_PROCESO`,
  porque crea proyectos, como la aceptación). Reutiliza `carpeta_pf` (`asegurar_carpeta`, `nombre_libre`,
  `proyectos_de`, `alimentadores_de`, `validar_nombre`, `nombre_de_perfil`).
- Importación (RF-81, RF-84, RF-101): `ComPfdimport` creado en el usuario, con las propiedades que da la ayuda de PF 2024
  (Python Reference §5.4.31 para `GetImportedObjects`; User Manual §8.1.4.3 y los textos de atributos de
  `localisation/en-GB/data.db` para `g_file` «PFD file», `g_target` «New Path» y `activatePrj` «Activate project after
  import»). Se importa en una `IntFolder` provisional dentro de la carpeta del conversor, el proyecto se renombra con
  `<fichero>_<huella[:10]>` y el sufijo libre (`nombre_libre`), se mueve a la carpeta y la provisional se borra. Así un
  proyecto del `.pfd` con el nombre de otro existente no choca nunca.
- Huella (RF-82, RF-83, RF-101, RF-102): la marca `CSG_PFD:` en `desc` del proyecto guarda el sha256 del fichero, su
  nombre, la huella del diagnóstico (redes, casos, escenarios, variaciones, cargas por caso y recuento, sin el caso
  activo ni los avisos) y un resumen para comparar versiones. Reutilizar compara la huella del diagnóstico de ahora con
  la guardada; si difiere, avisa y diagnostica lo que hay. Una versión nueva (mismo nombre, otra huella) compara su
  resumen con el guardado en la marca de la anterior, sin activarla ni tocarla. Descartado comparar con la huella del
  inventario nativo (`native_inventory_evidence`): no ve P, Q, casos ni escenarios.
- Diagnóstico (RF-85 a RF-97): solo `GetContents` dentro del proyecto y de sus carpetas (`iopt_typ` `netdat`, `study`,
  `scen`, `scheme`, `lib`), `GetCalcRelevantObjects('*.ElmLod')` por caso y `ElmFeeder.GetObjs('ElmLod')`. Cada caso se
  activa uno a uno para leerlo y al final se vuelve al que estaba (RF-88, RF-100); nunca se desactiva un escenario.
  Lo que da una etapa (RF-91): un `IntSdel` («Delete Object» en `data.db`) es una baja de su `root_id`; un objeto con
  `root_id` («Original Location») es un cambio de ese objeto; uno sin `root_id`, un alta. Vigente en un caso (RF-92): su
  variación está activa en el caso, su `tAcTime` no pasa de la `iStudyTime` del caso y `IsExcluded()` no es 1; con tres
  o más vigentes de la misma fecha se avisa (regla medida en DIgSILENT: no aplica ninguna). Caso de referencia (RF-95):
  el activo al empezar o, sin él, el primero por nombre, y se dice cuál.
- Reducida (RF-97): un caso, ningún escenario y ninguna variación es lo que deja la exportación de una instantánea
  (User Manual §8.1.4.2).
- Salida (RF-98, RF-99): el JSON y el informe `.txt` se reescriben con `os.replace` tras cada sección, y en el `finally`
  con el error y la traza, para que un fallo a mitad deje lo leído.
- Pruebas: `tests/test_pfd_diagnostico.py` con `tests/fake_pf.py` ampliado (`ComPfdimport`, `IntSdel`, `root_id` de las
  copias de etapa, el caso que recuerda cada proyecto al activarlo), con nombres, cargas, casos y fechas sorteados.
- RF-109 y RF-110 (T28; `pfd_vinculos.py` con el inventario y la extracción de `pide_dataset`): EL SISTEMA vinculará el proyecto con los ficheros de su expediente cuando su
  contenido nombre sus casos, escenarios, alimentadores, SET o proyectos; y, por separado, cada vínculo llevará su
  evidencia (fichero, hoja o página y texto), sin que un nombre de fichero parecido baste.
- RF de T29 (a numerar con la tarea): CUANDO el operador suba un `.pfd` en la web, EL SISTEMA lanzará el diagnóstico en
  el carril `powerfactory`; y EL SISTEMA mostrará en la web el informe sacado del JSON de la corrida.
- Versión anterior (RF-103 a RF-107, T31): solo cuando `ComPfdimport` ya dejó el proyecto nuevo en la provisional,
  `ejecutar` renombra los proyectos vigentes de la versión anterior (los de la marca con el mismo fichero, otra huella
  y sin `anterior`). Si uno está activo, lo desactiva antes y lo avisa. Les pone `<fichero>…_anterior_<sha10>_<sello>`
  en 40 caracteres: se recorta el nombre del fichero, nunca el sufijo. A su marca le añade `anterior` (nombre previo,
  sello y huella de la versión nueva), para no renombrarlo otra vez con la versión siguiente. Después, el nuevo toma
  el nombre base. Si ese nombre lo ocupa otro proyecto, se usa el sufijo libre y se avisa (nunca se pisa). Si la
  importación falla, la versión anterior se queda con su nombre.
## Memoria de la búsqueda de máximas (RF-108, 2026-11-15)

- `demanda_medida.Cabecera`: los nombres de las hojas de cada libro se guardan al abrirlo; quedan abiertos solo los
  libros que caben en `LIBROS_ABIERTOS_MAX_BYTES` (128 MiB de fichero), y se cierra el usado hace más tiempo. Descartado:
  un libro abierto por medidor (reabrir un .xls de 490 MB cuesta ~2 s, y hay cientos de medidores) y leer los .xls por
  partes (python-calamine los lee enteros).
- `maximas`: ordena los medidores por el libro que leerá (`Cabecera.libro_de`, solo con los nombres de las hojas),
  empezando por el que siga abierto, y devuelve el orden pedido.
- `CurvaMedida` y `TensionesMedidas`: arreglos (`array`) que se recorren como la lista de tuplas y el diccionario; lo
  que no cabe sin cambiar de tipo (fechas con zona, enteros) se queda como venía. No se usa la `CurvaCompacta` de
  `pronostico_demanda` porque ese módulo importa este (capas).
- Pruebas: en `tests/test_demanda_medida.py`, sintéticas y sorteadas: el pico de tracemalloc con 4N medidores frente a
  N, los libros abiertos a la vez con el tope a cero y las clases compactas frente a la lista y el diccionario.
