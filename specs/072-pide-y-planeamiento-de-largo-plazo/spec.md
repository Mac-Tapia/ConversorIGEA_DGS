# Spec 072 — PIDE y planeamiento de largo plazo: dos entregables desde un mismo estudio

Estado: aprobada · Fecha: 2026-11-02 · Origen: petición del usuario

## Contexto y objetivo

El usuario, el 2026-11-02: «el PIDE en su metodología y criterios tiene dos entregables: un PIDE y otro planeamiento de
largo plazo; para esto hemos implementado los pronósticos, se traslada caso por caso de estudio por años; lo que todo se
hizo es un caso de año cero o caso base». Sobre el año: «sí se presenta en año 2027; recuerda que esto no debe ser fijo
porque se presenta cada 4 años». Sobre los costos: «el VNR y SICODI, como los módulos aprobados para PIT, son públicos;
están en la página de Osinergmin de cada empresa».

Hoy el conversor diagnostica por años y da una propuesta parcial de obras, pero no genera ninguno de los dos entregables.
La referencia son los entregables de Empresa B: `PIDE 2026` (4.1 largo plazo y 4.2 PIDE, año 0 = 2025) y `PIDE 2021`
(informes sucesivos). Sus cifras son referencia de forma y contenido, no verdad: tienen incoherencias propias (103
proyectos en ALT1 y 81 hojas de evaluación; años 02-07 frente a los 04-07 de la norma).

La norma de partida es RM 428-2017-MEM/DM, que `config/pide_universal_2017.json` marca como prepublicación: su vigencia se
confirma antes de citarla como obligatoria en un entregable.

## Usuarios / actores

Ingeniero de planificación de cualquier distribuidora, desde la web; el asistente, por las mismas rutas.

## Requisitos funcionales (EARS)

### Estudio y años

- RF-1: CUANDO se cree un estudio, EL SISTEMA pedirá el año de presentación y calculará de él el año 00 como el anterior a la
  presentación (art. 7.2). Ningún año irá escrito en el código: la presentación se repite cada 4 años.
- RF-2: EL SISTEMA calculará desde el año 00 los años de largo plazo (04, 08, 12, 16, 20; arts. 5.1, 9) y los de detalle del
  PIDE (04 a 07; art. 11.2), con el horizonte en la configuración de la metodología.
- RF-3: SI la medición que calibró el caso base no es del año 00, ENTONCES EL SISTEMA lo dirá y seguirá (030:RF-12).
- RF-4: EL SISTEMA generará los dos entregables desde un mismo estudio: el PIDE consume el largo plazo, no lo vuelve a calcular
  (arts. 5.1, 6.1).

### Fuentes de costos

- RF-5: EL SISTEMA leerá los costos por un único contrato de fuente, con adaptadores para SICODI (distribución), módulos
  estándar (transmisión, PIT) y libro CAPEX; cada costo declarará fuente, resolución, año, moneda y sector típico.
- RF-6: EL SISTEMA valorará las obras de distribución con SICODI y las de transmisión con módulos estándar, sin mezclarlos
  en un mismo elemento.
- RF-7: CUANDO valore un tramo, EL SISTEMA cruzará código de costo, tensión, estructura y sector típico; SI no cruza,
  ENTONCES lo nombrará y no le atribuirá un costo.
- RF-8: EL SISTEMA no aplicará factores sobre los costos oficiales salvo que el estudio declare el factor y su sustento.
- RF-9: EL SISTEMA guardará de cada fuente pública la URL de Osinergmin, su fecha de descarga y su huella, y usará el VNR
  aprobado de la empresa según su propia resolución de fijación.
- Aclaración de RF-9 (orden del usuario del 2026-11-19: «lo que no puede cerrar debe usar los archivos que descargaste de la página de Osinergmin del PIT, en los entregables; lo que publique o no Osinergmin u otras entidades no debería ser una limitación o exigencia para cierre»): las obras de transmisión se valoran con la base de módulos PUBLICADA vigente ya
  descargada (la de la Res. 152-2026-OS/CD, con su URL, fecha y huella). La resolución que la sustituya (la 181-2026-OS/CD)
  no es requisito: cuando se descargue entra como versión nueva por su huella, la anterior se conserva y lo valorado con ella
  queda marcado. La obra de una red real puede ser la de los formatos de inversión publicados de un PIT (F-301 y F-302),
  comparada elemento a elemento con su cifra publicada y con la causa de cada diferencia.
