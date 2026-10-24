# Plan — Spec 011

Lee: `docs/constitution.md` y `specs/011-estudios-sobre-la-red-calibrada/spec.md`.

Estado: aprobado (2026-10-11) · Fecha: 2026-10-11 (obras de mejora añadidas el
mismo día)

## Contexto técnico

Lo que ya existe y se reutiliza:

- `tools/cargas_pf.py`: `activar_proyecto`, `Alimentadores`, `crear_variacion`,
  `nombre_libre`, `variaciones_activas`, `variaciones_de_la_base`, `medir_estado`
  (cabecera, pérdidas y tensión mínima por alimentador), `diferencia` (con − sin),
  `error_inesperado`. Es la base de los guiones nuevos: se importa, no se copia (P5).
- `tools/ajuste_cabecera_pf.py`: graba el reparto en la variación del ajuste y da en su
  informe el `origen` de cada SED (`cliente` o `kva`). Es donde se marca el escalado. Su
  `diagnostico` es el de RF-67.
- `tools/run_one_study.py`: un proceso por estudio con límite de tiempo, y `LDF_RELAJADO`.
- `tools/pf_proyectos.py` y `src/igea_dgs/carpeta_pf.py` (spec 005): la lista de proyectos
  del usuario, que da el «otro proyecto» de RF-91.
- `src/igea_dgs/studies.py`: el catálogo `ESTUDIOS`. Los siete de RF-23 ya son `defendible`.
- `src/igea_dgs/dgs.py`, `_type_name`: el sufijo de tensión de los `TypLne`
  (`_22_9kV`), que las copias de RF-61 tienen que repetir.
- `src/igea_dgs/web/services.py`: `ajuste_ejecutar`, `cargas_ejecutar`, `pf_verificar`,
  que lanzan los guiones con `ctx.run_process` en el carril `powerfactory`.
- `src/igea_dgs/web/app.py`: la base del ajuste viene de `ajuste_job_id` (spec 007, RF-1).
- `frontend/src/components/CargasTab.tsx`: los pasos 1 a 3 (spec 008).
- `tests/fake_pf.py`: el DIgSILENT falso. Hoy activa las variaciones de forma global; hay
  que darle casos de estudio con sus propias variaciones y escenario, bibliotecas de
  tipos (proyecto, global y de otro proyecto) y `AddCopy`.

## Elementos de DIgSILENT por obra

Comprobado en `datascheme.db` de PowerFactory 2024 (builds 22.0.2 y 23.0.5) el
2026-10-11. Los métodos de la API (`AddCopy`, `GetGlobalLibrary`, activar un caso) no
están en ese esquema y se confirman en T1 con el manual y en la prueba real.

| Obra | Elementos | Atributos | Tipo que se copia |
| --- | --- | --- | --- |
| Banco de condensadores | `ElmShnt` en un `StaCubic` nuevo de la barra | `shtype`, `qcapn`, `ncapx`, `ncapa`, `ushnm`, `i_cont` | ninguno: `ElmShnt` no tiene tipo |
| Reconectador | `StaSwitch` en el cubículo del tramo; `ElmRelay` en el mismo cubículo con un bloque `RelRecl` | `aUsage='cbk'`, `on_off`, `rel_hasProt`, `rel_hasRecl`; `typ_id` del `RelRecl` | `TypRecl` (tipo del bloque de reenganche) si viene de otra biblioteca |
| Regulador de tensión | `ElmVoltreg` entre una barra nueva y el tramo | `typ_id`, `usetp`, `buss`, `busl`, `nntap1` | `TypVoltreg` (`Un`, `In`, `pcReg`, `ntapmax`, `ntapmin`) |
| Sección de cable | `ElmLne` de la troncal | `typ_id` | `TypLne` a la tensión del alimentador (`uline`, `sline`, `InomAir`) |
| Una terna más | `ElmLne` | `nlnum` | ninguno |
| Cambio de tensión | `ComFeedertool` (`iopt_volt`, `vold`, `vnew`, `pStartElm`, `iopt_link`, `pLinkingElms`) sobre `ElmTerm` de media y la de cabecera, `ElmLne`, `ElmTr2`, `ElmShnt`, `ElmVoltreg`; `ElmXnet` de la cabecera | `uknom`, `typ_id`, `ushnm`, `usetp` (p.u., sin cambio) | los crea la herramienta: `TypLne` (`uline`), `TypTr2` (solo `utrn_h`), `TypVoltreg` (`Un`) |
| Transferencia de carga | `ComBbone` (estructura de red); `ElmBbone.GetCompleteBbPath`, `GetTieOpenPoint` (referencia de Python §5.2.4); `ElmCoup`/`StaSwitch` (`on_off`); `ComLdf` | — | — |
| Capacidad del enlace | `ComTransfer` (`iopt_method`, `psel_elms`, `p_expElms`, `p_impElms`, `p_boundary`, `iLoad`, `iVolt`, `iSave`, `isScaleLod`); `ElmBoundary.AddCubicle`; `GetTransferCalcData`, `IsLastIterationFeasible` | — | — |
| Escalado (RF-18 a RF-20) | `ElmLod`, `ComLdf`, `ElmFeeder` | `ElmLod.i_scale`, `ComLdf.iopt_fls`, `ElmFeeder.i_scale` | — |
| Solo informar (RF-26) | `ComTieopt`, `ComVoltplan`, `ComBalance` | `iopt_rem`/`iopt_out`/`iopt_result`, `iopt_mode`, `outChangedElts` | — |

