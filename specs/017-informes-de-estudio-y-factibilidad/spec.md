# Spec 017 — Informes de estudio eléctrico y de factibilidad de suministro

Estado: aprobada (2026-10-15, «continúa con el flujo hasta cerrar los dos informes») · Fecha: 2026-10-14 · Origen: petición del usuario, 2026-10-14 («para
cerrar el proyecto, el resultado se plasma en un informe de cada análisis: uno de punto
de diseño y factibilidad de suministro y otro de análisis de estudios eléctricos»)

## Contexto y objetivo

Las specs 011, 014 y 015 dejan el proyecto de DIgSILENT con tres casos («Caso base»,
«Sin proyecto» calibrado y «Con proyecto» con las cargas nuevas) y con obras de mejora
en variaciones propias. Pero el resultado se queda en DIgSILENT y en el JSON de cada
estudio: el ingeniero de planificación todavía copia a mano los datos de la fuente, la
tensión mínima, la cargabilidad y las imágenes del diagrama coloreado a un Word con el
formato de la distribuidora, y calcula aparte, en un libro Excel, las pérdidas y lo que
cuestan frente a lo que reconoce el regulador.

La empresa usa dos informes, y el usuario dio un modelo de cada uno (2026-10-14):

- **Factibilidad y punto de diseño** (`InformeModelo.docx`, el caso EMAPICA de 430 kW en
  IC106). Se hace para **una** carga nueva, la que se ingresa sola. Las que entran en
  bloque solo actualizan solicitudes ya analizadas, con punto de diseño ya dado, y en el
  informe cuentan como «cargas de solicitudes vigentes». Lleva el estado actual y el
  proyectado del alimentador, los datos en el punto de diseño, las pérdidas técnicas
  frente a las reconocidas por el regulador (las calcula el libro
  `informeModeloperdidas.xlsx`, cuyas fórmulas se reconstruyen aquí) y la cargabilidad
  del transformador de la SET, que sale de un proyecto de transmisión de DIgSILENT
  («AD8 V4»).
- **Estudio eléctrico** (`IT.CASA_BLANCA.doc`, en realidad un `.docx`: caída de tensión de
  un cliente en CA101 y PE104). Se hace cuando el problema es la calidad de tensión o la
  cargabilidad, no una carga nueva. Lleva el estado actual, el proyectado con las obras
  de mejora, el detalle de las obras y las conclusiones.

El caso de prueba es CA101, evaluado por caída de tensión (informe de estudio, sin carga
nueva), ejecutado desde cero: conversión, importación, «Caso base» verificado, «Sin
proyecto» calibrado y «Con proyecto» con las obras. Para ese caso el usuario fija el
orden de las obras: primero los bancos de condensadores que el alimentador ya tiene en
DIgSILENT (tres, en sus mismos nodos) y bancos nuevos propuestos; después reguladores de
tensión; después el cambio de conductor a 120 mm²; y, como último recurso, la migración
a 22,9 kV.

Las imágenes son siempre de DIgSILENT, del proyecto que se estudia. Las curvas que trae
el modelo no se incluyen.

## Usuarios / actores

- Ingeniero de planificación que, desde la web, genera el informe de un proyecto de
  DIgSILENT ya calibrado (specs 014 y 015).
- Destinatario del informe (Proyectos y Obras), que lo recibe en Word y puede editarlo.
- DIgSILENT PowerFactory 2024, por su API de Python, en el carril `powerfactory`.

## Historias de usuario

- H1: Como ingeniero quiero el informe de factibilidad de una carga nueva en el formato
  de la empresa, con los números y las imágenes de DIgSILENT, para no copiarlos a mano.
- H2: Como ingeniero quiero las pérdidas técnicas del alimentador antes y después de la
  carga, frente a las que reconoce el regulador y en soles al año, sin rellenar el libro
  Excel.
- H3: Como ingeniero quiero la cargabilidad del transformador de la SET con y sin la
  carga, tomada del modelo de transmisión, para decir si la SET la admite.
- H4: Como ingeniero quiero el informe de estudio de un alimentador con mala calidad de
  tensión, con el estado actual y el proyectado con obras, para justificar la inversión.
- H5: Como ingeniero quiero que las obras se prueben de la más barata a la más cara y que
  el informe diga cuál basta, para no proponer una migración donde bastan condensadores.
- H6: Como destinatario quiero un Word editable, para ajustar la redacción y firmarlo.
- H7: Como ingeniero quiero generar los informes desde la web, en el mismo sitio donde
  calibro, integro las cargas y modelo las obras, y ver el resumen y las imágenes antes de
  descargar el Word.

## Requisitos funcionales (EARS)

### Comunes a los dos informes