- RF-39: CUANDO el SICODI llegue como libro de cálculo (.xlsx, .xlsm, .xls o .xlsb), EL SISTEMA lo reconocerá por su
  contenido y leerá sus costos de inversión en la misma tabla que el zip, con su fuente, su huella y la columna de cada
  componente.
- Aclaración de RF-39 (usuario, 2026-11-14: el SICODI llega también como libro de cálculo del VAD vigente): las
  columnas se reconocen por su contenido y sus sinónimos, sin disposición fija; un componente en blanco o sin columna es
  «sin dato», nunca cero; si ninguna hoja trae los costos, el error nombra cada hoja con lo que le falta y lo que encontró.
- RF-40: EL SISTEMA reconocerá por su contenido cada hoja del libro del SICODI y devolverá lo leído con su hoja, su fila y
  la huella del libro, y una hoja no reconocida quedará en los avisos con su nombre y sus cabeceras.
- RF-41: SI una misma combinación de código, tensión, estructura y sector típico trae costos distintos en la fuente,
  ENTONCES EL SISTEMA no elegirá ninguno salvo que el elemento declare su subfamilia, y nombrará la ambigüedad.
- Aclaración de RF-41 (auditor 3e, 2026-11-14: «reconstruir, no bloquear»): si el elemento no declara la subfamilia, EL
  SISTEMA la deducirá de su tipo en el modelo canónico (tramo aéreo, subterráneo, de alumbrado, luminaria, SED) con una
  tabla universal, sin condiciones por empresa, y anotará cada valor así obtenido como «subfamilia deducida por el tipo»;
  la ambigüedad solo se nombra cuando el tipo no decide entre varias subfamilias.
- RF-42: EL SISTEMA ofrecerá el corto plazo, el PIDE y el largo plazo cada uno en su pestaña de la web, como el VNR, el
  PIT y el VAD, con su flujo de punta a punta: sus entradas y sus pasos, sus trabajos con su progreso, sus resultados, sus
  informes y sus salidas, y sus avisos. Cada pestaña reutilizará los pasos que ya existen en «Cargas en DIgSILENT», sin
  copiarlos, y esa pestaña seguirá entera. El PIDE dejará de ser beta en la 1.0.
- RF-43: (enmienda RF-29 y RF-42, orden del usuario del 2026-11-18) EL SISTEMA no repetirá en «Cargas en DIgSILENT» la
  elección del tipo de análisis: el corto plazo, el PIDE y el largo plazo tienen su pestaña, donde el tipo va fijo con su
  ficha, su norma y sus pasos. «Cargas en DIgSILENT» conserva todas sus secciones y sus ids, y el año de presentación
  sigue en su paso 5. Ningún otro control de la web llevará el nombre «Tipo de análisis» para elegir otra cosa.
- RF-44: (amplía RF-43, usuario, 2026-11-18) EN la pestaña de su módulo, EL SISTEMA titulará el recuadro del tipo con
  la etiqueta de esa pestaña (Corto plazo, PIDE o Largo plazo) también mientras llegan los tipos del servidor o si no
  llegan; nunca «Tipo de análisis».
- RF-45: (amplía RF-42, usuario, 2026-11-18) EL SISTEMA hará que el proyecto de DIgSILENT y sus alimentadores
  elegidos en el paso 1 de «Cargas en DIgSILENT», «Corto plazo», «PIDE» o «Largo plazo» sean del espacio: se
  guardan en él (sus opciones, con escritura atómica) y las demás pestañas los ven al momento, sin volver a elegirlos.
  En la matriz de vínculos de los módulos son una entrada compartida.