Por qué se copian los tipos: en DIgSILENT los tipos de la biblioteca no los graba ninguna
variación. Editar `uline` de un `TypLne` compartido para migrar un alimentador a 22,9 kV
cambiaría también ese conductor en «Sin proyecto» y en los demás alimentadores; con
`TypTr2.utrn_h`, la relación de transformación de todos los transformadores de ese tipo,
que dejaría la baja a una tensión imposible y el flujo sin converger. La copia es un
objeto nuevo que nadie usa hasta que la variación de la obra la asigna, y la asignación
(`typ_id`) sí la graba la variación.

## Métodos de la API comprobados (T1, 2026-10-11)

En `Help/PythonReference_en.pdf` (referencia de Python de PF 2024), en
`Help/UserManual_en.pdf` y en `Dgs/DGS_Documentation.pdf`, todos de la instalación local.

| Para qué | Método o atributo | Dónde |
| --- | --- | --- |
| Copiar caso, escenario o tipo **dentro** del proyecto | `DataObject.AddCopy(obj, partes_del_nombre…)` | ref. Python, `DataObject` |
| Copiar un tipo **desde otro proyecto** (RF-91, RF-92) | `DataObject.PasteCopy(obj)` → `(error, nuevo)`: «when source object(s) and target object are inside different projects» `AddCopy` no sirve | ref. Python, `DataObject` |
| Bibliotecas global y del proyecto | `Application.GetGlobalLibrary([clase])`, `GetLocalLibrary([clase])` | ref. Python §3 |
| Activar un caso | `IntCase.Activate()`, `Deactivate()` | ref. Python, `IntCase` |
| Escenario del caso | `IntScenario.Activate()`, `Apply()`; `Application.GetActiveScenario()` | ref. Python, `IntScenario` |
| Variaciones del caso activo | `IntScheme.Activate()`, `Deactivate()`, `NewStage()` | ref. Python, `IntScheme` |
| Maniobras | `ElmCoup` y `StaSwitch`: `Open()`, `Close()`, `IsClosed()` | ref. Python §5.2 |
| Elementos de un alimentador | `ElmFeeder.GetBuses()`, `GetBranches()`, `GetAll()`, `GetObjs(clase)` | ref. Python, `ElmFeeder` |
| Mover un cubículo a otra barra (regulador) | `DataObject.Move(obj)` sobre la barra nueva; `ElmTerm.GetConnectedCubicles()` | ref. Python, `DataObject`, `ElmTerm` |
| Camino de la troncal | `ElmBbone.GetCompleteBbPath(iReverse, iStopAtTieOpen)`, `GetTieOpenPoint()` | ref. Python §5.2.4 |
| Frontera temporal | `ElmBoundary.AddCubicle()`, `Clear()`, `Update()` | ref. Python §5.2.6 |
| Capacidad de transferencia | `ComTransfer.GetTransferCalcData()` → `(capacidad, iteraciones)`, `IsLastIterationFeasible()` | ref. Python §5.4.53 |
| Parámetros de un guion del operador (RF-28) | `ComDpl`/`ComPython`: `SetInputParameterInt/Double/String`, `SetExternalObject` (los de tipo objeto) | ref. Python, `ComDpl`, `ComPython` |
| Migración de tensión | `ComFeedertool` no tiene métodos propios: `Execute()` con `iopt_volt`, `vold`, `vnew`, `pStartElm`, `iopt_link`, `pLinkingElms`; el objeto de enlace es `ComLink` | manual §14.6.1; `datascheme.db` |
| Tipo de un interruptor `ElmCoup` | `aUsage`: `cbk` interruptor, `dct` seccionador, `sdc` seccionador bajo carga, `swt` interruptor de carga | DGS_Documentation, `$$ElmCoup` |

