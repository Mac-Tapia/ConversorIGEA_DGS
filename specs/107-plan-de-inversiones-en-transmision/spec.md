# Spec 107 — Plan de Inversiones en Transmisión (PIT) del sistema secundario y complementario

Estado: implementada (2026-11-19: el PIT con DIgSILENT desde la web, T42 y T43 cerradas; queda T14 en DIgSILENT) · Fecha: 2026-11-14 · Origen: Plan Maestro v1.6, BP-17, y orden del usuario del 2026-11-14:
«haz nuevos spec» para las brechas sin spec. G0: `D:/csg/G0_PLAN_MAESTRO/D/D_FILAS_BP.md`.

## Contexto y objetivo
El conversor estudia alimentadores de media tensión y arma el PIDE de distribución (072), pero no tiene nada para el PIT.
El PIT es el plan de inversiones de los sistemas secundario y complementario de transmisión (SST/SCT), que fija
Osinergmin por área de demanda: la norma de tarifas y compensaciones (RCD 217-2013-OS/CD) y el PIT 2025–2029 (RCD
112-2024 y 149-2024, con sus modificatorias). G0 comprobó que «PIT» solo aparece en el código como catálogo de módulos
del libro CAPEX (`set_nueva.py:113-140@51895566`). El PIT comparte con el PIDE la red, los motores, los costos y los
informes, pero **no** su método, su horizonte ni sus formatos. Esta spec crea el producto PIT separado y reutiliza lo
común.

## Usuarios / actores
- Ingeniero de planificación de transmisión de la concesionaria, desde la web.
- Revisor regulatorio que reproduce el expediente.

## Historias de usuario
- H1: Como planificador de transmisión, quiero diagnosticar las SET, los transformadores de potencia y las líneas de
  60 kV y superiores de un área de demanda para cada año del horizonte, y así saber qué elemento incumple y cuándo.
- H2: Como planificador, quiero comparar alternativas de transmisión mutuamente excluyentes por inversión, COyM,
  pérdidas y confiabilidad, para proponer el programa del área.
- H3: Como revisor, quiero que cada cifra del expediente cite la norma, la versión vigente, la fuente y el cálculo que
  la produjo.

## Requisitos funcionales (EARS)
- RF-1: EL SISTEMA tratará el PIT como un estudio distinto del PIDE: su norma, su horizonte, sus formatos y su
  registro se guardan aparte, aunque compartan la red y los costos.
- RF-2: CUANDO el operador elija un área de demanda y un periodo, EL SISTEMA reunirá las SET, los transformadores de
  potencia, las celdas, las líneas y la compensación de ese ámbito desde las fuentes ya importadas, sin mezclar áreas.
- RF-3: CUANDO se pida el diagnóstico, EL SISTEMA calculará para cada año del horizonte la cargabilidad, la tensión y
  el estado ante la contingencia de cada elemento, con la demanda proyectada del área.
- Aclaración de RF-3 y RF-4 (2026-11-15, f4/FIX-PUNTA; condiciones del auditor c3): la referencia del flujo es
  la barra de suministro que da la propia red, su red externa: la red equivalente de la SET de cabecera o el
  punto de entrega del COES. Nunca se elige una barra por su orden:
  - la red externa y la compensación que exporta DIgSILENT llevan la tensión nominal de su barra, para que el
    ámbito por tensión no las deje fuera de la red del área;
  - con una sola red externa, esa es la referencia; con varias, las que la red declara de referencia (tipo de
    barra SL, el `bustp` de DIgSILENT);
  - SI la red no trae ninguna red externa, o trae varias sin declarar su tipo de barra, o una se declara PV o PQ,
    ENTONCES el flujo no se calcula y el error nombra el área y las redes externas, en vez del error del motor.
- RF-4: SI un elemento necesario para el diagnóstico no tiene sus parámetros, ENTONCES EL SISTEMA lo listará con el
  dato que falta y no dará el diagnóstico de ese elemento como completo.