- RF-46: (enmienda el orden de 042:RF-54 y 087:RF-37; usuario, 2026-11-18: «haz lo recomendado») EL SISTEMA costeará
  cada alternativa de la escalera y del PIDE en este orden: el libro CAPEX real; después, el costo estándar de Osinergmin
  del SICODI vigente (por RF-5 a RF-9: leído por su sha256 y su vigencia, reemplazable por periodo, solo el costo exacto
  de RF-7 con el sector típico, la estructura y el código con su letra de tensión que declara
  `escalera.costos_osinergmin` del perfil); después, el del perfil; y lo que siga faltando se deducirá o se tomará de
  referencia, por confirmar, como hasta ahora (042:RF-54: ninguna obra queda sin solución). Cada costo dirá su origen
  (la resolución, el año, el código y la huella si es de Osinergmin). SI el SICODI está en otra moneda que la de
  trabajo, su unidad no es la de la alternativa (km o unidad) o falta su sector, su estructura o su fuente vigente,
  ENTONCES no se usará y el aviso dirá por qué.

### Mercado y años

- RF-10: EL SISTEMA proyectará la demanda anual con el método que gane contra lo ocurrido; la tasa de 029 será la referencia
  que debe superar. La spec 046 es de corto plazo y no alcanza estos horizontes; las variables exógenas son de la 031.
- RF-11: DONDE haya entregables históricos con datos, EL SISTEMA medirá el pronóstico contra lo ocurrido, sin mirar el futuro.
- RF-12: EL SISTEMA trasladará cada caso de estudio a cada año (030) y acumulará en cada año las obras de los anteriores.

### Continuación anual del corto plazo

Orden del usuario del 2026-11-07, ejecutada en P17 (2026-11-08): el PIDE es un
flujo propio, universal, después de los cuatro años del corto plazo (098:RF-37,
RF-39, RF-40). La 089 vigente excluye la proyección a años: una curva de 28 días
no acredita un horizonte anual y no se extrapola silenciosamente.

- RF-23: CUANDO se continúe el corto plazo, EL SISTEMA partirá de una copia del caso y escenario identificados por sus rutas completas, con las obras de corto plazo declaradas comprobadas activas.
- RF-24: EL SISTEMA usará en cada año únicamente una proyección anual aceptada con archivo y huella, modelo y evaluación identificados, cobertura del horizonte y P/Q por identidad completa de carga, sin sustituirla por una tasa cuando falte.
- RF-25: CUANDO un año incumpla los límites del perfil, EL SISTEMA comprobará las obras físicas declaradas para ese año y releerá el flujo después de aplicarlas; sin obra o sin solución lo dejará bloqueado.
- RF-26: EL SISTEMA copiará el estado con las obras del año anterior antes de evaluar el siguiente y registrará el primer año en que vuelven los problemas y las obras acumuladas.
- RF-27: CUANDO termine o falle el flujo anual, EL SISTEMA restituirá proyecto, caso, escenario y demandas originales, y no informará éxito si la relectura no lo confirma.
- RF-28: SI faltan identidad, proyección aceptada, unidad, datos físicos o conservación verificable, ENTONCES EL SISTEMA nombrará el faltante y no sobrescribirá estudios existentes ni inventará magnitudes o cumplimiento.

- Aclaración de RF-28 (P04, 2026-11-08): las nuevas lecturas CAPEX que alimenten cálculos conservarán
  la identidad SHA256 de los bytes realmente leídos, su ruta, hoja, configuración, unidades, escala y moneda
  declaradas y fecha de lectura en planes, resultados e informes persistidos. El recibo no acredita vigencia
  ni aprobación presupuestal; un dato no declarado queda explícito y una obra histórica sin enlace no recibe
  una procedencia retrospectiva. Se preservan costos, capacidades, ubicaciones, elecciones y fórmulas.