Lo que T1 cambia en el plan:

- **Copiar tipos de otro proyecto con `PasteCopy`, no con `AddCopy`.** La referencia lo
  exige cuando origen y destino están en proyectos distintos. `AddCopy` queda para las
  copias dentro del proyecto (casos, escenarios, tipos de la migración).
- **`ComFeedertool` no garantiza la baja de los transformadores**: el manual (§14.6.1,
  regla 7.d) dice que la herramienta para en el primario, pero «does not limit the
  selected 2-winding transformer type to the same secondary voltage». La comprobación
  posterior de RF-103 (baja y potencia iguales al original) es necesaria, no un adorno.
- **`StaSwitch` no tiene `aUsage` en PF 2024**: tiene `iUse` (entero; DGS_Documentation,
  `$$StaSwitch`, «Type of Usage»), y ni el manual ni la referencia dan sus valores. El DGS
  de hoy escribe `aUsage='cbk'` en los `StaSwitch` (esquema `pf21_dgs_1_8_4.json`), un
  atributo que PF 2024 no tiene: los equipos de maniobra del export quedan todos con el
  `iUse` por defecto. T15a escribe `iUse` en lugar de `aUsage`, con el valor de
  «Disconnector» que el usuario lea en DIgSILENT (pendiente).

Lo que T13 comprobó en `datascheme.db` y en las etiquetas de `localisation/en-GB/data.db`
de PF 2024 (2026-10-12), y cómo cambia el plan:

- **`ElmShnt.shtype`**: 0 R-L-C, 1 R-L, **2 C**, 3 R-L-C,Rp, 4 R-L-C1-C2,Rp. El banco es
  `shtype=2`. `qcapn` es la potencia de un escalón («Rated Reactive Power, C»); la total es
  `ncapa × qcapn`, como deja ComCapo sus bancos (spec 012). Regular por escalones (RF-72)
  es `iswitch=1` («Switchable») con la banda `usetp_mn`–`usetp_mx`; `ElmShnt` no tiene una
  consigna única. Solo maniobra si el `ComLdf` del caso tiene `iopt_asht` («Automatic tap
  adjustment of shunts»): el guion no lo cambia (lo eligen los estudios) y avisa.
- **`ElmVoltreg`**: `usetp`, banda `usp_low`–`usp_up`, `ntrcn` («Automatic tap changing»),
  `i_cont` (discreto), `nntap1`. Regula en el flujo con `ComLdf.iopt_at`; se avisa igual.
  Se conecta como `cargas_pf` conecta lo que crea (cubículo con `obj_id` y `obj_bus`, lado
  S 0 en la barra de origen y lado L 1 en la nueva), sin escribir `buss` ni `busl`.
  `TypVoltreg.pcReg` es el rango «(+/-)»; con los pasos a cada lado, la toma neutra
  (`nntap0`) es 0.
- **El reconectador no es un `ElmRelay` de tipo `TypRecl`**: `ElmRelay.typ_id` es un
  «Relay Type» (`TypRelay`), y `TypRecl` es el tipo del bloque de reenganche `RelRecl`,
  que va dentro del relé. Lo que leen la confiabilidad y la ubicación de reconectadores
  de DIgSILENT son las marcas del interruptor, `rel_hasProt` y `rel_hasRecl` (comprobado en
  DIgSILENT real con la spec 012). El guion pone el interruptor con esas marcas y, en su
  cubículo, un `ElmRelay` con un `RelRecl` del `TypRecl` elegido. Que DIgSILENT acepte un
  relé sin `TypRelay` con ese bloque lo confirma la prueba real (T19).
  Resultado de T19 (2026-10-24, Nasca por sistema, NA203): DIgSILENT deja crearlo, pero el
  flujo no se calcula («`ElmRelay`: missing type», «`RelRecl`: missing type», «Calculation
  not possible»), y «Con proyecto» quedaba sin converger. El guion deja solo el interruptor
  con sus marcas (RF-73 cambiado) y, si el operador eligió un tipo de reenganche, dice que el
  relé no se crea (RF-73b). Lo mismo confirmó que `aUsage='cbk'` del `StaSwitch` queda como
  `iUse=1` en PF 2024.