- RF-1: EL SISTEMA generará el informe de «factibilidad y punto de diseño» cuando se
  evalúa la conexión de un cliente nuevo.
- RF-1b: EL SISTEMA generará el informe de «estudio eléctrico» cuando se analiza la red
  existente (caída de tensión, cargabilidad, pérdidas) y sus obras de mejora, sin un
  cliente nuevo que evaluar.
- RF-2: EL SISTEMA generará cada informe como un documento `.docx` editable.
- RF-3: EL SISTEMA dará a cada informe las secciones, títulos y tablas de su modelo, en el
  mismo orden.
- RF-4: EL SISTEMA tomará el modelo de cada tipo de informe del fichero que indique el
  perfil de empresa, nunca de una ruta fija ni de `referencia/`.
- RF-5: SI el perfil de empresa no indica el modelo de un tipo de informe, ENTONCES EL
  SISTEMA no generará ese tipo y dirá qué clave del perfil falta.
- RF-6: EL SISTEMA sacará todo valor numérico del informe de DIgSILENT, del libro de la
  empresa (RF-36) o de lo que escriba el operador, y nunca lo copiará del modelo.
- RF-7: EL SISTEMA sacará toda imagen del informe de DIgSILENT, exportada del proyecto
  estudiado.
- RF-8: EL SISTEMA no incluirá en el informe las curvas que trae el modelo.
- RF-9: EL SISTEMA no incluirá en el informe documentos del cliente que no estén en
  DIgSILENT, como el recibo de luz del modelo de estudio.
- RF-10: EL SISTEMA exportará, por cada caso del informe, una imagen del alimentador
  coloreado por tensión y otra coloreado por cargabilidad.
- RF-11: EL SISTEMA exportará las imágenes del diagrama geográfico del alimentador.
- RF-12: SI el alimentador no tiene diagrama geográfico, ENTONCES EL SISTEMA exportará el
  esquemático y lo dirá al pie de la imagen.
- RF-13: EL SISTEMA tomará del perfil de empresa la banda de tensión admitida y el umbral
  de cargabilidad con que se colorea y se concluye.
- RF-14: SI el perfil no trae la banda de tensión o el umbral de cargabilidad, ENTONCES EL
  SISTEMA los pedirá en el formulario del informe, sin suponer ningún valor.
- RF-15: EL SISTEMA dará los «datos de la fuente» de cada caso: kW, kvar, kVA y factor de
  potencia desde la fuente, y las pérdidas en kW, kvar, kVA y factor de potencia.
- RF-16: EL SISTEMA dará de cada caso la tensión mínima en p.u., con su nodo, y el número
  de nodos fuera de la banda.
- RF-17: MIENTRAS el flujo de carga sea desbalanceado, EL SISTEMA dará la tensión mínima
  de cada fase (A, B y C).
- RF-18: MIENTRAS el flujo de carga sea balanceado, EL SISTEMA dará una sola tensión mínima,
  rotulada como trifásica, en vez de repetirla por fase.
- RF-19: EL SISTEMA dará de cada caso la cargabilidad máxima, con su tramo, y el número de
  tramos por encima del umbral.
- RF-20: EL SISTEMA redactará el texto de cada análisis (caída de tensión, cargabilidad) a
  partir de los resultados y de la banda o el umbral, sin afirmar nada que los
  resultados no digan.
- RF-21: EL SISTEMA redactará un borrador de conclusiones a partir de los resultados, que
  el ingeniero puede editar en el Word.
- RF-22: EL SISTEMA rellenará los campos de texto del encabezado (fecha, asunto,
  destinatario, antecedentes) con lo que escriba el operador en el formulario.
- RF-23: SI un dato del informe no se pudo obtener, ENTONCES EL SISTEMA dejará su hueco
  señalado en el Word con el motivo y generará el resto del informe.
- RF-24: SI el flujo de carga de un caso no converge, ENTONCES EL SISTEMA lo dirá en la
  sección de ese caso, sin valores, y generará el resto del informe.
- RF-25: EL SISTEMA dejará junto a cada `.docx` un JSON con todos los valores del informe,
  sus casos, variaciones activas e imágenes.
- RF-26: EL SISTEMA generará los informes como un trabajo en cola del carril
  `powerfactory`, con progreso y cancelable.
- RF-27: SI se cancela la generación, ENTONCES EL SISTEMA no dejará un `.docx` a medias.
- RF-28: EL SISTEMA dejará el proyecto del alimentador con los mismos casos, variaciones y
  escenarios activos que tenía antes de generar el informe.

### Informe de estudio eléctrico

- RF-29: CUANDO el operador pida el informe de estudio de uno o varios alimentadores, EL
  SISTEMA tomará como estado actual el caso «Sin proyecto».