Contrato web de RF-18 y RF-23 a RF-28 (P17, 2026-11-08): el modo histórico
conserva sus entradas y comportamiento por defecto. El modo anual recibe tres
JSON del operador: perfil, evaluación y aceptación del corto plazo. Se conservan
los originales y sus SHA-256; un derivado del perfil cambia únicamente la ruta
de evaluación por la custodiada con la misma huella. Ninguna referencia anidada
subida se abre como ruta del servidor ni permite leer otro espacio. La petición
comprueba las fuentes e identidades antes de encolar, y el trabajo las relee
antes del controlador CLI común. El carril PowerFactory comunica cancelación
entre etapas y conserva el informe parcial con restitución verificada, también
si el proyecto objetivo difiere del inicialmente activo. La interfaz muestra
fuentes, faltantes, obras acumuladas y aceptación nativa pendiente; subir un
archivo no concede aceptación científica ni reemplaza una revisión humana.
- Aclaración de RF-24: una carga desequilibrada exige P/Q explícitas de sus fases r/s/t, con suma coherente con el total y unidades verificadas; su representación anual conserva la conexión y el modo físicos originales.
- Aclaración de RF-25 y RF-26 (T14, 2026-11-20; usuario, 2026-11-07: «en cada año del PIDE, la obra que pida el año, encima
  de las anteriores»): una obra es lo declarado para un año con la misma alternativa (sin ella, todo lo del año va
  junto, como una sección con su maniobra); las alternativas de un año van en el orden de la escalera (042:RF-56), y cada
  obra es candidata desde su año. En el año que incumple, EL SISTEMA probará, encima de las ya acumuladas, cada obra aún
  no puesta de ese año o de los anteriores, una a una y en su orden, y se quedará con la primera que cumple; la que no cumple se retira y sigue
  disponible para los años siguientes; SI ninguna sola basta, ENTONCES las probará juntas, y SI tampoco, el año queda
  bloqueado. El informe da de cada año las probadas, con su resultado, y la elegida. El punto de partida es el año en
  que el estudio de «Con proyecto» dijo que la de corto plazo vuelve a fallar (098:RF-39, RF-40), que trae su
  aceptación; EL SISTEMA lo comparará con el primer año que falla medido con la proyección aceptada y, SI difieren,
  ENTONCES lo dirá, sin bloquear. La proyección aceptada es la que emite la 031 (`tools/proyeccion_anual.py`), no el
  pronóstico a 28 días de la 089.

### Entregables

- RF-13: EL SISTEMA generará el informe de largo plazo con mercado, diagnóstico, alternativas, técnico-económico, plan de obras
  y los formatos F01 a F07.
- RF-14: EL SISTEMA generará el informe PIDE con alternativas, evaluación con y sin proyecto, VAN, TIR, costo anual, priorización
  y los formatos F08 a F15.
- RF-21: EL SISTEMA generará los entregables por módulos, un documento ligero por cada uno y con sus tablas y formatos del anexo,
  siguiendo su artículo paso a paso: del plan, el diagnóstico y la formulación de alternativas; del PIDE, la formulación en su
  periodo, la evaluación técnica, la económica, la priorización y selección, y la propuesta (usuario, 2026-11-02: «para que sea
  ligero los informes se haga por módulos y entregables»).
- Aclaración de RF-21 (orden del usuario del 2026-11-19: «lo que no puede cerrar debe usar los archivos que descargaste de la página de Osinergmin del PIT, en los entregables; lo que publique o no Osinergmin u otras entidades no debería ser una limitación o exigencia para cierre»): la aceptación de los dos entregables no espera la revisión de una empresa. Se compara la
  estructura de los módulos del conversor con la de los entregables oficiales custodiados (sus capítulos), en un acta con
  origen «maestro/revisor independiente» que dice qué módulo cubre cada capítulo y nombra como hueco el que no tiene
  sección.
- RF-15: EL SISTEMA generará metrados desde la red de cada proyecto; sin metrado no habrá costo supuesto.
- RF-16: SI un dato del entregable falta, ENTONCES EL SISTEMA dejará el hueco nombrado, sin inventarlo.
  Ampliado (H5, auditor b4, 2026-11-14): un dato que falta tampoco vale 0 en lo que se calcula con él. Una obra sin
  costo en el libro CAPEX lleva la inversión vacía y se prioriza tras todas las que tienen costo, con su aviso; nunca
  gana el desempate como la más barata ni deja sobredimensionada a otra. El costo anual (art. 14.4) solo se escribe si
  lleva la anualidad, el COyM y el costo de las pérdidas (`completo`); si no, «Costo anual US$» queda vacío en F09 a
  F12, con su hueco nombrado. El flujo privado sin COyM o sin CP conserva su VAN y su TIR con la marca de incompleto
  (`completo`, `falta` y el hueco de alcance en F09). Sin tipo de cambio (025:RF-68), F09 y F10 dicen «sin tipo de
  cambio» en vez de 0, y los huecos lo nombran. La evaluación con y sin proyecto no se hace si una obra aplicada no
  tiene costo.
