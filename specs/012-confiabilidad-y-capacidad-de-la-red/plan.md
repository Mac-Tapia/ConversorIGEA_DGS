# Plan — Spec 012

Lee: `docs/constitution.md`, `specs/012-confiabilidad-y-capacidad-de-la-red/spec.md` y el
plan de la spec 011, del que este reutiliza casos, guiones y pruebas.

Estado: aprobado (2026-10-11) · Fecha: 2026-10-11

## Contexto técnico

Lo que ya existe y se reutiliza (P5: se importa, no se copia):

- `tools/casos_pf.py` (011): los tres casos y activar variaciones por caso. La variación
  «Datos de confiabilidad» se activa con él en «Sin proyecto» y «Con proyecto» (RF-21).
- `tools/cargas_pf.py`: `activar_proyecto`, `Alimentadores`, `crear_variacion`,
  `nombre_libre`, `error_inesperado`.
- `tools/estudios_pf.py` (011): un estudio en un caso, en su proceso; `Foto` (fotografía y
  restitución de interruptores y demandas), `_salida` (ventana de salida),
  `tramos_troncales` y el `ComSimoutage` propio del N-1, que las curvas PV reutilizan
  (RF-53). Los estudios nuevos entran como claves nuevas de su `ejecutar`.
- `src/igea_dgs/estudios_pf.py` (011): `estudios_ofrecidos`, `estudios_no_ofrecidos`,
  `Limites` y `limites_de_perfil` (RF-3), `diferencia`, `escribir_csv`, ficheros de
  resultados (RF-59).
- `src/igea_dgs/studies.py`: el catálogo `ESTUDIOS`, con `fiabilidad` (`ComRel3`) y
  `condensadores` (`ComCapo`) hoy bloqueados por `_TASAS_FALLA`, `_TIEMPOS_MANIOBRA`,
  `_PRECIOS` y `_COSTE_ENERGIA`.
- `tools/check_pf_license.py`: la lista de módulos de la licencia (RF-4).
- `src/igea_dgs/web/services.py`, `app.py`, `workspace.py`: trabajos del carril
  `powerfactory` y ficheros del espacio de trabajo.
- `frontend/src/components/EstudiosPF.tsx` (011, T17): la parte «4.2 Estudios».
- `tests/fake_pf.py`: el DIgSILENT falso de la 011, con casos, variaciones y escenarios.
- `openpyxl` ya está en `requirements.txt` (plantillas de cargas): leer y escribir el
  libro de la empresa no añade dependencias (P8).

## Lo comprobado en PowerFactory 2024 (2026-10-11)

En `datascheme.db` (atributos de entrada), `localisation/en-GB/data.db` (textos de las
opciones) y `Help/PythonReference_en.pdf` (métodos) de la instalación local.