- RF-30: CUANDO el operador pida el informe de estudio, EL SISTEMA tomará como estado
  proyectado el caso «Con proyecto» con las obras de mejora del informe activas.
- RF-31: SI el estado actual cumple la banda y el umbral en todos los alimentadores del
  informe, ENTONCES EL SISTEMA lo dirá y no evaluará obras.
- RF-32: SI el estado actual no cumple la banda o el umbral, ENTONCES EL SISTEMA evaluará
  las obras en este orden, cada etapa sumada a las anteriores: (1) bancos de
  condensadores existentes, (2) bancos propuestos, (3) reguladores de tensión, (4) cambio
  de conductor de la troncal, (5) migración a otra tensión.
- RF-33: CUANDO una etapa de RF-32 haga cumplir la banda y el umbral, EL SISTEMA la
  recomendará y no evaluará las siguientes, salvo que el operador pida evaluarlas todas.
- RF-34: SI ninguna etapa hace cumplir la banda y el umbral, ENTONCES EL SISTEMA lo dirá y
  dará los resultados de todas.
- RF-35: EL SISTEMA modelará cada etapa como una o varias obras de la spec 011, en sus
  propias variaciones, activas solo en «Con proyecto».
- RF-36: EL SISTEMA leerá de DIgSILENT los bancos de condensadores del alimentador con su
  nodo, su potencia en kvar y su estado de servicio.
- RF-36b: DONDE el operador indique un proyecto anterior de DIgSILENT del mismo
  alimentador (en CA101, «CA101 13»), EL SISTEMA leerá sus bancos de condensadores con su
  nodo, kvar, tipo y estado, los comparará por nodo con los del proyecto estudiado y dirá
  en el informe cuáles faltan o difieren. (El usuario, 2026-10-15: es un caso
  excepcional, no la regla.)
- RF-36c: DONDE se dé ese proyecto anterior, EL SISTEMA creará en la etapa 1, en una
  variación activa solo en «Con proyecto», los bancos que faltan, en los mismos nodos y con
  las mismas características, y los dejará en servicio.
- RF-36d: SI el nodo de un banco del proyecto anterior no está en el proyecto estudiado,
  ENTONCES EL SISTEMA no lo creará y dirá en el informe qué banco y qué nodo faltan.
- RF-37: EL SISTEMA modelará la etapa de bancos existentes con esos bancos en servicio y en
  sus mismos nodos.
- RF-38: SI los bancos existentes ya están en servicio en «Sin proyecto», ENTONCES EL
  SISTEMA dirá que la etapa 1 coincide con el estado actual y pasará a la etapa 2.
- RF-39: EL SISTEMA propondrá los bancos nuevos con la ubicación óptima de condensadores de
  DIgSILENT (`ComCapo`), limitada al alimentador y con la banda de tensión como restricción.
- RF-39b: EL SISTEMA tomará los bancos disponibles (kvar, tensión, coste de inversión y de
  mantenimiento anual) y el precio de la energía de una tabla de costes de la empresa, con
  la fuente y la fecha de cada fila.
- RF-39c: SI la tabla de costes no trae bancos o precio de la energía, ENTONCES EL SISTEMA no
  ejecutará la etapa 2 y dirá qué falta.
- RF-39d: EL SISTEMA traerá una tabla de costes de referencia con precios de mercado
  encontrados en la web, cada fila marcada «referencial» con su fuente, para que la
  empresa la sustituya por sus cotizaciones.
- RF-39e: EL SISTEMA dirá en el informe si los costes usados son referenciales o de la
  empresa.
- RF-40: EL SISTEMA propondrá los reguladores de tensión con la ubicación óptima de equipos
  de DIgSILENT (`ComPlaceopt`, «Optimal Equipment Placement»), limitada al alimentador.
- RF-40b: EL SISTEMA ejecutará `ComPlaceopt` con la banda de tensión y el umbral de
  cargabilidad como restricciones y con los nodos de la troncal como candidatos.
- RF-40c: EL SISTEMA tomará los tipos de regulador, su coste de instalación y de
  mantenimiento de la tabla de costes de RF-39b.
- RF-40d: EL SISTEMA guardará los bancos y reguladores propuestos en variaciones propias,
  activas solo en «Con proyecto» (RF-35).
- RF-41: EL SISTEMA modelará el cambio de conductor con la sección y el tipo que indique el
  operador (120 mm² en CA101) en los tramos de la troncal que van de la cabecera a la SED
  que indique el operador.