- RF-17: EL SISTEMA tomará de un perfil de empresa todo lo propio de cada distribuidora; una fuente no alimenta a otra.
- RF-22: DONDE el perfil dé el COyM en % de la inversión (`escalera.coym_pct_anual`, el mismo dato de 025:RF-53), EL SISTEMA lo
  sumará al costo anual de cada obra con inversión conocida (024:RF-58) y lo escribirá en F10, F11 y F12; un grupo con alguna obra
  sin COyM queda vacío, con su hueco nombrado (RF-16). (Revisión de la 076, fila `formatos_pide-012`, 2026-11-03: la propuesta
  pasaba siempre el COyM vacío y la columna quedaba en blanco aunque el perfil lo diera.)
  Ampliado (H5, 2026-11-14): lo mismo para cada suma de F10 y F11 (demanda, energía, inversión, anualidad y costo
  anual): un grupo con alguna obra sin el dato queda vacío, no con la suma de las demás.
- RF-47: (auditoría PM-09 del Plan Maestro, 2026-11-19) EL SISTEMA, en cada peso y criterio del ranking del PIDE (los
  indicadores del art. 15.2 y los criterios del art. 15.3 con sus pesos del perfil) y en sus entregables (la propuesta,
  la hoja «Base normativa» del libro de formatos y el módulo de priorización), citará la norma con el estado legal que
  da el registro normativo (`config/normativa`), igual que el PIT y el VAD. Una norma `prepublicada` o `no_verificada`
  nunca saldrá como vigente: el entregable dirá «criterio de una norma prepublicada (sin vigencia comprobada)» o
  «heurístico, no conforme», con su motivo; lo mismo sin registro legible o fuera de la vigencia de la norma. La
  vigencia sale del texto de la norma, de su cláusula; solo si calla, del día siguiente de su publicación (art. 109 de
  la Constitución). La traza no cambia ningún número del ranking.

### Tipo de análisis en la web

Usuario, 2026-11-11: «desde la web se debe diferenciar si va a ser un análisis de corto plazo, el PIDE o el planeamiento de
largo plazo, según la normativa», «cada uno bien hilado y robusto», con los botones o pasos necesarios. Hasta ahora la web
llegaba a los tres por pasos sueltos (4 · Obras y estudios, 5 · Planificación PIDE) y un único «Planificar» escribía siempre
los dos entregables.

- RF-29: EL SISTEMA hará que el operador elija en la web, de forma explícita, uno de tres tipos de análisis: corto plazo,
  PIDE o planeamiento de largo plazo.
- RF-30: EL SISTEMA dará el horizonte de cada tipo desde la metodología y el perfil, sin años en el código: el corto plazo,
  del año 00 al periodo de corto plazo (098:RF-37); el PIDE, los años de detalle (art. 11.2); el largo plazo, los años de
  largo plazo (arts. 5.1 y 9); y, DONDE haya año de presentación, el año de calendario de cada uno (RF-1).
- RF-31: EL SISTEMA dará las obras que admite cada tipo según 098:RF-50: el corto plazo, solo las de implementación
  inmediata; el PIDE, las de su periodo empezando por la de corto plazo (098:RF-37); el largo plazo, además, las integrales.
- RF-32: EL SISTEMA dará los entregables de cada tipo: el corto plazo, los informes de estudio y de factibilidad (spec 017)
  con su libro (spec 066); el PIDE, los módulos de los arts. 11 a 17 con F08 a F15; el largo plazo, los de los arts. 6 a 10
  con F01 a F07; los artículos y formatos, los de la metodología.
- RF-33: EL SISTEMA mostrará los pasos de cada tipo en su orden, cada uno con su estado según los trabajos del proyecto y un
  acceso al paso de la web que lo hace, sin quitar ni duplicar ningún paso. El estado también sale de lo guardado en disco
  (calibración, cargas nuevas aplicadas, flujos de «Con proyecto», obras e informes), no solo de la sesión; y CUANDO los
  alimentadores marcados ya están calibrados, EL SISTEMA ofrecerá ir directo a 4.2 y a 4.4, sin ocultar los pasos 2 y 3
  (CA101_CHN102, 2026-11-13).
- RF-34: CUANDO se planifique como largo plazo, EL SISTEMA escribirá solo los módulos del plan de largo plazo.
- RF-35: SI se planifica como largo plazo con la aplicación de obras pedida, ENTONCES EL SISTEMA lo rechazará antes de
  encolar: el plan plantea las obras, no las aplica en «Con proyecto».