- Aclaración de RF-3 y RF-4 (2026-11-15, f4/PIT-TEN; condiciones del auditor 28): la tensión se diagnostica por
  barra, con el criterio que da la norma, no con un único par de límites:
  - la barra con entrega de suministro cumple la tolerancia de la NTCSE (5.1.2: ±5,0 %; ±7,5 % solo en la red
    secundaria, BT, de los servicios urbano-rurales o rurales) o, en un SER, la de la NTCSER (4.1.2: ±6 % en MT y
    ±7,5 % en BT), por la remisión de la RCD 217-2013, 12.2.1.a;
  - la barra de AT sin entrega no tiene límite propio: se comprueba que el rango de tomas de cada transformador AT/MT
    lleve su barra de MT a esa tolerancia (12.2.1.a);
  - en el Área de Demanda 15, la MAT y la AT sin entrega cumplen la RM 129-2009-MEM/DM (art. 10 y Primera), por la
    remisión del 12.3.2 en la redacción de la RCD 018-2018-OS/CD, sobre la tensión de operación del COES. El caso
    base y el N-1 van con el rango normal; el de emergencia solo si el estudio sustenta su importancia (nota 2 del
    art. 10) en `pit.emergencia_rm129` (`{"aplica": true, "sustento": "…"}`; true sin sustento es un error), con un
    aviso que cita el sustento y la nota. El «≥220 kV» y el «≤138 kV» son una decisión de interpretación con sus dos
    citas en el registro; entre 138 y 220 kV no hay rango de emergencia;
  - la MAT sin entrega de las demás áreas lleva la RM 129-2009 solo como referencia: un aviso visible por barra, con
    su tensión, su rango y su fuente, en el diagnóstico, el expediente y la web, que no cuenta como violación;
  - el nivel sale de la definición «Nivel de Tensión» de la 217-2013; la entrega, el tipo de red, la tensión de
    operación y las tomas, de la red del área o de `pit.barras` del perfil. Lo que falta es un hueco nombrado por
    barra o por transformador, que deja el diagnóstico incompleto y va a los pendientes del expediente, nunca un valor
    supuesto ni la nominal en lugar de la de operación;
  - una regla cuenta como violación si su norma obliga en el registro; si no, avisa. Cambiar el estado jurídico de la
    norma basta para pasar de una cosa a la otra;
  - `pit.limites` del perfil sigue valiendo como respaldo explícito de la barra a la que le falta un dato, con su
    origen y un aviso.
- Aclaración de RF-3 y RF-4 (2026-11-15, f4/FIX-PUNTA; condiciones del auditor c3): la referencia del flujo es
  la barra de suministro que da la propia red, su red externa: la red equivalente de la SET de cabecera o el
  punto de entrega del COES. Nunca se elige una barra por su orden:
  - la red externa y la compensación que exporta DIgSILENT llevan la tensión nominal de su barra, para que el
    ámbito por tensión no las deje fuera de la red del área;
  - con una sola red externa, esa es la referencia; con varias, las que la red declara de referencia (tipo de
    barra SL, el `bustp` de DIgSILENT, o la columna `tipo_barra` del libro de la red);
  - SI la red no trae ninguna red externa, o trae varias sin declarar su tipo de barra, o una se declara PV o PQ,
    ENTONCES el flujo no se calcula y el error nombra el área y las redes externas, en vez del error del motor.
- RF-5: CUANDO el operador defina alternativas, EL SISTEMA evaluará cada una por inversión, COyM, pérdidas y
  confiabilidad, con la misma demanda y el mismo motor.
- Aclaración de RF-5 (2026-11-15, f4/P10c; diseño conforme del auditor 28): las alternativas llegan en un JSON del
  espacio de trabajo, `{"alternativas": [{"nombre", "cambios": [...]}]}`. Cada cambio lleva:
  - `accion` (`alta` o `baja`);
  - `elemento`: en un alta, el elemento nuevo con su `id` y su `tipo`; en una baja, el `id` del que sale;
  - `costo` en un alta: `codigo`, `cantidad` mayor que cero y `unidad` del módulo estándar;
  - `anio` entero, `titular`, `instalacion` y `descripcion`.
  Del mismo JSON sale el programa de la elegida. Un JSON mal formado es un error que nombra el campo (422 en la web).
  Los costos salen de `pit.costos` del perfil, por ámbito y por vigencia (ficheros reemplazables por periodo). Cada
  fuente lleva su fichero, sus metadatos y su sha256, que se comprueba antes de leerla. Sin una fuente vigente, no hay
  comparación y se dice. Un expediente sin comparación o sin una alternativa elegida completa sale «DE DIAGNÓSTICO, no
  presentable a Osinergmin», en su resumen y en el resultado, con el pendiente que lo dice, y nunca como completo,
  aunque no le falte nada más.