| Para qué | Clase, atributo o método | Dónde |
| --- | --- | --- |
| Modelo de falla de líneas y cables | `StoTyplne`: `DnFr` (falla permanente), `RepMu` (reparación, h), `trans_ff` (falla transitoria, para MAIFI) | `datascheme.db`; manual §45.3.1.2 |
| Modelo de transformadores y de barras | `StoTyptrf`, `StoTypbar` (`DnFr`, `RepMu`) | `datascheme.db` |
| Asignar el modelo **al elemento** (RF-22) | `ElmLne.pStoch`, `ElmTr2.pStoch`, `ElmTerm.pStoch`, `ElmShnt.pStoch` | `datascheme.db` |
| Equipos de maniobra para la confiabilidad (RF-27) | `StaSwitch`/`ElmCoup`: `rel_hasProt` (despeja), `rel_hasRecl`, `Tswitch` (tiempo de maniobra), `iRestore`, `iNormOpenSwt`; `StaSwitch.iUse` (clase) | `datascheme.db` |
| Clientes (RF-24) | `ElmLod.NrCust`, que el DGS ya escribe | `datascheme.db`; `studies.py` |
| Confiabilidad | `ComRel3` (`iopt_mode`, `iopt_net`, `iopt_time`…); `AnalyseElmRes()` | ref. Python §5.4.37 |
| Aportes a los índices | `ComRelpost.CalcContributions(cargas)`; `GetContributionOfComponent(clase, 'ENS')` da el aporte **por clase** (líneas, cables, transformadores…), no por elemento | ref. Python §5.4.38 |
| Ubicación de reconectadores | `ComOpri`: `objective` (0 ENS, 1 SAIDI, 2 EIC), `locations` (interruptores o con protección), `excludedSwts`, `exclCableProt`, `nrOfRecl`, `maxNrPerFeeder`, `recResults` («Calculate results only», «Change existing network», «Save results in variation»), `variationName` | `datascheme.db`, `data.db` |
| Capacidad de alojamiento | `ComHostcap`: `objective`, `ioptLoads`, `ioptUsrLod` («Consider user-defined load selection»), `ioptIndFeeder`; `CalcMaxHostedPower(barra)` → `(código, P, Q, elemento que limita)`, con código 1 térmico, 2 tensión, 3 los dos | ref. Python §5.4.20 |
| Curvas PV | `ComPvcurves`: `pSel_Load`, `pSel_Busb`, `calcCont`, `pInputCont`, `results`; `FindCriticalBus(resultados)` | `datascheme.db`; ref. Python §5.4.34 |
| Condensadores | `ComCapo`: `feeder`, `iopt_meth`, `ecost`, `vmin`, `vmax`, `maxmvar`, y la tabla de bancos `shntqstep`, `shntmxsteps`, `shntswitch`, `shnttech`, `shntcost`, `shntignored`; `TotalLossCost()` | `datascheme.db`; ref. Python §5.4.7 |

Lo que **no** está en esas fuentes y se confirma en T1 y en la prueba real:

- **Nombres de las variables de resultado**: índices por carga (ACIF, ACIT, LPENS),
  índices por alimentador y aporte de cada elemento tras `ComRelpost`. Están en el
  manual (§45.2, §45.5.6), pero sin su prefijo de variable (`c:`, `b:`…).
- **Valores enteros** de `ComHostcap.objective`, `ioptLoads` y `ComCapo.iopt_meth`, y si
  `ioptUsrLod` restringe las cargas que crecen en el crecimiento conjunto (RF-45, RF-46).
- **Unidad de `DnFr` asignado al elemento**: el manual da «por km y año» en el tipo; que
  en el elemento se multiplique también por la longitud se confirma en T1.

## Lo que T1 confirmó (2026-10-11)

Con el manual (§45.2, §45.5.5), `datascheme.db` y `localisation/en-GB/data.db`:

- **Índices por carga y suma por alimentador.** Por carga, DIgSILENT da LPIF, LPIT, AID,
  LPENS y, ponderados por clientes, TCIF = ACIF·N y TCIT = ACIT·N (ec. 45.12 y 45.13).
  SAIFI = ΣTCIF/ΣN y SAIDI = ΣTCIT/ΣN (ec. 45.16 y 45.19). La parte C suma **TCIF, TCIT
  y LPENS** de las cargas del alimentador: es la definición del manual, no un cálculo
  propio. El prefijo de variable (`c:`) no figura en ningún documento local; el guion
  lee las variables por un único diccionario de nombres, y la prueba real (T13) lo
  confirma.
- **Aporte por elemento: existe, RF-32 se mantiene.** El manual (§45.5.5.2) colorea
  ramas, barras y cargas de media tensión según su aporte a la ENS, el SAIDI y el SAIFI,
  y `SetColours` tiene los rangos `C_ENS`, `C_SAIDI`, `C_SAIFI` y sus porcentajes `Cp…`.
  Hay, por tanto, una variable de aporte por elemento tras `ComRelpost`; su nombre exacto
  entra en el mismo diccionario de T13.
- **MAIFI**: el manual lo define (ec. 45.26) con las interrupciones momentáneas de cada
  carga; su variable por carga va en el mismo diccionario. Si no aparece en la prueba
  real, RF-30 informa MAIFI como «no disponible», no como cero.