- RF-36: SI se planifica como PIDE o largo plazo sin año de presentación en la petición ni en el perfil, ENTONCES EL SISTEMA
  lo rechazará antes de encolar, diciendo que falta el año de presentación.
  Ampliada (revisión en pantalla, 2026-11-14): SI el año, escrito o del perfil, cae fuera del rango que la API publica con
  los tipos de análisis, ENTONCES EL SISTEMA lo rechazará con 422 y dirá el rango; la web usa ese rango, sin copiarlo, en
  un solo campo del año de presentación, el mismo arriba y en el paso 5.
- RF-37: EL SISTEMA dirá con los tipos de análisis la norma de la que salen y su estado jurídico, sin presentarla como
  vigente mientras la metodología la marque como proyecto.
- RF-38: MIENTRAS el tipo elegido sea PIDE y no conste un «Con proyecto» del proyecto, EL SISTEMA avisará que el PIDE parte
  de la obra de corto plazo (098:RF-37), sin bloquear.

### Asistente

- RF-18: EL SISTEMA dará al asistente herramientas para ejecutar cada paso del estudio por las mismas rutas que la web, con
  plan y confirmación.
- RF-19: EL SISTEMA podrá usar los entregables de Empresa B para entrenar al asistente, con revisión humana, solo para
  redactar y dar formato, nunca como verdad eléctrica. Cambia 027:RF-47 por orden del usuario del 2026-11-02, a la propuesta
  «¿autorizas usar los resultados de EMPB para entrenar, con revisión humana?»: «has la 3 y 4 según lo recomendado».
- RF-48: (revisión de T9b con origen «maestro», 2026-11-20, hallazgo 1) CUANDO se registre una decisión sobre un
  fragmento del corpus de redacción, EL SISTEMA guardará su origen, `humano` o `maestro`, el que declare la orden
  (`--origen`, `humano` por defecto) y, si lo trae, el de la propia decisión; un fichero de decisiones cuyo origen no
  coincide con el declarado no se aplica, ni en parte, y una decisión cuya huella del texto ya no es la del fragmento
  tampoco. Por orden del usuario del 2026-11-19 («no deberían ser limitaciones otras personas para cerrar»), la revisión
  de RF-19 la puede hacer una persona o un revisor independiente marcado `maestro`: lo aprobado con cualquiera de los dos
  orígenes se exporta y se sella, cada ejemplo con su origen y el corpus con su recuento por origen; el origen nunca se
  cambia ni se omite, y una decisión de otro origen (o sin él) no se registra ni entra.
- RF-49: (misma revisión, hallazgo 2) EL SISTEMA, al exportar o sellar lo aprobado, ocultará además de las cifras y los
  códigos los nombres de empresa, sede e instalación: los de un catálogo que llega en tiempo de ejecución desde los datos
  del espacio (la empresa que declara cada fragmento y la lista que se pase, sin distinguir mayúsculas ni tildes) y, sin
  catálogo, el nombre que sigue a «SET», a una subestación, central o sede, y la razón social terminada en «S.A.A.»,
  «S.A.» o semejantes, con `‹empresa›`, `‹sede›`, `‹instalación›` o `‹nombre›`. Ningún nombre real va en el código ni en
  las pruebas (RF-20).
- RF-50: (misma revisión, hallazgo 3) EL SISTEMA convertirá lo aprobado (RF-48) y anonimizado en un corpus sellado con
  el mismo formato de particiones, huellas y custodia de fuentes que lee `tools/asistente_qlora.py`
  (`sellar_particiones` de 047), con su propio prompt de redacción, un documento entero por partición, los textos
  repetidos una sola vez, el fragmento de origen custodiado, el origen de cada ejemplo y el recuento `por_origen` en el
  manifiesto; sin ninguna aprobación de origen declarado no sella nada. El preflight de `asistente_qlora.py` lo audita
  (particiones, huellas, fuente, anonimato, origen y que el recuento por origen sea el de sus ejemplos).