- RF-42: EL SISTEMA modelará la migración con la tensión que indique el operador (22,9 kV
  en CA101) solo en la troncal que va de la cabecera a la SED que indique el operador, con
  lo que cuelga de ella, y no en el alimentador entero. (El usuario, 2026-10-15: «se está
  migrando según la troncal que va a Casa Blanca», es decir, hasta la SED SE20701.)
- RF-42b: EL SISTEMA construirá la troncal de RF-41 y RF-42 y la migración por tramos con
  las obras de la spec 016 (troncal y migración aguas abajo de un nodo), que esta spec
  necesita implementadas.
- RF-42c: SI la SED indicada no está en el alimentador, ENTONCES EL SISTEMA no evaluará las
  etapas 4 y 5 y dirá qué SED no encuentra.
- RF-43: EL SISTEMA dará, por etapa evaluada, la tensión mínima, la cargabilidad máxima,
  las pérdidas y si cumple la banda y el umbral.
- RF-44: EL SISTEMA dará en el detalle de obras, por etapa: los bancos con nodo y kvar, los
  reguladores con nodo, los km de conductor cambiado con su tipo y, en la migración, el
  número de transformadores de distribución que hay que adecuar a la nueva tensión.
- RF-45: DONDE el operador asigne un año a cada etapa, EL SISTEMA lo dará en el detalle de
  obras, como las etapas por año del modelo.
- RF-46: EL SISTEMA dará la vista topológica y de ubicación del alimentador en el estado
  actual y en el proyectado con la etapa recomendada.

### Informe de factibilidad y punto de diseño

- RF-47: EL SISTEMA generará el informe de factibilidad solo para una carga nueva ingresada
  sola (spec 007), nunca para las cargas ingresadas en bloque.
- RF-48: EL SISTEMA tomará como estado actual el caso «Sin proyecto».
- RF-49: EL SISTEMA tomará como estado proyectado el caso «Con proyecto» con la variación
  de la carga del informe y las de las cargas en bloque, y sin las demás cargas
  ingresadas solas.
- RF-50: EL SISTEMA dirá en el informe que las cargas en bloque son «solicitudes vigentes»
  consideradas en el estado proyectado.
- RF-51: EL SISTEMA tomará del formulario los datos de la solicitud: cliente, ubicación,
  tipo de solicitud, potencia solicitada, fecha de la solicitud, alimentador, SET,
  tensión, transformador de la SET y expediente.
- RF-52: EL SISTEMA dará los datos en el punto de diseño del estado proyectado: tensión en
  p.u., kV entre líneas, kV de fase, corriente, kVA, kW y kvar.
- RF-53: EL SISTEMA dará como punto de diseño el nodo de media tensión donde se conecta la
  carga (spec 007), con su código de la red de origen.
- RF-54: EL SISTEMA calculará la energía anual como la máxima demanda (kW desde la fuente)
  por 8760 h y por el factor de carga.
- RF-55: EL SISTEMA calculará el factor de pérdidas como 0,3·FC + 0,7·FC².
- RF-56: EL SISTEMA calculará las pérdidas técnicas anuales como las pérdidas totales del
  flujo en kW por 8760 h y por el factor de pérdidas.
- RF-57: EL SISTEMA calculará el porcentaje de pérdidas como las pérdidas técnicas anuales
  entre la energía anual.
- RF-58: EL SISTEMA calculará la pérdida no reconocida al año como (pérdidas técnicas
  anuales − porcentaje reconocido en energía × energía anual) × precio de compra.
- RF-59: EL SISTEMA dará RF-54 a RF-58 para el estado actual y para el proyectado.
- RF-60: EL SISTEMA calculará el factor de carga con la medición de cabecera del mes de
  análisis (spec 013), como energía medida entre máxima demanda medida por horas del mes.
- RF-61: SI no hay medición de cabecera del mes de análisis, ENTONCES EL SISTEMA pedirá el
  factor de carga en el formulario.
- RF-62: EL SISTEMA leerá del libro de pérdidas de la empresa el sistema eléctrico del
  alimentador, sus pérdidas técnicas reconocidas en MT (en potencia y en energía) y el
  precio de compra de la energía.
- RF-63: EL SISTEMA buscará las hojas y columnas del libro de pérdidas por los nombres que
  indique el perfil de empresa.
- RF-64: SI el alimentador no está en el libro de pérdidas, ENTONCES EL SISTEMA dará las
  pérdidas técnicas calculadas y dejará señalado el hueco de lo reconocido.
- RF-65: EL SISTEMA obtendrá la cargabilidad del transformador de potencia de la SET del
  proyecto de transmisión de DIgSILENT que indique el perfil de empresa. (En Electro Dunas,
  `AD08_MPIT25-29_v4`: solo transmisión, sin redes de media tensión; cada alimentador es
  una carga concentrada en la barra de 10 kV o de 22,9 kV de su SET, y el proyecto sirve
  para ver la cargabilidad de la SET.)