- **«Al principio del tramo»** es el extremo más cercano a la cabecera por la red del
  alimentador, no el cubículo con `obj_bus=0`: un tramo dibujado al revés en el export
  dejaría el reconectador o el regulador aguas abajo.
- **La troncal de la sección y de la terna (T14)** es la del N-1 (`tramos_troncales` de
  `estudios_pf`, RF-44). Se calcula siempre que haya una de esas obras, también con tramos
  indicados, porque RF-87 necesita saber cuáles no son de ella. Las `ElmBbone` que crea el
  cálculo se borran después de leerlas; las que ya había se quedan.
- **Uso de los equipos de maniobra en el DGS (T15a, RF-128)**: la nota de T1 de que
  `StaSwitch` no tiene `aUsage` la corrigió la spec 012 en DIgSILENT real (existe, «Switch
  Type»; `cbk` dejó `iUse=1`). El DGS escribe `aUsage` por la clase del export
  (`dgs.USO_POR_CLASE`): `SWITCH` → `dct` (seccionador), `SECTIONALIZER` → `swt`; igual en
  los `ElmCoup` de los puentes fundidos. Antes todos eran `cbk`, y un seccionador del export
  pasaba por interruptor también para la spec 012 (RF-35). Qué `iUse` deja `dct` en
  DIgSILENT lo confirma la prueba real (T19). La línea base de la spec 001 se regeneró
  (2026-10-12) tras comprobar que, sin este cambio, los 97 DGS eran idénticos a ella.
- **Las maniobras de la transferencia van en una variación temporal (T15c)**, además de
  restituirse a mano (RF-119, RF-120): con el escenario apagado, `on_off` y `outserv`
  irían a la etapa que grabe, que puede ser la de una obra o del operador. La variación
  temporal, como la de los optimizadores (RF-26), se borra al terminar cada caso, y la
  etapa que grababa antes vuelve a grabar. Cada barra del camino lleva la carga que
  cuelga de ella por el recorrido de la red del alimentador (también por el lado de baja
  de sus transformadores), sin cruzar el camino ni un interruptor abierto.
- **Opciones de `ComTransfer` (T15d)**: la localización de PF 2024 da sus etiquetas pero no
  sus valores. Se toman por su orden (`iopt_method=1` «Element selection», `iSave=0` «Do
  not save», `iLoad`/`iVolt=0` límite global), en `tools/transferencia_pf.py`, y los
  confirma la prueba real. Si `ComTransfer` falla, no tiene licencia o no da solución
  viable, la capacidad se calcula subiendo `scale0` de las cargas transferidas por
  bisección (`transferencia_pf.maximo_factor`), que en `fake_pf` da la misma cifra.
- **Guiones del operador en la web (T17b, RF-27 a RF-30)**: la validación de T18 vio que T8
  los dejó en `tools/estudios_pf.py --guion`, que trabaja con un caso por vez, y que la
  web no los lanzaba. El servicio lista los guiones en un trabajo del carril
  `powerfactory` y ejecuta el elegido una vez por caso, cada una en su proceso con el
  límite de los estudios; si en un caso devuelve error, lo informa y sigue con el otro.
- **Mover el cubículo dentro de la variación**: que DIgSILENT grabe el `Move` en la etapa
  (y lo deshaga al desactivarla) no se puede ver en `fake_pf`; lo confirma la prueba real.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| A. Lógica pura de los estudios: estudios ofrecidos, límites del perfil, violaciones, diferencia con − sin, violaciones nuevas, filas ordenadas de los dos ficheros | `src/igea_dgs/estudios_pf.py` (nuevo) | RF-23, RF-24, RF-32 a RF-35, RF-37 |