- RF-51: (d8, 2026-11-20) CUANDO `tools/asistente_qlora.py entrenar` reciba un corpus sellado, EL SISTEMA elegirá el
  lector y el prompt de sistema por el tipo que declara su manifiesto: sin tipo, el corpus de órdenes con el prompt del
  alumno, como hasta ahora; `redaccion_pide`, el corpus de redacción con el prompt que selló; otro tipo, rechazado. El
  ajuste sigue en CUDA, sin promover el candidato (047:RF-8).
- RF-52: (d8, 2026-11-20, ensayo de T9b) AL sellar el corpus de redacción (RF-50), EL SISTEMA repartirá los documentos
  por su número de ejemplos y no por su huella: cada documento entero en una partición, del mayor al menor; uno va a
  selección, calibración o prueba si cabe en la décima parte del total (o en el doble, si esa partición está vacía), a la
  que más le falte, y lo demás a entrenamiento; con menos de cuatro documentos todo entrena. El reparto no depende del
  orden de llegada.
- RF-53: (d8, 2026-11-21, T9b, puertas del modelo de redacción) CUANDO se examine un modelo entrenado con el corpus de
  redacción sellado (RF-50), EL SISTEMA medirá en CUDA, en las particiones selladas de selección y de prueba, la pérdida
  por token de cada respuesta con la base NF4 fijada y con el adaptador del candidato, sobre los mismos tokens, con su
  perplejidad; SI en alguna de las dos el candidato tiene más pérdida que la base, o no se pudo medir, ENTONCES no lo
  aprobará y lo dirá.
- RF-54: EL SISTEMA redactará una salida por ejemplo de esas dos particiones y SI una deja un nombre de empresa, sede o
  instalación que el anonimizador de RF-49 oculta, con el mismo catálogo con el que se selló el corpus (comprobado por su
  huella), o trae un código de elemento o una cifra que su entrada no trae, ENTONCES no aprobará el modelo; el informe
  dice qué salidas fallan y por qué, sin copiar los nombres ni las cifras. Sin el catálogo del sellado no se examina.
- RF-55: EL SISTEMA examinará el adaptador exportado (pérdida y, sin otro, las salidas) o el modelo publicado en Ollama
  (las salidas, con el prompt de sistema sellado y la instrucción de cada ejemplo, con su semilla); un adaptador
  entrenado con otro corpus o con otro prompt no se examina con este, y sin adaptador la pérdida queda sin medir.
- RF-56: EL SISTEMA no repetirá la prueba sellada del intérprete de órdenes: el modelo de redacción no sustituye al
  intérprete y, sin más, no es activable como tal. Para usarlo también como intérprete, comparará los informes de
  prueba de las órdenes (los de 070 T22, `llm_destilar.py evaluar --parte prueba`) del candidato y del modelo en uso,
  del mismo corpus y el mismo prompt, y solo lo dará por activable si no baja ni el acierto de tarea ni el F1 de datos.
- RF-57: EL SISTEMA dejará la decisión, aprobado o rechazado, con sus motivos, sus medidas por partición y la puerta del
  intérprete, en un informe del candidato, sin promover ni activar nada (047:RF-8), y terminará con 0 si aprueba, 1 si
  rechaza y 2 si no pudo examinar; un corpus de órdenes se remite a su propia evaluación.
- RF-58: (d8, 2026-11-22, rechazo del primer candidato de redacción: en un caso de prueba puso cifras y encadenó la
  misma frase) EL SISTEMA sellará el corpus de redacción con un prompt de sistema que exige escribir ‹n› por cada cifra,
  ‹código› por cada código y ‹empresa›, ‹sede› o ‹instalación› por cada nombre, sin dígitos, y que prohíbe repetir
  frases; un corpus sellado con el prompt anterior se seguirá leyendo para examinar lo ya entrenado, y uno con otro
  prompt no.
- RF-59: EL SISTEMA redactará con el modelo de redacción con penalización de repeticiones, la misma al examinarlo (con el
  adaptador y con Ollama) y al publicarlo en Ollama, donde va en su Modelfile; el Modelfile solo admite parámetros
  numéricos con nombre de parámetro.
- RF-60: SI una salida del modelo de redacción repite seguido un trozo de ocho palabras o más (cinco que no sean
  marcadores) que su entrada no repite, ENTONCES EL SISTEMA la dará por mala (`repetida`) y no aprobará el modelo (RF-54).