- **Tasas en el elemento, por km.** El manual (§45.3.1.2) dice que en el modelo del
  elemento se introducen «as described above for the line type», es decir, por km y año:
  el guion escribe la tasa del libro tal cual, sin multiplicar por la longitud, y una
  prueba lo fija.
- **Opciones de `ComHostcap`** (`data.db`): objetivo «DER Capacity» o «Spare Load
  Capacity»; cargas «All loads simultaneously» o «Each load separately»; `ioptUsrLod`
  «Consider user-defined load selection», y el mensaje `msgloadssimulscal` («The
  following loads have been scaled simultaneously») confirma que esa selección es la que
  crece. El valor entero de cada opción no está en ningún fichero local: se usa el
  orden del diálogo (la primera, 0) y lo confirma la prueba real.
- **`ComHostcap` y `ComCapo` exigen sin escalado por alimentador** (`err_fls`: «Please
  disable 'Feeder Load Scaling'»). Ya es así en los estudios (011, RF-20).
- **`ComCapo` con varias redes externas** (`c_mextnet`): no puede tomar el coste de la
  energía de la red externa. El DGS da una por alimentador, así que `ecost` va siempre a
  mano, desde el libro (RF-15). Opciones: «Optimisation» o «Sensitivity Analysis»;
  «Report only» o «Install capacitors».
- **Curvas PV con contingencias piden licencia propia** (`ComPvcurves.cCntLic`: «No
  licence available to execute PV Curves Calculation with 'Consider contingencies'
  option»). RF-53 se trata como RF-4: si la licencia no lo cubre, la opción se lista
  como no disponible y las curvas se calculan sin contingencias.

## Lo que confirmó DIgSILENT (2026-10-12)

Sondas ejecutadas por el usuario en DIgSILENT 2024 (a su petición) sobre una copia de
`NA203_NA205_224027`, borrada al terminar. Sustituyen a las suposiciones de arriba:

| Punto | Resultado real | Qué hace el código |
| --- | --- | --- |
| Índices por alimentador | `ElmFeeder` da `c:SAIFI`, `c:SAIDI`, `c:CAIDI`, `c:ENS` (MWh/a), `c:MAIFI`, `c:ASAI`, `c:AENS` | se leen de `ElmFeeder`; la suma de `c:TCIF`, `c:TCIT` y `c:LPENS` de las cargas coincidió exactamente y queda como comprobación |
| Por carga | `c:LPIF`, `c:LPIT`, `c:LPENS`, `c:ACIF`, `c:ACIT`, `c:AID`, `c:TCIF`, `c:TCIT`; no hay MAIFI por carga | — |
| Aporte por elemento (RF-32) | tras `ComRel3`, cada línea tiene `c:C_ENS`, `c:CpENS` (%), `c:C_SAIDI`, `c:C_SAIFI`; `GetContributionOfComponent` devolvió 0 en todas las clases, y `ComRelpost.CalcContributions` devuelve 1 | se ordenan las líneas y transformadores por `c:C_ENS`; `ComRelpost` no hace falta |
| Despeje de fallas (RF-69) | sin interruptor en la cabecera, «No protection devices to clear the faults» en todas las fallas de línea; con un `StaSwitch` `aUsage='cbk'`, `rel_hasProt=1`, cerrado, en el cubículo del primer tramo, cero errores | el guion lo crea en la variación «Datos de confiabilidad» |
| `aUsage` de `StaSwitch` | existe y se escribe en PF 2024 («Switch Type»; `cbk` puso `iUse=1`). Corrige la nota de la 011 (T1) de que solo existía `iUse` | — |
| Candidatos a reconectador (RF-35) | los acopladores de SED del DGS son `ElmCoup` `cbk`; los equipos del export, `ElmCoup` `swt`. Con `locations=1` («con protección») y `exclCableProt`, `ComOpri` solo toma los que tienen `rel_hasProt=1` | el guion marca `rel_hasProt` solo en los candidatos de RF-35 y, además, los demás interruptores van en `excludedSwts` |
| `ComOpri` | `objective` 0 ENS; `recResults=2` crea y activa la variación con su nombre, graba en ella `rel_hasRecl=1` y `reclAttempts`; escribe «The ENS is reduced by X MWh/a (Before…, After…)»; **cambia la hora de estudio del caso** | se guarda y restituye `iStudyTime` y la etapa que grababa; la variación se borra |
| `ComHostcap` | `objective` 0 generación, 1 carga; `CalcMaxHostedPower` → `[código, P MW, Q, elemento]`, código 2 tensión; en carga, un nodo sin carga conectada devuelve `[1, 0, 0, None]` con «No relevant loads connected» (RF-72); 0,1 a 0,4 s por nodo | un resultado sin elemento es «no calculado», no un límite térmico |
| `ComPvcurves` | `frLoads=1` + `pSel_Load` (`SetSelect`) escala solo esas cargas; restituye las demandas; el `ElmRes` principal queda vacío (subficheros por contingencia) y `FindCriticalBus` no da nada sobre él; la ventana de salida da «Initial scalable demand… X MW», «Total critical demand… Y MW» y la tabla con la barra crítica, con coma decimal | se lee el resumen de la ventana de salida (manual §40.2.3.1) |
| `ComCapo` | `iopt_con=1` instala; dentro de una variación temporal, al desactivarla y borrarla no queda ningún banco; los nuevos tienen barra exacta (el informe de texto recorta el nombre); propone también en barras de baja de las SED; 24 s en un alimentador de 744 barras | variación temporal, `qcapn`, `ncapa`, `ushnm` de cada `ElmShnt` nuevo y `TotalLossCost()` |
| Clientes (RF-70) | todas las cargas con `NrCust=1` (por defecto de PowerFactory) | aviso por alimentador |
| Alimentador sin tensión (RF-71) | NA205 tenía su `ElmXnet` fuera de servicio: índices cero | se comprueba antes con el flujo |

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| A. Libro de la empresa: leer el Excel, validar hojas, filas y unidades, clases que faltan, anualidad de los bancos, plantilla descargable | `src/igea_dgs/datos_empresa.py` (nuevo) | RF-6 a RF-18, RF-62 a RF-66 |
| B. Catálogo: estudios nuevos en `studies.py`; las entradas de tasas y costes pasan a depender del libro cargado; módulos nuevos en la lista de la licencia | `src/igea_dgs/studies.py`, `src/igea_dgs/estudios_pf.py`, `tools/check_pf_license.py` | RF-1, RF-4, RF-19 |
| C. Resultados sin DIgSILENT: índices por alimentador a partir de los de cada carga, diferencias, ENS total, aportes ordenados, capacidad mínima y máxima, margen PV, informe de bancos, comprobación de estado, filas de los ficheros | `src/igea_dgs/estudios_red_pf.py` (nuevo) | RF-25, RF-30 a RF-33, RF-39, RF-47 a RF-49, RF-52, RF-56, RF-57, RF-59 a RF-61, RF-67, RF-68 |
| D. Datos de confiabilidad en DIgSILENT: variación «Datos de confiabilidad», modelos `Sto*` por clase y por tipo, asignación `pStoch` en los elementos, equipos de maniobra, comprobación de clase | `tools/confiabilidad_pf.py` (nuevo, modo `--aplicar-datos`) | RF-20 a RF-27 |
| E. Confiabilidad y reconectadores: `ComRel3` propio en el caso, lectura por carga, aportes por elemento, `ComOpri` con candidatos filtrados en una variación temporal | `tools/confiabilidad_pf.py`; claves `fiabilidad` y `reconectadores` en `tools/estudios_pf.py` | RF-2, RF-28 a RF-39 |
| F. Capacidad: `ComHostcap` nodo a nodo y conjunto, curvas PV por alimentador, `ComCapo` por alimentador en una variación temporal | `tools/capacidad_pf.py` (nuevo); claves `alojamiento`, `curvas_pv` y `condensadores` en `tools/estudios_pf.py` | RF-41 a RF-46, RF-50 a RF-58 |
| G. Web: subir el libro y guardarlo con el proyecto, plantilla, aplicar los datos como trabajo, opciones de los estudios nuevos, aceptar una propuesta como obra de la 011 | `src/igea_dgs/web/services.py`, `app.py`, `workspace.py` | RF-5, RF-6, RF-7, RF-20, RF-37, RF-40, RF-58 |
| H. Interfaz: libro de la empresa y estudios nuevos dentro de «4.2 Estudios» | `frontend/src/components/EstudiosPF.tsx`, `DatosEmpresaPF.tsx` (nuevo), `api.ts`, `types.ts` | RF-1, RF-7, RF-19, RF-37, RF-40, RF-45, RF-53, RF-58 |
| I. DIgSILENT falso: modelos `Sto*`, `pStoch`, `ComRel3` con resultados por carga, `ComRelpost`, `ComOpri`, `ComHostcap.CalcMaxHostedPower`, `ComPvcurves`, `ComCapo` | `tests/fake_pf.py` | pruebas de D, E y F |
| J. Índice y estado | `CODIGO_FUENTE.md`, `CLAUDE.md`, `docs/MANUAL_COMANDOS.md` | P12, spec 009 |