| B. Los tres casos: renombrar el original, copiar casos y escenarios, activar en cada caso sus variaciones, desactivar ajustes anteriores, caso ajeno, restaurar el caso activo | `tools/casos_pf.py` (nuevo) | RF-1 a RF-11, RF-46 a RF-50 |
| C. Dónde trabajan las specs 006 a 008 con los tres casos | `tools/ajuste_cabecera_pf.py`, `tools/cargas_pf.py` (llaman a `casos_pf`) | RF-51 a RF-55 |
| D. Fijas y escaladas: el ajuste marca `i_scale`; los estudios desactivan el escalado por alimentador y comprueban la cabecera | `tools/ajuste_cabecera_pf.py`, `tools/estudios_pf.py` | RF-18 a RF-22 |
| E. Guion de un estudio en un caso | `tools/estudios_pf.py` (nuevo) | RF-17, RF-25, RF-26, RF-31, RF-33, RF-36, RF-38, RF-49, RF-68 |
| F. Contingencias N-1 sobre la troncal | `tools/estudios_pf.py` | RF-36, RF-43 a RF-45 |
| G. Guiones DPL y Python del operador | `tools/estudios_pf.py` (modo `--guion`) | RF-27 a RF-30 |
| H. Lógica pura de las obras: modelo de cada obra y su validación, nombres de variación y de copias de tipo, igualdad de datos de un tipo, plan de cambios de la simulación | `src/igea_dgs/obras_pf.py` (nuevo); el sufijo de tensión pasa de `dgs._type_name` a `naming.py` para que lo usen los dos | RF-56, RF-59, RF-61 a RF-63, RF-69, RF-85 |
| I. Bibliotecas: leer los tipos de una clase del proyecto, de la global y de otro proyecto, con los datos de RF-94; leer barras y tramos de un alimentador; copiar un tipo a la biblioteca del proyecto | `tools/obras_pf.py` (nuevo, modo `--bibliotecas`) | RF-88 a RF-94 |
| J. Aplicar las obras: una variación por obra, activarla en sus casos, copiar tipos, crear o cambiar los elementos de cada obra, flujo por caso, desactivar la que no converge, comprobar que «Sin proyecto» no cambió | `tools/obras_pf.py` (modo `--aplicar`/`--simular`) | RF-57, RF-58, RF-60, RF-64 a RF-67, RF-71 a RF-87, RF-96, RF-97 |
| K. Web: obras guardadas en el espacio, lecturas de biblioteca y aplicación como trabajos del carril `powerfactory`; plan y trabajo de los estudios; ficheros descargables | `src/igea_dgs/web/services.py`, `src/igea_dgs/web/app.py`, `src/igea_dgs/web/workspace.py` | RF-12 a RF-16, RF-25, RF-39 a RF-41, RF-95 |
| N. Transferencia de carga: camino por `ComBbone`, pasos por seccionador y por nodo, viabilidad, restitución de maniobras, capacidad y margen del enlace con `ComTransfer` o por bisección, fichero | `src/igea_dgs/transferencia_pf.py` (nuevo: pasos, viabilidad, máximos, filas) y `tools/transferencia_pf.py` (nuevo: DIgSILENT) | RF-104 a RF-129 |
| L. Paso «4 · Obras y estudios» | `frontend/src/components/ObrasPF.tsx`, `EstudiosPF.tsx` y `TransferenciaPF.tsx` (nuevos), `CargasTab.tsx`, `api.ts`, `types.ts` | RF-24, RF-35, RF-42, RF-70, RF-88 a RF-95, RF-98, RF-104 |
| M. Índice y estado | `CODIGO_FUENTE.md`, `CLAUDE.md` | P12, spec 009 |

## Decisiones

- **Una obra nunca edita un tipo existente**: copia y asigna en su variación (RF-59,
  RF-60). Descartado: editar el tipo dentro de la variación, porque DIgSILENT no graba
  los tipos en variaciones y el cambio llegaría a todos los casos.
- **Los tipos de otra biblioteca se copian al proyecto** (RF-92). Descartado: apuntar al
  tipo de la biblioteca global o del otro proyecto, porque el proyecto dejaría de abrirse
  bien si el otro cambia o se borra.
- **El nombre de la copia de un tipo usa el mismo sufijo de tensión que el conversor**,
  movido a `naming.py` (P5: una regla, un sitio). Descartado: un sufijo propio de las
  obras, porque el mismo conductor a 22,9 kV saldría con dos nombres según lo creara el
  DGS o una obra.