- Aclaración de RF-5 (2026-11-15, f4/P-REG; condiciones del auditor 28): el COyM se calcula por elemento, como su
  costo de inversión por el porcentaje de la regla `pit.coym_pct` vigente en cada año del flujo:
  - si la regla da un cuadro (la RCD 163-2021-OS/CD, del 01-05-2021 al 30-04-2027), el porcentaje sale de la
    ubicación (costa, sierra o selva) y del nivel de tensión del elemento;
  - la ubicación es la del elemento (`ubicacion`) o, si no la trae, la del área en el perfil (`pit.areas[].ubicacion`),
    sin valor por defecto;
  - el nivel MT del cuadro vale solo para las celdas de alimentadores de MT dentro de las SET;
  - un transformador toma el nivel de su mayor tensión (Norma Tarifas, 17.3); si es elevador (`funcion`: `elevador`),
    donde la nota de la 163-2021 («lado primario») no coincide, se avisa de la discrepancia entre las dos normas;
  - un año sin porcentaje publicado durante todo el año (los posteriores a abril de 2027, y el propio 2027), un
    elemento sin ubicación o un nivel que el cuadro no da son huecos nombrados: la alternativa queda incompleta, y el
    expediente sale «DE DIAGNÓSTICO» con cada hueco en sus pendientes. No se supone ningún porcentaje.
- RF-6: EL SISTEMA programará cada elemento por año de puesta en servicio, titular y área, con las bajas y los
  reemplazos.
- RF-7: EL SISTEMA guardará en el expediente, por cada regla aplicada, la norma, el artículo o anexo, su estado
  jurídico (vigente comprobada, modificada, prepublicada o no verificada) y su fecha de vigencia.
- RF-8: SI una regla está prepublicada o no verificada, ENTONCES EL SISTEMA no la usará como obligatoria y lo dirá
  en el expediente.
- Aclaración de RF-8 (2026-11-15, f4/P-REG): una regla del registro puede llevar, como dato y no en una nota, sus
  `pendientes` (lo que falta comprobar) y su `verificacion` (fecha, resultado y fuentes con su URL y su sha256). Una
  regla con pendientes se usa con un aviso que los nombra; la verificación va con la regla en la comparación y en
  `reglas_aplicadas.json`.
- RF-9: CUANDO se emita el expediente, EL SISTEMA generará los cuadros del periodo y del área aplicables, con la
  traza de cada celda a su fuente y a su cálculo.
- Aclaración de RF-9 (2026-11-14): los cuadros y formatos aplicables son los que lista la norma vigente del registro
  normativo con su definición transcrita; la lista no se escribe en la spec ni en el código, porque cambia con cada
  periodo y cada modificatoria. Un formato que la norma lista y el registro no transcribe se nombra en el expediente como
  no transcrito, sin inventar sus columnas, y una celda que se deriva de otro formato se escribe vinculada a la celda de
  la que sale (veredicto de 7e sobre el inventario de entregables de Osinergmin; la propuesta n.º 13 del inventario queda
  absorbida aquí).
- Aclaración de RF-9 (2026-11-14, auditor ca: dos potencias y cadena de ventas): los formatos de demanda (F-101 a F-124)
  se llenan con la cadena regulatoria de la norma vigente, no con la suma de la potencia de los alimentadores. De la
  medida del año representativo salen los factores (FC, FCP, FS, FPHMS y FPMWHS); de las ventas proyectadas, la energía
  por barra con las pérdidas estándar de la fijación del VAD vigente de la empresa (su factor de expansión, en cascada
  por nivel; sin fijación vigente, «no transcrita» y nunca la de otra empresa); y de ahí la potencia no coincidente, la
  coincidente con el sistema y la coincidente con el SEIN. La suma de alimentadores sigue siendo la potencia de
  diagnóstico de la red: las dos no se mezclan, y un aviso compara por SET y año la regulatoria con la de diagnóstico,
  con la diferencia en %, sin corregir ninguna. El horizonte de las series sale de la norma registrada.
- RF-10: EL SISTEMA registrará cada observación del regulador con su respuesta y el elemento, el caso o el cálculo
  al que afecta.