## Decisiones

- **El libro se valida entero antes de escribir nada en DIgSILENT** (RF-16, RF-17). La
  lectura y la validación son de `src/` y no abren DIgSILENT, así que la web las hace al
  subirlo y responde con los errores por hoja, fila y columna. Solo «aplicar» es un
  trabajo del carril `powerfactory` (P7). Descartado: validar dentro del guion, porque el
  operador esperaría a que abra DIgSILENT para enterarse de una celda vacía.
- **Un modelo `Sto*` por clase y uno por cada tipo con fila propia** (RF-10, RF-11), en
  una carpeta de la biblioteca del proyecto, con nombre `igea-dgs:012:<clase|tipo>`. Se
  asignan con `pStoch` en cada elemento **dentro de la variación** «Datos de
  confiabilidad» (RF-22). Descartado: asignarlo en el `TypLne`, que es lo que el manual
  sugiere para muchos elementos iguales, porque un tipo no lo graba ninguna variación y
  llegaría también al «Caso base» (la misma razón de la 011, RF-59). Crear un `Sto*` nuevo
  no modifica ningún tipo existente.
- **Un fichero nuevo reemplaza los modelos**, no los acumula (RF-23): se reescriben los
  `Sto*` con la marca y se reasignan; los que ya no tienen fila se borran.
- **Qué equipo despeja y cuál aísla sale de la clase escrita por la 011** (RF-26, RF-27):
  `StaSwitch.iUse` (T15a de la 011). Interruptor, reconectador y fusible:
  `rel_hasProt = 1`; reconectador además `rel_hasRecl = 1`; seccionador: `rel_hasProt =
  0`. Todos con `Tswitch` = tiempo de maniobra manual, salvo los telemandados del libro
  (RF-13). **Depende de la tarea T15a de la 011**: sin ella, RF-26 bloquea, que es lo que
  pide la spec.
- **Índices por alimentador a partir de los de cada carga** (RF-30). `ComRel3` da por
  carga TCIF, TCIT y LPENS (manual §45.2); por alimentador, SAIFI = ΣTCIF/ΣNrCust,
  SAIDI = ΣTCIT/ΣNrCust, CAIDI = SAIDI/SAIFI y ENS = ΣLPENS, con las cargas de
  `ElmFeeder.GetObjs('ElmLod')`. No es un cálculo propio de confiabilidad: es la suma que
  define el manual sobre los resultados del módulo. Si T1 encuentra los índices
  directamente en `ElmFeeder`, se leen de ahí y la suma queda como comprobación cruzada
  en las pruebas. Descartado: un `ComRel3` por alimentador, porque multiplicaría el
  tiempo por el número de alimentadores (P2).
- **Aportes por elemento con `ComRelpost.CalcContributions`** sobre las cargas de cada
  alimentador, leyendo el aporte a la ENS de cada elemento (RF-32). Si T1 no encuentra
  esa variable por elemento, la API solo da el aporte por clase
  (`GetContributionOfComponent`), y RF-32 se cambia en la spec (diff primero) en vez de
  improvisar un reparto.