- **La migración se hace elemento a elemento, no con `ComFeedertool`** (cambiado en T15,
  2026-10-12; el plan aprobado decía la «Voltage Change Tool» y preveía esta vía si no
  copiaba los tipos como pide la spec). El manual (§14.6.1.4) y las etiquetas de PF 2024
  muestran que no lo hace:
  - solo cambia el tipo de una línea si su tensión «no es compatible» con la nueva, con una
    tolerancia `vtol` del 30 % por defecto: de 10 a 12 kV dejaría las líneas con su tipo de
    10 kV, contra RF-82;
  - los tipos que crea los nombra la herramienta, no con el sufijo del conversor (RF-61);
  - exige un objeto de enlace cuya clase no es `ComLink` (en PF 2024 `ComLink` es el enlace
    de datos externos SCADA/OPC), y `iopt_link` no tiene valores documentados;
  - no garantiza la baja de los tipos de transformador (regla 7.d).
  El guion aplica lo que lista `obras_pf.plan_simulacion`: `uknom` de las barras de media y
  de la de cabecera, una copia por tipo de línea, de SED (solo `utrn_h`) y de regulador con
  `copiar_tipo` (nombre del conversor, original intacto, datos comprobados), y `ushnm` de
  los condensadores de media. Así lo aplicado es exactamente lo simulado. `ComFeedertool`
  sigue en `check_pf_license.py`, por si una versión futura lo hace utilizable.
- **La migración de tensión cambia la fuente y la barra de la cabecera, sin SET**
  (RF-86, RF-96 a RF-102). El DGS del conversor da a cada alimentador su propia red
  externa (`ElmXnet`) en su propia barra de cabecera (`dgs.py`, «una fuente por
  alimentador»), así que basta poner `uknom` nuevo en esa barra: la `ElmXnet` no tiene
  tipo y su consigna `usetp` está en p.u. Descartado: un transformador de SET nuevo
  (usuario, 2026-10-11: «no necesitamos una SET»). Si la barra o la fuente las comparte
  otro alimentador (un proyecto hecho a mano), la obra se rechaza (RF-102).
- **Los tipos de las SED los crea el sistema** (RF-83, RF-99, RF-103): uno por tipo
  original, con `AddCopy` en la carpeta `equip` del proyecto, cambiando solo `utrn_h`;
  `utrn_l` y `strn` quedan como en el original. Descartado: elegirlos de una biblioteca,
  porque el usuario quiere que se creen (2026-10-11) y rara vez existe uno con la
  potencia y la alta exactas.
- **Qué barras son de media al migrar**: las del alimentador con `uknom` igual a la
  tensión de origen (RF-85). Las de baja de las SED quedan como están, porque su tensión
  es otra. Descartado: decidirlo por el nombre de la barra (P13).
- **El regulador se intercala moviendo el cubículo del tramo a una barra nueva**, con el
  `ElmVoltreg` entre la barra de origen y la nueva. Descartado: partir la línea en dos,
  porque cambiaría las longitudes y el trazado GPS de la spec 010.
- **El escalado se marca en la variación del ajuste**, al grabar cada carga. Descartado:
  marcarlo al preparar los estudios, porque grabaría en la variación que estuviera
  grabando y el «Caso base» lo heredaría. Para los ajustes anteriores a esta spec, la
  preparación activa su variación como etapa de grabación y completa la marca con el
  `origen` de su informe.
- **Los casos se identifican por nombre y por una marca en su descripción**
  (`desc` = `igea-dgs:011:<rol>`), que distingue uno del sistema de uno ajeno (RF-10).
- **Un proceso por estudio y caso**, en serie, porque PowerFactory solo admite un proceso
  con el motor a la vez (medido en `run_one_study.py`). Descartado: un proceso para todo,
  porque un contingencias colgado se llevaría el resto (RF-40).
- **Leer las bibliotecas también es un trabajo del carril `powerfactory`** (P7): abrir
  DIgSILENT tarda más de un segundo. La web guarda la última lectura para no repetirla al
  cambiar de obra en el formulario.
- **La lógica sin PowerFactory va en `src/`, la que toca la API en `tools/`**, como en las
  specs 004 y 006: A y H se prueban con datos sorteados; el resto con `fake_pf`.
- **La transferencia de carga se calcula con el guion, no con un comando de DIgSILENT**
  (RF-104 a RF-121). Revisado el manual de usuario 2024: `ComTransfer` (§40.5) escala
  generación o carga entre regiones sin maniobrar, `ComBbone` (§41.3) puntúa solo la
  reposición del alimentador entero y `ComOmr` (§46.4) busca la secuencia de maniobras
  tras una falla. Ninguno da «cuánto y hasta qué seccionador». Se usa `ComBbone` con el
  criterio de estructura de red para obtener el camino entre los dos alimentadores
  (`ElmBbone`, su contenido y su punto de enlace), y sobre él el guion cierra el enlace y
  abre, paso a paso hacia la cabecera del que cede, cada seccionador y cada nodo,
  ejecutando el `ComLdf` en cada paso. Descartado: un `ComTransfer` por elementos, porque
  escala cargas en vez de moverlas de alimentador y no dice el punto de corte.