- RF-65b: EL SISTEMA usará el caso de estudio del proyecto de transmisión que elija el
  operador entre los que tiene el proyecto, con el del año de análisis propuesto.
- RF-66: EL SISTEMA dará la cargabilidad de cada devanado del transformador de la SET al que
  se conecta el alimentador, en el estado actual y en el proyectado.
- RF-67: EL SISTEMA pondrá en la carga concentrada del alimentador, en cada estado, la P y la
  Q que entran por la cabecera del alimentador en el flujo de ese estado.
- RF-67b: EL SISTEMA no sumará aparte la carga nueva en el proyecto de transmisión, porque ya
  está en la P y la Q de la cabecera del estado proyectado.
- RF-67c: EL SISTEMA buscará la carga concentrada del alimentador por su nombre en la barra
  de su SET.
- RF-67d: SI el proyecto de transmisión no tiene carga concentrada para el alimentador,
  ENTONCES EL SISTEMA pondrá una provisional en la barra de su SET y tensión, y lo dirá en
  el informe.
- RF-67e: DONDE parte del alimentador pase a otra tensión en el estado proyectado, EL
  SISTEMA pondrá esa parte en la barra de esa tensión de la misma SET.
- RF-68: EL SISTEMA no guardará ningún cambio en el proyecto de transmisión.
- RF-69: EL SISTEMA dará la imagen del transformador de la SET con su cargabilidad, del
  diagrama del proyecto de transmisión.
- RF-70: SI el perfil no indica el proyecto de transmisión, o en él no se encuentra la SET
  o su barra, ENTONCES EL SISTEMA dejará señalada la sección del transformador y generará
  el resto.
- RF-71: EL SISTEMA concluirá que la carga es factible solo si, en el estado proyectado, el
  alimentador cumple la banda y el umbral y el transformador de la SET no supera su
  capacidad.
- RF-72: SI la carga no es factible, ENTONCES EL SISTEMA dirá en las conclusiones qué límite
  se supera, dónde y en cuánto.

#### Estructura y figuras del informe de factibilidad

El modelo (`InformeModelo.docx`, EMAPICA en IC106, leído entero el 2026-10-15) tiene
este orden, y cada figura sale de DIgSILENT salvo la ubicación, que en el modelo es una
captura de Google Earth.

- RF-106: EL SISTEMA dará al informe de factibilidad este orden de secciones: 1
  Antecedentes; 2 Descripción; 2.1 Vista topológica y ubicación; 2.2 Estado actual (2.2.1
  Datos de la fuente, 2.2.1.1 Caída de tensión, 2.2.1.2 Cargabilidad); 2.3 Estado
  proyectado (Datos de la fuente, 2.3.1 Caída de tensión con los datos en el punto de
  diseño, 2.3.2 Carga para considerar, 2.3.3 Cargabilidad); 2.4 Pérdidas técnicas; 2.5
  Transformador de potencia; 3 Conclusiones.
- RF-107: EL SISTEMA redactará los antecedentes con las frases del libro de la empresa:
  fecha y tipo de la solicitud con la ubicación del predio, expediente, potencia
  solicitada, alimentador próximo y características del transformador de la SET.
- RF-108: EL SISTEMA redactará la descripción con las fuentes de información del análisis
  y el alimentador en cuya zona de influencia está el cliente.
- RF-109: EL SISTEMA dará en 2.1 una imagen de la ubicación del cliente nuevo sobre un
  mapa, con el cliente marcado y rotulado con su nombre, su punto de conexión y los
  alimentadores cercanos, cada uno en su color y rotulado con su nombre.
- RF-110: EL SISTEMA tomará la imagen de ubicación del diagrama geográfico de DIgSILENT,
  con el mapa de fondo y centrada en el cliente y su punto de conexión.
- RF-111: EL SISTEMA usará de fondo el mapa satélite configurado en DIgSILENT (Esri
  ArcGIS u OpenStreetMap), sin enviar coordenadas a ningún servicio fuera de DIgSILENT.
- RF-112: SI no se puede cargar el mapa de fondo, ENTONCES EL SISTEMA dará el diagrama
  geográfico sin fondo y lo dirá al pie de la imagen.
- RF-113: EL SISTEMA pondrá antes de cada imagen coloreada por tensión la leyenda de ese
  coloreado, con sus bandas, colores y anchuras de línea.
- RF-114: EL SISTEMA pondrá antes de cada imagen coloreada por cargabilidad la leyenda de
  ese coloreado, con sus bandas, colores y anchuras de línea.