- Aclaración de RF-10 (2026-11-14): el registro de observaciones da también el documento de absolución, con cada
  observación, su objeto, su respuesta y la traza de lo que cambió en el expediente por ella (veredicto de 7e; la
  propuesta n.º 19 del inventario queda absorbida aquí).
- Aclaración de RF-9 y RF-10 (orden del usuario del 2026-11-19: «lo que no puede cerrar debe usar los archivos que descargaste de la página de Osinergmin del PIT, en los entregables; lo que publique o no Osinergmin u otras entidades no debería ser una limitación o exigencia para cierre»): la aceptación de los cuadros no espera «datos autorizados por la
  empresa». Se hace con un expediente PUBLICADO por el regulador y ya descargado: el conversor calcula con su propio código
  los cuadros que en el expediente se derivan de sus formatos de entrada (los resúmenes F-119 a F-122 desde F-109 a F-112 y
  F-115 a F-118 del mismo libro), los compara celda a celda con los publicados, deja la referencia con su huella y da la
  causa de cada diferencia; una diferencia sin causa no se emite. El cotejo de una muestra lo hace un revisor distinto del
  implementador (otro modelo o sesión), con su acta y origen «maestro/revisor independiente», y entra como observaciones
  por la vía de RF-10. Los datos reales se leen solo en la corrida de evidencia, fuera de git; las pruebas son sintéticas.
- RF-11: EL SISTEMA no tendrá ningún valor de un área, de una empresa ni de un periodo en el código: van en el
  perfil o en el registro normativo (P13).
- RF-12: CUANDO se lea el libro de la red, EL SISTEMA lo abrirá en cualquier formato de libro (.xlsx, .xlsm, .xls o
  .xlsb) con el lector común y recorrerá todas sus hojas, o solo las que declare el perfil, tomando las que traigan las
  columnas del contrato con la cabecera buscada por contenido, anotando en los avisos cada hoja que no las traiga y
  deteniéndose con las hojas y las cabeceras encontradas si ninguna las trae (orden del usuario del 2026-11-14).
- RF-13: CUANDO se emita el expediente, EL SISTEMA generará el resumen ejecutivo del estudio con la demanda del área,
  la alternativa elegida y la programación de inversiones, con cada cifra tomada del expediente.
- RF-14: CUANDO se emita el expediente, EL SISTEMA acompañará cada sección del estudio con su memoria (criterios,
  metodología, entradas y resultados) y con la relación de los documentos de sustento, cada uno con su descripción, su
  uso y su huella.
- Aclaración de RF-14 (2026-11-15, f4/P10; aceptada por el auditor 28): la relación sigue el num. 5.3 de la Norma
  Tarifas. Cada documento lleva su n.º, su fichero, su tipo, la descripción de su contenido, su aplicación y su volumen
  con sus folios, agrupada por volúmenes y con el foliado consecutivo del num. 5.5; la relación no tiene plantilla.
  La acompaña el «F-000», que no es una plantilla: es el nombre que el regulador da al grupo «Formatos de Información
  General», que la RCD 217-2013 (art. 30.1, Tabla 1 y art. 31) forma con F-001, F-002 y F-003. Se da por cumplido
  cuando el expediente trae los tres, y si falta alguno lleva el hueco «F-000 incompleto: falta F-00x». Se entrega
  como libro aparte, con el nombre que declara su alias en el mapeo de formatos, escrito sobre una copia de la
  plantilla oficial comprobada por su sha256. Si falta un formato, el libro sale con lo que hay y sigue el hueco: el
  regulador observa como incompleto un F-000 a medias, y uno no remitido deja la observación parcialmente subsanada.
  Lo que falta
  en un documento declarado (la descripción, el uso o aplicación, el volumen o los folios) es un hueco nombrado: no
  detiene la emisión, y el expediente sale «incompleto», con cada hueco en los pendientes de su resumen. Un documento
  que nadie declara sigue deteniendo la emisión.
- RF-15: CUANDO se emita el expediente, EL SISTEMA generará el diagrama unifilar de cada alternativa y de cada año, con
  el flujo de potencia de cada línea (F-212), en DXF, y además en DWG si está disponible el convertidor que declare la
  configuración, avisando de cómo obtener el DWG cuando no lo está.