- RF-61: AL sellar el corpus de redacción, EL SISTEMA dejará fuera, y los contará, los textos aprobados que una vez
  anonimizados repiten seguida una frase (filas de tabla que quedan iguales al ocultar sus códigos): enseñan a
  encadenar la misma frase. Un corpus sellado así lo declara y su validación rechaza cualquier ejemplo repetido.
- RF-62: CUANDO se selle de nuevo el corpus de redacción indicando el sellado al que sustituye, EL SISTEMA conservará la
  partición de cada documento que ya estaba sellado, repartirá solo los nuevos y declarará en el manifiesto, antes de
  entrenar, las huellas del sellado anterior, sus particiones y cuántos documentos se conservan y cuántos entran.
- RF-63: (d8, 2026-11-22, ratificación independiente de la revisión C4: 922 de 1 255) EL SISTEMA ocultará entero, como
  ‹código›, un código con guion o subrayado que lleve una cifra o un subrayado («TA-201», «CMC_1», «TD_SM»), y también el
  prefijo que quede pegado a un marcador («YUS_‹n›»); un guion entre palabras o entre cifras sigue como está.
- RF-64: EL SISTEMA ocultará un nombre del catálogo también en plural o con otra letra final (si su última palabra tiene
  cinco letras o más), sin tildes y con su codificación rota (la «ñ» leída como «Ð» o «Ã‘», el carácter de reemplazo), y
  el nombre que sigue a un río, una provincia, un distrito, un departamento, una región, una localidad, un centro
  poblado o un caserío (‹nombre›). Al sellar, añadirá al catálogo los nombres que el propio corpus señala tras una SET,
  una sede o un lugar, en una línea y sin las palabras que el corpus también escribe en minúscula, para ocultarlos donde
  salgan solos. Ningún nombre real va en el repositorio: el catálogo sale de los datos del espacio en cada sellado.
- RF-65: AL sellar el corpus de redacción, EL SISTEMA quitará el encabezado y el pie de página del PDF («Informe … – Mes
  ‹n›», «Página ‹n› de ‹n›»), dejará fuera y contará el texto que solo traía eso, y un corpus sellado así rechazará en su
  validación un ejemplo que aún los lleve.
- RF-66: SI una salida del modelo de redacción deja un código con guion o subrayado, o el prefijo de una sede pegado a
  un marcador («TA-‹n›»), ENTONCES EL SISTEMA la dará por mala (`código`); un nombre del catálogo en cualquiera de sus
  variantes de RF-64 la da por mala (`nombre`).
- RF-67: CUANDO un sellado nuevo sustituya a otro (RF-62), EL SISTEMA comprobará el anterior por sus huellas (corpus y
  prompt) y no por las reglas de anonimato de hoy, que son justo lo que cambia.
- RF-68: (enmienda RF-52; coordinador d8, 2026-11-22: «22–23 ejemplos no bastan para decidir») AL sellar el corpus de
  redacción sin un sellado anterior, SI un documento tiene más de la décima parte de los ejemplos, ENTONCES EL SISTEMA
  lo partirá en tramos seguidos de la centésima parte del total (redondeada hacia arriba), en el orden de sus
  fragmentos, y repartirá cada tramo entero como un documento más, para que selección, calibración y prueba lleguen
  cerca de su décima parte. Con menos de cuatro documentos no parte nada; con un sellado anterior (RF-62), los
  documentos siguen enteros.

### Casos de prueba

- RF-20: EL SISTEMA tratará los nombres de empresas, clientes y proyectos de ejemplos, pruebas y documentos como casos de prueba
  del conversor, no como valores por defecto (usuario, 2026-11-02: «etiqueta como de prueba del conversor»).

## Requisitos no funcionales

Universal: cualquier distribuidora y número de alimentadores. Determinismo del DGS intacto. Los datos descargados quedan fuera
de git.

## Casos límite

Una empresa sin VNR fijado en el último proceso usa el de su última resolución y lo dice. Una red con códigos sin costo
sigue con el hueco nombrado. Un año base distinto del año medido se avisa.

## Fuera de alcance

El piloto MADRL. La tensión en valle en la elección de obras es de la spec 073. No se reproduce el consultor: los entregables
históricos son referencia.

## Criterios de finalización

Cada RF con su prueba, una aceptación real de los dos entregables en una empresa, y suite completa sin omitidas.
