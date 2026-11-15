# Spec 107 — Plan de Inversiones en Transmisión (PIT) del sistema secundario y complementario

Estado: aprobada · Fecha: 2026-11-14 · Origen: Plan Maestro v1.6, BP-17, y orden del usuario del 2026-11-14:
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
- RF-5: CUANDO el operador defina alternativas, EL SISTEMA evaluará cada una por inversión, COyM, pérdidas y
  confiabilidad, con la misma demanda y el mismo motor.
- RF-6: EL SISTEMA programará cada elemento por año de puesta en servicio, titular y área, con las bajas y los
  reemplazos.
- RF-7: EL SISTEMA guardará en el expediente, por cada regla aplicada, la norma, el artículo o anexo, su estado
  jurídico (vigente comprobada, modificada, prepublicada o no verificada) y su fecha de vigencia.
- RF-8: SI una regla está prepublicada o no verificada, ENTONCES EL SISTEMA no la usará como obligatoria y lo dirá
  en el expediente.
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
  completa con el DXF y nunca sale un DWG vacío.
- RF-16: CUANDO el área tenga transformadores de potencia, EL SISTEMA hará el análisis de los transformadores de
  reserva con el procedimiento vigente del registro normativo, y SI el registro no trae su regla, ENTONCES lo dirá
  nombrando la regla que falta, sin suponerla.
- RF-17: CUANDO el operador pida la modificación del plan de inversiones vigente, EL SISTEMA listará los elementos que
  se eliminan, cambian o agregan, cada uno con su razón, y rehará la demanda y las alternativas con los mismos criterios
  del plan vigente.
- RF-18: EL SISTEMA llenará el formato de fallas e índices de desempeño (F-208) con la estadística de fallas de las
  fuentes importadas, y nombrará el hueco cuando falte un dato.

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