- **`ComRel3` y `ComOpri` propios en el caso**, creados por el guion y borrados al
  terminar, como el `ComSimoutage` de la 011. Así no se tocan los comandos que el
  operador tenga configurados. Ajustes: análisis por flujo de carga, red de
  distribución, un único instante (RF-28, RF-29).
- **Reconectadores en una variación temporal** (RF-38): `ComOpri.recResults` = «Save
  results in variation», con un nombre libre. El guion lee en esa variación qué
  interruptores pasaron a `rel_hasRecl = 1` y la mejora del índice que escribe la ventana
  de salida («The ENS is reduced by…»), y borra la variación. Descartado: «Calculate
  results only» leyendo solo la ventana de salida, porque su texto de ubicaciones no
  identifica el elemento de forma estable. Candidatos (RF-35): `locations` =
  interruptores, y `excludedSwts` = un `SetSelect` con todo fusible y seccionador del
  alimentador. Así, aunque DIgSILENT los tome por interruptores, quedan fuera.
  `exclCableProt = 1` (RF-36).
- **Capacidad de alojamiento nodo a nodo con `CalcMaxHostedPower`** (RF-44, RF-47): por
  cada barra de media tensión del alimentador, una vez con objetivo de generación y otra
  de carga. Devuelve P, Q, el elemento que limita y el motivo, que es lo que pide RF-47.
  El coste es una llamada por barra y objetivo; lo acota el límite de tiempo (RF-5) y T1
  mide un alimentador real. Descartado: un único `Execute` con todo el alimentador como
  sitio y leer las barras del `ElmRes`, porque no da el elemento que limita de cada barra
  sin abrir los informes tabulares.
- **Crecimiento conjunto solo si DIgSILENT deja fuera las fijas** (RF-45, RF-46): con
  `ioptUsrLod` y un `SetSelect` de las cargas escalables (`i_scale = 1`, 011 RF-19). Si
  T1 muestra que esa selección no restringe qué cargas crecen, el modo no se ofrece.
- **Curvas PV por alimentador** con `pSel_Load` = las cargas escalables del alimentador y
  `pSel_Busb` = sus barras (RF-50, RF-51). Con contingencias (RF-53), `pInputCont` es el
  `ComSimoutage` de la troncal que crea la 011, y se borra al terminar. La barra crítica
  sale de `FindCriticalBus(resultados)`; las demandas inicial y crítica, del `ElmRes`.
- **Condensadores en una variación temporal** (RF-55): `ComCapo` con «Install
  capacitors» dentro de una variación creada por el guion. Se leen los `ElmShnt` nuevos
  (barra, kvar, pasos) y `TotalLossCost()` antes y después, y se borra la variación. Es
  el mismo patrón que la 011 usa con los optimizadores (T6). Descartado: «Report only»,
  porque la propuesta solo queda en la ventana de salida.
- **La anualidad la calcula `datos_empresa.py`, no DIgSILENT** (RF-64, RF-65): `ComCapo`
  recibe en `shntcost` el coste anual ya calculado, y el informe da los cuatro valores
  (RF-66).
- **Aceptar una propuesta crea una obra de la 011** (RF-40, RF-58): la web rellena el
  formulario de la obra «Reconectador» o «Banco de condensadores» con el elemento o la
  barra y los kvar propuestos, y el operador la aplica como cualquier obra. **Depende de
  T13 y T16 de la 011.**
- **El libro se guarda en el espacio de trabajo del proyecto**, con su nombre y fecha de
  carga (RF-20), nunca en el repositorio (P9).
- **Comprobación de estado al terminar** (RF-60, RF-61): se reutiliza la `Foto` de la 011
  (interruptores y demandas) y se añade la lista de variaciones del proyecto. Si algo
  cambió, se restituye desde la foto.

## Comprobación contra la constitución