- **La capacidad del enlace usa `ComTransfer` en modo por elementos** (RF-122 a RF-127),
  en la configuración del seccionador viable más lejano: conjunto que importa = las
  cargas de la parte transferida; conjunto que exporta = las cargas del resto del
  alimentador que cede (bajarlas no limita nada del que recibe); frontera = un
  `ElmBoundary` temporal con el cubículo del enlace (`ElmBoundary.AddCubicle`), que se
  borra al terminar; restricciones solo sobre el que recibe y la parte transferida
  («Consider constraints only for selected objects»); salida «Do not save» (`iSave`);
  resultado con `GetTransferCalcData()` y `IsLastIterationFeasible()` (referencia de
  Python 2024, §5.4.53). `ComTransfer` es de las herramientas de transmisión y la
  licencia puede no cubrirlo: si falla por licencia, o no es viable, el guion sube la
  carga de la parte transferida por bisección con `ComLdf` hasta el primer límite, que
  da la misma cifra sin depender del módulo (RF-125). Descartado: usar `ComTransfer`
  para la transferencia entera, porque no maniobra y no dice el punto de corte.
- **Cómo se reconoce un seccionador en DIgSILENT** (RF-118, RF-128, RF-129). Hoy el DGS
  escribe todos los equipos de maniobra del export (`SWITCH` y `SECTIONALIZER` de
  `dataset.switching_by_feeder`) como `StaSwitch` con `aUsage='cbk'`, y en DIgSILENT no se
  distinguen. El DGS pasa a escribir `aUsage` según la clase: `SWITCH` como seccionador
  (`dct`, a confirmar en T1 contra los valores que admite `StaSwitch.aUsage`) y
  `SECTIONALIZER` como hasta ahora. Para los proyectos ya convertidos, el guion los
  reconoce por el número de equipo (`loc_name` = `eq_number`) contra la entrada cargada
  en el espacio, si la hay. Descartado: reconocerlos por el nombre, porque la forma de
  los códigos es de cada empresa (P13). Este cambio toca el DGS: suite completa con las
  tres `IGEA_*` y `TestParallelWorkers` (P1).
- **Solo los seccionadores del tramo troncal** (RF-118): el camino ya es la troncal de
  `ComBbone` (`GetCompleteBbPath(…, iStopAtTieOpen=1)` da solo la parte del que cede), y
  de él se toman los `StaSwitch` con `aUsage` de seccionador.
- **Las maniobras del cálculo no se graban**: el guion guarda `on_off` de cada interruptor
  que toca y lo restituye al terminar cada sentido, también si se cancela o falla
  (RF-119, RF-120). Con un escenario de operación activo, `on_off` iría al escenario; por
  eso el escenario del caso se desactiva durante el cálculo y se restaura, como en la
  spec 004.
- **El resultado por nodos (RF-113)** abre la rama en cada barra del camino moviendo el
  cubículo del tramo aguas arriba fuera de servicio (`outserv` del tramo) en lugar de un
  seccionador que no existe, y lo restituye igual que los interruptores.
- **Todos los estudios con el módulo de DIgSILENT que los resuelve** (usuario,
  2026-10-11). El N-1 (T7, RF-36, RF-43 a RF-45) usa `ComSimoutage`: uno propio en el
  caso, para no tocar las contingencias del operador, con un `ComOutage` por tramo
  troncal (`SetObjs`), `Execute`, y cada contingencia leída con la traza del módulo
  (`StartTrace`, `ContinueTrace` hasta el final, medir, `StopTrace`; ref. Python
  §5.4.30); el comando creado se borra al terminar. Descartado: sacar cada tramo de
  servicio en un bucle propio de `ComLdf` (la primera versión de T7), porque el
  resultado que se defiende es el del módulo de contingencias.
- **Los optimizadores corren en una variación temporal** (T6, RF-26). La localización de
  PF 2024 (`localisation/en-GB/data.db`) da las opciones (`ComTieopt.iopt_result`:
  «Change existing network», «Record to operation scenario», «Record to results only»;
  `ComBalance.storage`: «Create new Variation», «Change existing network…») pero no su
  valor numérico. En vez de apostar por uno, el guion fotografía interruptores y
  demandas, ejecuta en una variación temporal, lee la propuesta y lo deshace todo.
- **Ningún DPL de terceros** (búsqueda del 2026-10-11): solo los guiones del operador.

## Comprobación contra la constitución