- RF-115: EL SISTEMA tomará las bandas de los dos coloreados del perfil de empresa. (Las del
  modelo, que irán en el perfil de Electro Dunas: tensión 85, 90, 95 y 105 % de la
  nominal; cargabilidad 80, 90, 95, 105 y 150 %.)
- RF-116: EL SISTEMA aplicará esas bandas al coloreado del diagrama de DIgSILENT antes de
  exportar y dejará después el coloreado que tenía.
- RF-117: EL SISTEMA marcará la carga nueva en las imágenes del estado proyectado con un
  rótulo «Carga-{nombre}-{kW} kW-Cod {código del punto de diseño}» y una flecha a su punto
  de conexión.
- RF-118: EL SISTEMA dará la tabla de tensión mínima por fase (RF-17) después de la imagen
  de caída de tensión del estado actual y después de la de cargabilidad del proyectado,
  como el modelo.
- RF-119: EL SISTEMA dará en 2.5 la imagen del unifilar del proyecto de transmisión
  recortada al transformador de la SET, con un rótulo «Cargabilidad devanado {kV} kV {x} %».
- RF-120: EL SISTEMA dará al pie de la imagen de 2.5 «Figura n: Cargabilidad de {x} % en el
  devanado de {kV} kV de la SET {nombre} - {transformador}».
- RF-121: EL SISTEMA redactará 2.5 con la cargabilidad del devanado sin proyecto y con
  proyecto y el caso de estudio del proyecto de transmisión del que sale.
- RF-122: EL SISTEMA redactará las conclusiones en apartados: a) la solicitud y si el predio
  está en el área de concesión, según indique el operador; b) la factibilidad en el
  alimentador; c) el transformador de la SET; d) el punto de diseño recomendado, con el
  código de la estructura de media tensión.

### Interfaz

El informe es lo último que hace el operador sobre el proyecto: va en un paso nuevo,
«5 · Informes», de la pestaña de cargas en DIgSILENT, después de «4 · Obras y estudios»,
con el mismo proyecto (paso 1) y los mismos alimentadores marcados (paso 2).

> Cambio del 2026-10-15 (el usuario): los informes van en **«4.4 · Informes»**, dentro de
> «4 · Obras y estudios», no en un paso 5; «5.1» es «4.4.2» (factibilidad) y «5.2» es
> «4.4.1» (estudio). Cada informe se arma con lo que la web ya guardó: los flujos de 4.2,
> las obras de 4.1, las cargas nuevas aplicadas en el paso 3 y la máxima de 2.2. Hasta que
> estén T5 (libro de pérdidas en la web) y T10 (transformador de la SET), las pérdidas
> reconocidas y la cargabilidad del devanado de la SET se escriben a mano en 4.4.2; lo que
> falte queda señalado en el Word. Sin T7 y T8 no hay imágenes ni etapas evaluadas por el
> guion: el estudio usa las obras de «Con proyecto» tal como se aplicaron.

Paso y requisitos previos

- RF-73: EL SISTEMA mostrará el paso «5 · Informes» en la pestaña de cargas en DIgSILENT,
  después del paso «4 · Obras y estudios», con dos apartados: «5.1 · Conexión de un cliente
  nuevo (factibilidad y punto de diseño)» y «5.2 · Análisis eléctrico (estudio
  eléctrico)».
- RF-74: EL SISTEMA usará en el paso 5 el proyecto elegido en el paso 1 y los
  alimentadores marcados en el paso 2, sin volver a pedirlos.
- RF-75: SI no hay proyecto elegido o ningún alimentador marcado, ENTONCES EL SISTEMA
  mostrará en el paso 5 qué paso falta, en vez del formulario.
- RF-76: SI el perfil de empresa no trae el modelo de un tipo de informe, ENTONCES EL
  SISTEMA desactivará su botón «Generar» y dirá, junto al botón, qué clave del perfil falta.
- RF-77: SI el proyecto no tiene el caso «Sin proyecto» o el caso «Con proyecto», ENTONCES
  EL SISTEMA desactivará «Generar» y dirá qué paso los crea.
- RF-78: SI el último flujo de «Sin proyecto» de un alimentador marcado no convergió,
  ENTONCES EL SISTEMA lo avisará junto al botón y dejará generar el informe, que lo dirá en
  su sección (RF-24).

Formulario común

- RF-79: EL SISTEMA pedirá en los dos apartados la fecha, el asunto, el destinatario y los
  antecedentes del informe.
- RF-80: EL SISTEMA propondrá la fecha de hoy y un asunto con el tipo de informe y los
  alimentadores, que el operador puede cambiar.