- Aclaración de RF-15 (2026-11-14): decidido por e6 por orden del usuario, con criterio de planeamiento. El DXF es un
  formato abierto que leen AutoCAD y cualquier programa de CAD, y cumple lo que pide el entregable de «ficheros
  compatibles con AutoCAD»; el DWG es cerrado y solo se obtiene con un convertidor externo, por eso es un añadido
  cuando el convertidor está y nunca una condición para entregar. `ezdxf`, que escribe y lee el DXF, es dependencia
  obligatoria del conversor (auditor ca, 2026-11-14): sin ella el expediente quedaría incompleto. El conversor no tiene hoy ningún escritor de DXF (sus
  diagramas son imágenes de `mapa_informe`), así que el unifilar no duplica ninguno. Condiciones de 7e (2026-11-14): el
  convertidor se detecta y nunca se distribuye (su ruta sale del perfil o del PATH, nunca del código); el aviso de que
  falta dice cómo obtener el DWG y queda en el manifiesto del expediente; sin convertidor, o si falla, la entrega queda
  completa con el DXF y nunca sale un DWG vacío. Implementación (2026-11-15, f4): el convertidor se declara en el perfil
  como `pit.convertidor_dwg` o se busca en el PATH como `ODAFileConverter`. El contenido de cada hoja es el del F-212
  (217-2013, art. 37, pdf pág. 64), y el año de ingreso de cada elemento nuevo se marca con la convención de colores
  que esa norma pide «de preferencia», con su leyenda en la hoja; la norma no fija qué color corresponde a cada año.
- RF-16: CUANDO el área tenga transformadores de potencia, EL SISTEMA hará el análisis de los transformadores de
  reserva con el procedimiento vigente del registro normativo, y SI el registro no trae su regla, ENTONCES lo dirá
  nombrando la regla que falta, sin suponerla.
- RF-17: CUANDO el operador pida la modificación del plan de inversiones vigente, EL SISTEMA listará los elementos que
  se eliminan, cambian o agregan, cada uno con su razón, y rehará la demanda y las alternativas con los mismos criterios
  del plan vigente.
- RF-18: EL SISTEMA llenará el formato de fallas e índices de desempeño (F-208) con la estadística de fallas de las
  fuentes importadas, y nombrará el hueco cuando falte un dato.
- RF-19: EL SISTEMA tomará las entradas del PIT de las fuentes de la empresa del espacio (109:RF-25): el libro de la red
  del área, la proyección y las alternativas, sin pedir otra vez lo que la empresa ya cargó; lo que se suba quedará en la
  empresa para los demás módulos. Las alternativas solo entrarán si se nombran. La pestaña dirá de qué carga y de qué
  empresa es la red convertida del espacio, y avisará si no es la del perfil. Un perfil sin
  áreas del PIT no es un error: la lista de áreas sale vacía con su motivo, sin un 422.
- RF-20: EL SISTEMA leerá del registro normativo lo que la Norma Tarifas fija para el PIT, y no de la entrada: los años
  de la programación de la demanda (art. 5.9.4), con el año 1 en el primero pedido, y el horizonte de las alternativas
  (art. 3.14); el factor de potencia de las barras de MT de las SET (art. 12.1.8.c) para la Q de la demanda; el N-1
  solo en los elementos que atienden más de la demanda mínima de la norma en el caso base (art. 12.3.1); y el criterio
  de la comparación, el costo total, el método del COyM y la fuente de la tasa (5.9.3, 11.3, 17.2 y 24.2). Cada una se
  citará en las reglas aplicadas del expediente; lo pedido fuera de la norma se avisará, y sin la regla en el registro
  el cálculo seguirá como antes y lo dirá.
- RF-21: EL SISTEMA tendrá una sola biblioteca normativa, la del programa más una capa del usuario fuera del paquete,
  que añade normas o sustituye la versión de una (lo sustituido se dice, nada se borra), para cualquier empresa,
  estudio y módulo, y con una huella del conjunto que cambia con cualquier fichero. (Orden del usuario, 17-11.)