- P2 Escala: se recorre cada alimentador marcado con `ElmFeeder.GetObjs`, nunca la red
  entera por alimentador; las pruebas sortean cuántos alimentadores, cargas, obras,
  tramos y tipos.
- P5 Una sola vía: lecturas de cabecera, flujo y variaciones de `cargas_pf`; el nombre de
  los tipos de `naming.py`; el diagnóstico de `ajuste_cabecera_pf`.
- P7 Nada largo en HTTP: plan y formulario síncronos (solo validan); bibliotecas, obras y
  estudios en el carril `powerfactory`, con progreso y cancelables.
- P9 Datos: pruebas con `fake_pf` y resultados sintéticos; la prueba real la hace el
  usuario.
- P10 Idioma: todo en español.
- P12 La spec manda: cada prueba cita `011:RF-n`.
- P13 Universal: límites de tensión y cargabilidad del perfil de empresa (claves nuevas
  `estudios.tension_min_pu`, `tension_max_pu`, `cargabilidad_max_pct`), tensiones de
  origen y destino de la migración del alimentador y del operador; ningún 10 ni 22,9 kV
  en el código.

## Estrategia de pruebas

- `tests/test_estudios_pf.py` (A) y `tests/test_obras_pf.py` (H): sorteadas, sin
  PowerFactory.
- `tests/test_casos_pf.py` (B, C): `fake_pf` con casos y escenarios por caso.
- `tests/test_estudios_pf_guion.py` (D a G): `fake_pf` con órdenes de resultados
  sintéticos, límite de tiempo, cancelación, guion con error.
- `tests/test_obras_pf_guion.py` (I, J): bibliotecas de los tres orígenes, copia y
  reutilización de tipos, cada obra, migración de tensión con un tipo compartido con otro
  alimentador (que no debe cambiar), obra que no converge, comprobación de RF-64.
- `tests/test_transferencia_pf.py` (N, lógica) sorteada, y
  `tests/test_transferencia_pf_guion.py` (N, `fake_pf` con dos alimentadores, un enlace,
  seccionadores en el camino y un límite que corta en un paso conocido; los dos
  sentidos; interruptores restituidos también al cancelar).
- `tests/test_estudios_pf_web.py` y `tests/test_obras_pf_web.py` (K).
- `tests/test_obras_estudios_front.py` (L), y `npx tsc --noEmit -p .` y `npm run build`.
- Regresión: `test_ajuste_cabecera*.py`, `test_cargas_pf*.py`, `test_verificar_pf.py`
  siguen en verde sin los tres casos; las pruebas del DGS siguen en verde tras mover el
  sufijo de tensión a `naming.py` (el DGS idéntico byte a byte, P1).
- No toca el lector: no hacen falta las dos disposiciones. Mover el sufijo toca el DGS:
  suite completa con las tres `IGEA_*`.

## Riesgos

- **Licencia de `ComTransfer` y de `ComFeedertool`**: no están en
  `tools/check_pf_license.py`. T1 los añade a su lista; la vía por bisección (RF-125) y la
  migración elemento a elemento cubren el caso de que la licencia no los incluya. Que el
  modo por elementos acepte solo cargas en los dos conjuntos lo confirma la prueba real.
- **Métodos de la API** (`AddCopy`, `GetGlobalLibrary`, leer otro proyecto sin activarlo,
  activar un caso, mover un cubículo): no están en `datascheme.db` y `fake_pf` no los
  valida. T1 los comprueba en el manual; la prueba real (T19) los confirma.
- **Activación por caso**: si `fake_pf` no imita bien que variaciones y escenario son de
  cada caso, las pruebas pasarían y la red real no. Se prueba en
  `test_fake_pf_variaciones.py` antes de usarlo.
- **Migración de tensión**: es la obra que más elementos toca. Un `TypTr2` de
  distribución sin copia a la tensión nueva deja la baja fuera de rango y el flujo sin
  converger; RF-67 la desactiva en ese caso y RF-64 detecta si alcanzó a «Sin proyecto».
- **Reconectador sin curvas**: se modela, pero no cambia ningún estudio de esta iteración
  (RF-74); su valor llega cuando haya fiabilidad y protecciones.
- **Cambio en las specs 006 a 008** (parte C): con los tres casos, el ajuste y las cargas
  cambian de caso; sus informes dirán en cuál se aplicaron.
- **N-1 sobre muchos alimentadores**: puede pasar del límite de tiempo; RF-40 lo deja como
  no terminado y sigue.