- RF-81: CUANDO el perfil no traiga la banda de tensión o el umbral de cargabilidad, EL
  SISTEMA mostrará esos campos en el formulario, vacíos y obligatorios (RF-14).
- RF-82: EL SISTEMA guardará lo escrito en el formulario con el espacio de trabajo, en el
  servidor, para no perderlo al recargar la página.

Apartado 5.1 · Conexión de un cliente nuevo

- RF-89: EL SISTEMA ofrecerá en 5.1 elegir la carga del informe entre las cargas nuevas
  ingresadas solas que tienen variación en «Con proyecto» de los alimentadores marcados.
- RF-90: SI no hay ninguna carga nueva ingresada sola en esos alimentadores, ENTONCES EL
  SISTEMA lo dirá en 5.1 y remitirá al paso 3.
- RF-91: CUANDO el operador elija la carga, EL SISTEMA rellenará con sus datos la potencia,
  el alimentador y la tensión de RF-51, y dejará editables los demás campos de la
  solicitud.
- RF-92: EL SISTEMA mostrará el factor de carga calculado de la medición de cabecera (RF-60)
  con el mes del que sale, y pedirá el factor de carga solo si no hay medición (RF-61).
- RF-93: EL SISTEMA permitirá subir el libro de pérdidas de la empresa en 5.1 y lo guardará
  con el espacio de trabajo.
- RF-94: CUANDO se suba el libro de pérdidas, EL SISTEMA mostrará el sistema eléctrico, las
  pérdidas reconocidas y el precio que lee para el alimentador, o qué no encuentra.
- RF-95: EL SISTEMA mostrará en 5.1 el proyecto de transmisión del perfil y permitirá elegir
  otro de la carpeta de proyectos de DIgSILENT (spec 005).
- RF-124: EL SISTEMA ofrecerá en 5.1 una vista previa de la imagen de ubicación, como
  trabajo del carril `powerfactory`, antes de generar el informe.
- RF-125: EL SISTEMA pedirá en 5.1 que el operador confirme si el predio está en el área de
  concesión (RF-122 a).

Apartado 5.2 · Análisis eléctrico

- RF-83: EL SISTEMA mostrará en 5.2 las cinco etapas de obras de RF-32, en su orden, cada
  una con una casilla para incluirla o no.
- RF-84: EL SISTEMA mostrará en la etapa de bancos existentes los bancos que lee de
  DIgSILENT (nodo, kvar y estado), o dirá que el alimentador no tiene ninguno.
- RF-85: EL SISTEMA pedirá en la etapa de cambio de conductor el tipo de línea, elegido de
  las bibliotecas del proyecto como en las obras de la spec 011.
- RF-86: EL SISTEMA pedirá en la etapa de migración la tensión de destino en kV.
- RF-86b: EL SISTEMA pedirá en las etapas de cambio de conductor y de migración la SED hasta
  la que llega la troncal, con búsqueda entre las SED de los alimentadores marcados, y
  mostrará la longitud de esa troncal.
- RF-87: EL SISTEMA permitirá dar a cada etapa un año opcional para el detalle de obras
  (RF-45).
- RF-88: EL SISTEMA ofrecerá una casilla «Evaluar todas las etapas aunque una ya cumpla»,
  desmarcada por defecto (RF-33).

Generación, progreso y resultado

- RF-96: CUANDO el operador pulse «Generar», EL SISTEMA validará el formulario en el
  servidor y, si hay un error, lo mostrará junto al campo, sin empezar el trabajo.
- RF-97: MIENTRAS se genera un informe, EL SISTEMA mostrará el progreso por pasos (caso,
  etapa de obras, imagen, documento) y escribirá el detalle en el Registro.
- RF-98: MIENTRAS corre un trabajo del carril `powerfactory`, EL SISTEMA desactivará los
  botones «Generar» de los dos apartados.
- RF-99: EL SISTEMA ofrecerá cancelar la generación, y al cancelar dirá que no se ha
  escrito ningún informe y que el proyecto ha quedado como estaba (RF-27, RF-28).
- RF-100: CUANDO termine la generación, EL SISTEMA mostrará en la página un resumen por caso
  y por etapa (tensión mínima, cargabilidad máxima, pérdidas, si cumple) y la etapa
  recomendada o el veredicto de factibilidad.
- RF-101: CUANDO termine la generación, EL SISTEMA mostrará en miniatura las imágenes
  exportadas de DIgSILENT, que se amplían al pulsarlas.
- RF-102: SI el informe tiene huecos señalados (RF-23), ENTONCES EL SISTEMA los listará en el
  resumen, con su motivo.