- RF-22: (amplía RF-21: «actualizable») EL SISTEMA regenerará un registro de la biblioteca desde su fuente oficial ya
  descargada en la carpeta de fuentes normativas, con su generador (la Guía VNR de la RCD 232-2017, los formatos y las
  sombreadas de la RCD 217-2013, el COES y las reconsideraciones): comprobará antes la huella de la fuente y, si no
  coincide, no regenerará y dirá por qué; leerá los libros oficiales solo en copia, nunca con COM; comparará el registro
  nuevo con el vigente y dirá qué reglas entran, salen o cambian antes de escribirlo; y tomará la vigencia del texto de
  la norma (su cláusula; el art. 109 solo si calla). Sin la fuente, dirá cuál falta y dónde ponerla; nunca la descargará.
- RF-23: (revisión de motores del 19-11, hallazgo 1; amplía RF-3, RF-5) CUANDO DIgSILENT esté disponible en el equipo
  (una instalación con su API y el Python que pide, la misma comprobación que la web usa para los demás estudios de
  DIgSILENT) y el operador lo pida, EL SISTEMA encolará `tools/pit_pf.py` en el carril `powerfactory` para el
  diagnóstico y el expediente, con el proyecto de transmisión del área y el caso de estudio de cada año (del pedido o de
  `pit.digsilent` del perfil), y leerá su informe de vuelta con el motor que lo dio; sin proyecto o sin el caso de un
  año, lo dirá antes de encolar. El expediente arma sus cuadros con el motor abierto y lleva al lado el estudio de
  DIgSILENT, y lo dice. La pestaña ofrecerá DIgSILENT cuando esté disponible.
- RF-24: (revisión de motores del 19-11, hallazgo 8; amplía 081:RF-17) SI el caso base de un año no converge, con el
  motor abierto o con DIgSILENT, ENTONCES EL SISTEMA terminará el diagnóstico con el estado «no converge» y su motivo;
  SI el diagnóstico queda incompleto, con el estado «parcial» y su motivo; un diagnóstico entero termina «hecho».

## Requisitos no funcionales
- Universal: cualquier área de demanda y titular. Las pruebas usan al menos dos perfiles sintéticos.
- Determinismo: el mismo caso, con la misma norma y los mismos costos, da el mismo expediente.
- El diagnóstico de varios años es un trabajo en cola, cancelable (P7).

## Casos límite
- Un área con un solo titular y otra con varios.
- Una modificatoria publicada después de iniciar el expediente.
- Un elemento compartido entre dos áreas.
- Un año sin demanda proyectada.

## Fuera de alcance
- Fijar tarifas o peajes.
- La dinámica RMS y los transitorios EMT.
- Presentar el expediente al regulador: la presentación la hace la empresa.
- Declarar el expediente «aprobado por Osinergmin».

## Criterios de finalización
Cada RF citado por una prueba (`grep "107:RF-"`). Se reproduce un cuadro de un PIT publicado, autorizado por la
empresa, fila por fila, con sus diferencias explicadas. Un revisor independiente coteja una muestra de celdas.

## Decisiones (2026-11-14)
Tomadas por delegación del usuario (`D:/csg/G0_PLAN_MAESTRO/G1_DECISIONES_RECOMENDADAS.md`, punto 3):
- Primer caso real: el área de demanda de la primera empresa de prueba (sus datos, solo en su perfil local). El número de área y el titular van en su perfil, nunca en el
  código (P13); es un caso de prueba, no el diseño.
- Motor: el abierto (pandapower) por defecto y DIgSILENT si hay licencia, con la misma matriz de capacidades. Lo que un
  motor no puede calcular se dice, y cada resultado nombra el motor que lo dio. El PIT usa el modelo de transmisión del
  área, no el de MT.
- Ampliación del 2026-11-14 (veredicto de 7e, `VEREDICTO_INVENTARIO_OSINERGMIN_7e.md`, con su corrección de las
  20:20): de los RF propuestos en el inventario de entregables de Osinergmin, el 13 (formatos) y el 19 (absolución) se
  absorben como aclaraciones de RF-9 y RF-10; el 14, el 15, el 16 (unifilar, que sale de la espera por decisión de e6),
  el 17, el 18 y el 20 entran, en ese orden, como RF-13 a RF-18. La numeración vigente no cambia.
- RCD 199-2026: entra en el registro normativo como no verificada y sin reglas hasta que se pueda leer y transcribir
  (tarea T3 de `tasks.md`); mientras tanto no se usa como obligatoria (RF-8).