- P2 Escala: cada estudio recorre los alimentadores marcados con `ElmFeeder.GetObjs`, un
  `ComRel3` para todos y no uno por alimentador; las pruebas sortean alimentadores,
  cargas, barras, equipos y filas del libro.
- P5 Una sola vía: casos y variaciones de `casos_pf`; límites de `estudios_pf.Limites`;
  ficheros de `escribir_csv`; N-1 de la 011 para las curvas PV.
- P7 Nada largo en HTTP: subir y validar el libro es síncrono (no abre DIgSILENT); aplicar
  los datos y cada estudio son trabajos del carril `powerfactory`, cancelables.
- P8 Entorno: sin dependencias nuevas (`openpyxl` ya está).
- P9 Datos: el libro de la empresa vive en el espacio de trabajo; las pruebas usan libros
  sintéticos y `fake_pf`.
- P10 Idioma: hojas, columnas y mensajes en español.
- P12 La spec manda: cada prueba cita `012:RF-n`. RF-32 se cambia en la spec si T1 lo
  exige.
- P13 Universal: las clases de elemento son genéricas y las tasas, tiempos y costes son
  de la empresa; nada de Electro Dunas ni de la NTCSE en el código.

## Estrategia de pruebas

- `tests/test_datos_empresa.py` (A): libros sintéticos con `openpyxl`, sorteados (filas,
  clases, tipos), cada error de RF-16 con su hoja, fila y columna, hoja que falta, clase
  que falta, anualidad con tasa y con tasa cero, y la plantilla leída de vuelta.
- `tests/test_estudios_red_pf.py` (C): sumas por alimentador contra valores calculados a
  mano, diferencias, ENS total, aportes ordenados, capacidad mínima y máxima, margen PV,
  bancos sin propuesta.
- `tests/test_confiabilidad_pf_guion.py` (D, E): `fake_pf` con dos casos; variación
  «Datos de confiabilidad» solo en «Sin proyecto» y «Con proyecto»; ningún tipo
  modificado; fichero nuevo que reemplaza; proyecto sin clases; candidatos sin fusibles
  ni seccionadores; variación temporal de `ComOpri` borrada; todos los `Sto*` a cero.
- `tests/test_capacidad_pf_guion.py` (F): `CalcMaxHostedPower` con un límite conocido por
  barra, crecimiento conjunto con y sin selección efectiva, PV con y sin contingencias,
  `ComCapo` sin bancos rentables, variaciones temporales borradas, demandas intactas
  (RF-60, RF-61).
- `tests/test_estudios_red_web.py` (G) y `tests/test_estudios_red_front.py` (H), con
  `npx tsc --noEmit -p .` y `npm run build`.
- Regresión: las pruebas de la 011 (`test_estudios_pf*.py`, `test_casos_pf.py`) en verde.
- No toca el lector ni el DGS: no hacen falta las dos disposiciones ni las `IGEA_*`, salvo
  la suite completa de cierre.

## Riesgos

- **Dependencias de la 011**: RF-26, RF-27 y RF-35 necesitan la clase de equipo (T15a);
  RF-40 y RF-58 necesitan las obras (T13) y su web (T16, T17). Las tareas de esta spec
  que dependen de ellas se ordenan después.
- **Variables de resultado sin nombre comprobado** (índices por carga, aportes por
  elemento): T1 las confirma en el manual y con `GetAttribute` en la prueba real; `fake_pf`
  no puede validarlas. Si RF-32 no tiene variable por elemento, se cambia la spec.
- **Tiempo de `CalcMaxHostedPower` barra a barra** en alimentadores con cientos de
  barras: lo acota RF-5; si la prueba real lo hace inviable, se plantea en la spec limitar
  los sitios a la troncal.
- **Licencia**: `ComRel3`, `ComOpri`, `ComHostcap`, `ComPvcurves` y `ComCapo` pueden no
  estar en la licencia de la empresa; RF-4 los lista como no disponibles.
- **Unidad de las tasas en el elemento** (por km o total): un error multiplica o divide
  las fallas de las líneas por su longitud. T1 lo confirma, y una prueba lo fija.