- RF-103: EL SISTEMA ofrecerá descargar el `.docx` y su JSON de cada informe generado.
- RF-104: EL SISTEMA listará en el paso 5 los informes ya generados del proyecto, con su
  tipo, fecha y alimentadores, y los dejará descargar de nuevo.

Línea de órdenes

- RF-105: EL SISTEMA ofrecerá generar los informes desde una herramienta de línea de
  órdenes con el mismo plan JSON que prepara la web.

## Requisitos no funcionales

- Escala: un informe de estudio admite uno o varios alimentadores, sin número fijo; nada
  recorre la red entera por alimentador.
- Imágenes de al menos 150 ppp, para que se lea el coloreado al imprimir en A4.
- Universal (P13): la banda de tensión, el umbral de cargabilidad, las hojas del libro de
  pérdidas, los modelos de informe y el proyecto de transmisión van en el perfil de
  empresa; ninguno es un valor por defecto del código.
- Datos de la distribuidora (P9): los informes, sus JSON y sus imágenes se escriben solo en
  el espacio de trabajo local.
- Entorno (P8): la librería que escribe el `.docx` entra en `requirements.txt`.
- Idioma: el informe, sus textos generados y los mensajes, en español.

## Casos límite

- Alimentador sin diagrama geográfico (RF-12).
- Flujo que no converge en «Con proyecto» con una etapa, por ejemplo la migración sin
  adecuar los transformadores (RF-24 y RF-34).
- Alimentador sin bancos de condensadores en DIgSILENT: la etapa 1 se omite con aviso.
- Estado actual que ya cumple (RF-31).
- Informe de estudio de varios alimentadores, como Casa Blanca con CA101 y PE104.
- Carga nueva sin variación en «Con proyecto» (no se conectó): el informe de factibilidad
  no se genera y se dice por qué.
- Proyecto de transmisión abierto por otro usuario o que no converge (RF-70).
- Cancelación a mitad de la generación (RF-27) y restauración del proyecto (RF-28).
- Recarga de la página o reinicio de la web a mitad del formulario (RF-82) o de la
  generación: el trabajo sigue en el carril y el resultado aparece al volver.
- Libro de pérdidas con otras hojas o columnas que las del perfil (RF-94).
- Muchos alimentadores marcados en el paso 2: el informe de estudio los admite todos, sin
  número fijo, y la lista de bancos de RF-84 se muestra por alimentador.

## Fuera de alcance

- Las curvas de carga del modelo y el recibo de luz (RF-8, RF-9).
- Comparar varios alimentadores candidatos para una misma carga (la conclusión b del
  modelo EMAPICA): el operador genera un informe por alimentador.
- La transferencia de tramos a otro alimentador y la fuente desde una SET nueva, como en
  Casa Blanca (PE104 hacia Chincha Nueva). La migración por la troncal sí entra (RF-42),
  con las obras de la spec 016.
- PDF, firma y envío del informe.
- Valorizar la inversión de las obras (VNR): la hoja `INVERSION_VNR_LINEA` del libro está
  vacía.

## Criterios de finalización

- Cada RF citado por al menos una prueba (`grep -rnoE "017:RF-[0-9]+" tests`).
- Suite en verde, también con las variables `IGEA_*`, con una prueba de API en
  `tests/test_web_api.py` por cada endpoint nuevo.
- `npx tsc --noEmit -p frontend` sin errores y `npm run build` correcto; el paso 5 revisado
  con la checklist del skill `igea-dgs-frontend` (modo claro y oscuro, sin `localStorage`).
- Prueba en DIgSILENT con CA101 desde cero: conversión, importación, «Caso base»
  verificado, calibración en «Sin proyecto», etapas de obras en «Con proyecto» e informe
  de estudio generado, con las imágenes de DIgSILENT, revisado por el usuario.
- Prueba en DIgSILENT de un informe de factibilidad con una carga nueva real del libro de
  cargas nuevas y el proyecto de transmisión AD8 V4.

## Dudas abiertas

Resueltas el 2026-10-15:

- Mapa: cualquiera; se usa el de DIgSILENT (RF-111), sin Google Maps.
- Bancos nuevos y reguladores: con los módulos nativos `ComCapo` y `ComPlaceopt`, costes de
  mercado como referencia (RF-39 a RF-40d).
- Bancos de CA101: hoy en servicio; la etapa 1 coincide con el estado actual (RF-38).
- AD08: solo transmisión, alimentadores como cargas concentradas (RF-65 a RF-67e).
- SED de Casa Blanca: SE20701 (NIS 381000372), radial CA101.

- Bancos de «otro modelo ya considerado» (RF-36b a RF-36d): el proyecto anterior de
  DIgSILENT «CA101 13»; se copian a los mismos nodos con las mismas características.

Abiertas: ninguna.
