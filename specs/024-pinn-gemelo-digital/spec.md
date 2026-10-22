# Spec 024 — PINN como oráculo y gemelo digital de la red calibrada

Estado: aprobada el 2026-10-21, con el cambio del mismo día (RF-39 a RF-53: aprendizaje autónomo, propuestas e implementación propias, diagnóstico y plan por etapas); plan y tareas de la primera entrega (búfer de episodios) aprobados · Fecha: 2026-10-21

## Contexto y objetivo

El usuario pidió que el aprendizaje acompañe cada trabajo completo, desde una fuente nueva hasta
su implementación y aceptación en DIgSILENT PowerFactory, tanto para un alimentador como para
dos o más alimentadores, enlaces, transferencias y obras. El objetivo no es que una red neuronal
memorice una maniobra aislada, sino construir un gemelo digital local que acumule episodios
auditables, aprenda la relación entre topología, inyecciones y estado eléctrico, y nunca sustituya
la validación nativa.

El caso inicial dorado de topología —no de aceptación operativa— es el proyecto
`20261015-170359_IGEA_IN111_TA225`: el corredor manual del
enlace se conserva, el nodo 3092 y sus ramales quedan en 22,9 kV, el nodo 3091 y la red hacia
IN111 permanecen en 10 kV, y la frontera se corrige cerrando `SEC_1091_1055021(1)`. Después de
guardar y reabrir PowerFactory, el flujo converge; 3091 queda en 0,9522 p.u., 3092 en 0,9604 p.u.
y la mínima global es 0,8683 p.u. en `SE41154_BT`. Esta última condición debe aprenderse como
violación o alerta, no como solución operativamente aceptada solo porque el flujo converge.

Una PINN combina ejemplos con una pérdida física. En esta spec, la parte física penaliza los
residuos de balance nodal y flujo de potencia; la parte supervisada aprende exclusivamente de
resultados nativos trazables. El gemelo digital agrega identidad, tiempo, topología, medidas,
incertidumbre, modelo y realimentación: un modelo sin sincronización ni evidencia no se denomina
gemelo digital.

## Principios de diseño

1. **DIgSILENT es la referencia.** El PINN acelera, prioriza y detecta; PowerFactory confirma.
2. **Aprender por episodios, no por archivos sueltos.** Cada ejecución conserva entrada,
   transformación, estado antes/después, resultados y aceptación.
3. **Separar éxito técnico y aceptación.** Convergencia, persistencia, límites eléctricos y
   aprobación operativa son estados distintos.
4. **No entrenar con una instantánea.** Una maniobra aceptada inicia una familia de escenarios;
   por sí sola no permite generalizar.
5. **Fallar cerrado.** Datos ambiguos, topología no identificada, flujo inválido, deriva o entrada
   fuera de distribución impiden usar la predicción.
6. **Aprendizaje autónomo con puertas.** Los modelos aprenden solos de cada trabajo, eligen qué
   más necesitan aprender y se reentrenan sin que nadie lo pida; un modelo nuevo se promueve
   solo si supera las puertas nativas y de calidad, y todo cambio queda registrado y se puede
   deshacer.

## Usuarios y actores

- Ingeniero de planificación desde la web o el CLI.
- PowerFactory como fuente de verdad de simulación y persistencia.
- Adaptadores TXT, MDB, VNR-GIS y futuros orígenes como productores de procedencia.
- Oráculo independiente de validación, cuando exista, sin reemplazar la aceptación nativa.
- Registro local de episodios y modelos.

## Historias de usuario

- H1: Como ingeniero quiero que todo trabajo aceptado deje datos entrenables sin volver a
  reconstruir manualmente qué fuente, red, caso y variación lo produjeron.
- H2: Como ingeniero quiero estimaciones con incertidumbre para alimentadores sin medidor,
  coherentes con la barra de su SET y diferenciadas de una medida real.
- H3: Como ingeniero quiero localizar tramos faltantes, cargas mal asignadas y parámetros
  incompatibles mediante residuos físicos y evidencia temporal.
- H4: Como ingeniero quiero reproducir un día o mes y comparar el gemelo con curvas de cabecera,
  barra y alimentador.
- H5: Como ingeniero quiero evaluar uno o varios alimentadores, enlaces y transferencias sin que
  el PINN confunda topologías o niveles de tensión.
- H6: Como ingeniero quiero que intentos fallidos o revertidos ayuden a reconocer estados
  inválidos, pero nunca se presenten como ejemplos positivos.

## Arquitectura

### A. Capturador de episodios

Se integra en las fronteras ya existentes del flujo fuente → modelo canónico → DGS → proyecto →
casos/variaciones → cálculo → guardado → reapertura. No modifica PowerFactory para obtener más
datos durante una acción normal; observa los artefactos y lecturas que ya exige la aceptación.

### B. Búfer de experiencias

Es una memoria local, inmutable y direccionada por contenido. Conserva el manifiesto y los
resultados pequeños en JSON/SQLite, y matrices grandes en un formato binario versionado. Un
índice puede reconstruirse desde los artefactos; la base de datos no es la única evidencia.

El búfer se divide en:

- `accepted`: guardado, reabierto, convergente y dentro de las puertas declaradas;
- `converged_with_violations`: converge, pero tiene subtensión, sobrecarga u otra infracción;
- `rejected`: no converge, no persiste, tiene procedencia ambigua o falla una puerta;
- `counterfactual`: escenario sintético generado desde un episodio aceptado y validado en
  PowerFactory, sin afirmar que ocurrió en operación;
- `quarantine`: incompleto, corrupto, incompatible o pendiente de revisión.

Los intentos revertidos no se eliminan del aprendizaje diagnóstico: se guardan como `rejected`,
con la razón y el estado restaurado, y quedan excluidos del objetivo supervisado de solución.

### C. Generador de escenarios

Desde un episodio dorado produce perturbaciones acotadas de P/Q, tensión de fuente, estados de
maniobra, indisponibilidades y configuración de enlaces. Solo publica escenarios cuyo modelo
nativo se pueda ejecutar y releer. Las particiones de entrenamiento, validación y prueba se hacen
por familia topológica y periodo, no por filas aleatorias, para evitar fuga de la misma maniobra.

### D. Oráculo PINN/GNN

La entrada contiene grafo eléctrico, parámetros, estados de interruptores, niveles nominales,
inyecciones y condiciones de contorno. La salida contiene magnitud/ángulo de tensión, P/Q por
rama, pérdidas, cargabilidad e incertidumbre. La función de pérdida combina:

- error frente a PowerFactory en ejemplos aceptados o contrafactuales válidos;
- balance nodal de P y Q;
- ecuaciones de rama y transformador;
- condiciones de fuente y estados abierto/cerrado;
- penalización por mezclar islas o bases de tensión incompatibles;
- calibración de incertidumbre y consistencia entre topologías.

Se permite una GNN informada por la física cuando el tamaño o la variación topológica hagan
inadecuada una red densa. “PINN” designa aquí el contrato físico, no una arquitectura única.

### D2. Qué aprende cada modelo

Usuario, 2026-10-21: «eso es lo que debe aprender la RNN, PINN y, si es posible, se debe
implementar otro modelo si se requiere». Lo que se aprende es la planificación del PIDE completa,
no solo el flujo. Cada tarea tiene el modelo que le conviene; todos comparten el búfer y ninguno
sustituye a DIgSILENT:

| Tarea | Modelo | Aprende de | Entrega |
| --- | --- | --- | --- |
| Estado eléctrico de una topología | PINN/GNN (D) | flujos nativos de los tres casos | tensiones, flujos, pérdidas, cargabilidad e incertidumbre |
| Evolución en el tiempo | RNN (LSTM o GRU) informada por la física | curvas de cabecera, barra y alimentador del mes | demanda y estado hora a hora o cada 15 min; pseudo-medidas (RF-20 a RF-22) |
| Elección de alternativas del PIDE | modelo de ordenamiento sobre las alternativas, con el PINN como evaluador rápido dentro de un optimizador | episodios de «Con proyecto» con su alternativa, coste y cumplimiento (RF-32 a RF-34) | alternativas candidatas ordenadas por cumplimiento y coste total |
| Confiabilidad | modelo de regresión sobre los índices nativos (spec 012) | índices de los episodios | estimación previa de SAIFI y SAIDI por alternativa |

El tipo concreto de cada modelo se fija en su plan y se cambia si las métricas lo piden: el
contrato es la tarea, su entrada, su salida y sus puertas, no la arquitectura.

### E. Entrenador y registro de modelos

El entrenamiento es offline, local, reproducible y cancelable. PyTorch será una dependencia
opcional `ml`; el conversor y PowerFactory deben funcionar sin instalarla. Cada modelo registra
versión del código, semilla, consulta exacta del búfer, huellas de episodios, normalización,
hiperparámetros, métricas, límites conocidos y compatibilidad de esquema.

### F. Servicio del gemelo

Solo carga modelos promovidos. Una inferencia informa modelo, dominio, incertidumbre y puertas.
Si la entrada está fuera de distribución, la topología no fue entrenada o la incertidumbre excede
el perfil, deriva el caso a PowerFactory y no entrega una respuesta operativa automática.

## Contrato mínimo de episodio

Cada episodio tendrá, como mínimo:

- `episode_id`, fecha, versión de esquema y clasificación del búfer;
- `source_run_id`, modo, ficheros, SHA-256, `source_fingerprint` y versión canónica;
- proyecto, carpeta, huella nativa, caso, escenario y variaciones activas ordenadas;
- alimentadores implicados, cabeceras, barras, enlaces y frontera de transferencia;
- grafo con identidad estable por objeto, fases, bases de tensión, tipos y parámetros;
- geometría o huella del trazado cuando una obra dependa de una modificación manual;
- P/Q y tensión de las fuentes; P/Q de cargas, generación y compensación;
- estados de líneas, acopladores, interruptores y elementos fuera de servicio;
- resultados nativos por barra/rama/equipo y estado de `ComLdf`;
- evidencia de escritura, reapertura, relectura, convergencia y límites eléctricos;
- acción solicitada, cambios efectivos, reversión si ocurrió y decisión de aceptación;
- unidades explícitas, valores ausentes explícitos y procedencia de cada bloque.

Una variación, una respuesta web o un nombre de proyecto no bastan como etiqueta. Sin reapertura
y relectura, el episodio no puede ser `accepted`.

## Evaluación por caso

Usuario, 2026-10-21: «en todas se evalúa flujos de potencia, de ahí salen los balances,
cargabilidad, índices de confiabilidad»; «caso base debe ser como está el sistema, sin proyecto
acepta las modificaciones manuales o automáticas, con proyecto sí se debe tener en cuenta el
cumplimiento de la norma, pérdidas, confiabilidad, con nuevas obras».

Lo que se mide es igual en los tres casos: el flujo de potencia nativo y, de él, el balance de
potencia y energía (pérdidas), la cargabilidad de conductores y transformadores, las tensiones y
los índices de confiabilidad (spec 012). Lo que cambia es qué se exige al resultado:

| Caso | Qué representa | Episodio aceptado si | Fuera de norma |
| --- | --- | --- | --- |
| «Caso base» | La red tal como está, igual al archivo de origen (spec 015) | verificado frente al origen, flujo convergido, reabierto y releído | diagnóstico del estado real; no rechaza |
| «Sin proyecto» | Caso base calibrado con los cambios manuales del operador y los automáticos (calibración, transformadores NTP, bancos, obras de «Sin proyecto») | además, cuadra con la medida de cabecera o barra | diagnóstico; un cambio manual es intencional y no rechaza |
| «Con proyecto» | «Sin proyecto» con cargas nuevas y obras | además, cumple la norma de calidad de su sistema y no empeora pérdidas ni confiabilidad frente a «Sin proyecto» | `converged_with_violations` |

La norma de cada sistema (NTCSE o NTCSER) y sus límites salen de la estructura y del perfil de la
empresa (P13); la cargabilidad de transformadores, de la NTP 370.400 del perfil (≤ 80 %).

### «Con proyecto»: planificación según el PIDE

Usuario, 2026-10-21: «con proyecto debe cumplir criterios y metodología de planificación en redes
eléctricas PIDE […] todo esto se debe implementar según el anexo y criterios de priorización de
alternativas de solución para cumplir las normas sin exceder; se debe optimizar».

El PIDE es el Plan de Inversiones en Distribución Eléctrica que la concesionaria presenta a
Osinergmin; sus criterios están en los Términos de Referencia del VAD (R033-2026-OS-CD, Anexo
N.º 6), resumidos en `docs/superpowers/plans/2026-09-23-plataforma-planificacion-pide.md`.
Las alternativas de solución, de menor a mayor intervención, son:

| Orden | Alternativa | Spec que la construye en DIgSILENT |
| --- | --- | --- |
| 1 | Bancos de condensadores | 011, 017 |
| 2 | Reguladores de tensión | 011, 017 |
| 3 | Cambio de sección del conductor | 011, 017 |
| 4 | Nueva terna (refuerzo en paralelo) | 016, 017 |
| 5 | Refuerzo de red: enlace, transferencia, migración de tensión | 016 |
| 6 | Nueva SED o cambio de transformador | 020 |
| 7 | Nuevo alimentador | por especificar |
| 8 | Nueva SET o transformador de SET | por especificar |

El orden y los parámetros económicos van en el perfil, no en el código. Optimizar es elegir la
combinación que cumple la norma con el menor coste total capitalizado: inversión más valor presente
de pérdidas y de energía no suministrada, con la tasa, el valor de la ENS y la vida útil del Anexo
N.º 6 tomados del perfil. «Sin exceder» quiere decir que no se sobredimensiona: una alternativa que
cumple con margen de sobra pierde frente a otra más barata que también cumple.

## Requisitos funcionales (EARS)

### Captura universal

- RF-1: CUANDO una ejecución recorra desde una fuente hasta PowerFactory, EL SISTEMA emitirá un
  episodio ligado al `source_run_id`, huella de fuente, proyecto y resultado nativo.
- RF-2: DONDE intervengan uno, dos o más alimentadores, enlaces o transferencias, EL SISTEMA
  conservará la identidad y orientación de cada red y la frontera abierta que separa fuentes.
- RF-3: CUANDO exista trazado o conexión manual, EL SISTEMA conservará su huella antes y después;
  una diferencia no autorizada bloqueará el episodio positivo.
- RF-4: SI una acción se revierte, no converge o no persiste al reabrir, ENTONCES EL SISTEMA la
  clasificará como `rejected` y conservará la causa y la restauración.
- RF-5: SI un episodio de «Con proyecto» converge pero viola los límites de la norma de su
  sistema o empeora pérdidas o confiabilidad frente a «Sin proyecto», ENTONCES EL SISTEMA lo
  clasificará como `converged_with_violations`, nunca como aceptación operativa.
- RF-32: CUANDO un episodio de «Con proyecto» incluya obras, EL SISTEMA registrará la alternativa
  del PIDE de cada obra (tabla de «Con proyecto»), su tramo o equipo, su coste y los indicadores
  que pide el Anexo N.º 6 (VAN, TIR y período de retorno) tomados de la evaluación nativa.
- RF-33: EL SISTEMA ordenará las alternativas de solución por el criterio del perfil: primero la
  que cumple la norma; entre las que cumplen, la de menor coste total capitalizado (inversión,
  pérdidas y energía no suministrada en valor presente).
- RF-34: SI dos alternativas cumplen la norma, ENTONCES EL SISTEMA marcará como sobredimensionada la
  de mayor coste; un episodio con una obra sobredimensionada no será objetivo positivo del oráculo.
- RF-35: EL SISTEMA podrá proponer con el oráculo alternativas candidatas en ese orden, pero cada
  una se construirá y confirmará en DIgSILENT antes de aceptarse (principio 1, RF-23).
- RF-36: EL SISTEMA aprenderá, a partir de los episodios de «Con proyecto», a proponer la
  alternativa del PIDE que cumple la norma con el menor coste total, y la confirmará en DIgSILENT
  antes de darla por buena (RF-35).
- RF-37: EL SISTEMA tendrá un modelo temporal (RNN) que reproduzca la demanda y el estado de la
  red en el mes de análisis, para evaluar las alternativas en el instante crítico y no solo en la
  máxima.
- RF-38: DONDE una tarea no se resuelva con la PINN o la RNN con las métricas del perfil, EL
  SISTEMA admitirá otro modelo con el mismo contrato de tarea, entrada, salida, puertas y registro
  (E), sin cambiar el búfer.
- RF-28: EN todos los casos, EL SISTEMA guardará en el episodio el flujo de potencia nativo y lo
  que sale de él: balance de potencia y energía con sus pérdidas, cargabilidad de conductores y
  transformadores, tensiones e índices de confiabilidad (spec 012), con la misma definición.
- RF-29: CUANDO el episodio sea del «Caso base» o de «Sin proyecto», EL SISTEMA guardará las
  violaciones de la norma como diagnóstico del estado real y no lo rechazará por ellas; un cambio
  manual del operador en «Sin proyecto» se aceptará siempre como intencional.
- RF-30: CUANDO el episodio sea de «Sin proyecto», EL SISTEMA exigirá además que la calibración
  cuadre con la medida de cabecera o de barra para clasificarlo `accepted`.
- RF-31: CUANDO el episodio sea de «Con proyecto», EL SISTEMA evaluará la norma de calidad del
  sistema eléctrico (NTCSE o NTCSER, de la estructura) con sus límites del perfil, y comparará
  pérdidas e índices de confiabilidad con el «Sin proyecto» del mismo proyecto.

### Búfer

- RF-6: EL SISTEMA escribirá episodios de forma atómica, inmutable e idempotente por huella.
- RF-7: EL SISTEMA impedirá mezclar episodios con esquema, unidades, procedencia o identidad de
  proyecto incompatibles sin una migración explícita.
- RF-8: EL SISTEMA permitirá consultar el búfer por proyecto, alimentador, topología, periodo,
  fuente, clase de resultado y versión de PowerFactory.
- RF-9: EL SISTEMA mantendrá una cuarentena y validará integridad, cardinalidad, unidades,
  referencias, balance y disponibilidad antes de declarar entrenable un episodio.
- RF-10: EL SISTEMA conservará suficientes episodios de topologías y periodos anteriores para
  evitar olvido catastrófico; una política de muestreo equilibrará proyectos, estados normales,
  violaciones y rechazos sin borrar la evidencia original.

### Generación y aprendizaje

- RF-11: EL SISTEMA no entrenará un oráculo con una sola operación; generará y validará en
  PowerFactory una matriz configurable de escenarios alrededor de episodios aceptados.
- RF-12: EL SISTEMA separará entrenamiento, validación y prueba por familia topológica y tiempo,
  evitando que variantes de la misma maniobra aparezcan en particiones distintas.
- RF-13: EL SISTEMA entrenará únicamente con una consulta inmutable del búfer y publicará esa
  consulta junto con la versión del modelo.
- RF-14: EL SISTEMA podrá usar `rejected` y `converged_with_violations` para clasificación,
  detección fuera de distribución y aprendizaje de barreras, pero no como objetivo positivo de
  tensión o maniobra aceptada.
- RF-15: EL SISTEMA dará incertidumbre y residuos físicos por predicción, no solo valores.
- RF-16: SI las métricas contra PowerFactory o los residuos físicos superan el perfil, ENTONCES
  EL SISTEMA rechazará la promoción del modelo.
- RF-17: CUANDO llegue nueva evidencia, EL SISTEMA entrenará un candidato con repetición del
  búfer histórico; el modelo promovido solo cambia por la promoción de RF-42, registrada.

### Aprendizaje autónomo y propuestas propias

Usuario, 2026-10-21: «necesito que los modelos sean autodidactas, autoaprendizaje, que sean
escalables, autoadaptables, cada vez aprendan más y sean capaces de proponer proyectos u obras
por su propia cuenta».

- RF-39: CUANDO se registre un episodio entrenable nuevo, EL SISTEMA programará por sí mismo el
  reentrenamiento del candidato, sin que el operador lo pida.
- RF-40: EL SISTEMA elegirá por sí mismo los escenarios donde su incertidumbre, su residuo físico
  o su error frente a DIgSILENT sean mayores, los construirá y simulará en DIgSILENT sobre una
  copia del proyecto y los añadirá al búfer como episodios `counterfactual` (aprendizaje activo).
- RF-41: MIENTRAS el aprendizaje activo use DIgSILENT, EL SISTEMA respetará el presupuesto de
  licencia del perfil y cederá el turno a cualquier trabajo del operador (spec 019).
- RF-42: CUANDO un candidato supere las puertas frente a DIgSILENT sin empeorar los casos dorados,
  EL SISTEMA lo promoverá solo, registrará qué cambió y con qué episodios, y conservará el modelo
  anterior para volver a él.
- RF-43: SI EL SISTEMA detecta deriva (medidas nuevas que no reproduce, topología nunca vista o
  demanda fuera de lo aprendido), ENTONCES se adaptará con un ajuste sobre lo nuevo y repetición
  del histórico, sin reentrenar desde cero.
- RF-44: EL SISTEMA aprenderá de cualquier número de alimentadores, sistemas eléctricos y
  empresas con los mismos modelos, que generalizan a topologías nuevas por la estructura del
  grafo y no por un modelo por red.
- RF-45: EL SISTEMA buscará por sí mismo, en «Sin proyecto» y con la demanda proyectada,
  incumplimientos de la norma, pérdidas y confiabilidad, y propondrá proyectos u obras del PIDE
  (alternativa, ubicación y dimensión) ordenados por coste total, sin que el operador los pida.
- RF-46: EL SISTEMA construirá y verificará cada propuesta propia en DIgSILENT sobre una copia
  del proyecto antes de mostrarla al operador, con su evidencia (norma, pérdidas, confiabilidad,
  coste e indicadores del Anexo N.º 6).
- RF-47: CUANDO una propuesta propia quede verificada en la copia (RF-46), EL SISTEMA la
  implementará solo en «Con proyecto» del proyecto real, en una variación propia marcada como
  autónoma, sin esperar aprobación (usuario, 2026-10-21: «la implementa sola»).
- RF-47b: EL SISTEMA no modificará el «Caso base» ni lo hecho por el operador en «Sin proyecto» o
  en «Con proyecto» al implementar una propuesta propia; ante un conflicto con un cambio manual,
  gana el manual y la propuesta queda sin implementar, con aviso.
- RF-47c: EL SISTEMA avisará al operador de cada implementación autónoma con su evidencia y le
  permitirá deshacerla desactivando o borrando su variación.
- RF-48: CUANDO el operador acepte, rechace o modifique una propuesta, EL SISTEMA guardará esa
  decisión como episodio y aprenderá de ella.

Usuario, 2026-10-21: «además debe ser capaz de diagnosticar la situación actual de las redes y
pensar cómo planificar».

- RF-49: EL SISTEMA diagnosticará por sí mismo la situación actual de cada red («Caso base» y
  «Sin proyecto»): tensiones, cargabilidad, pérdidas y confiabilidad frente a la norma de su
  sistema, con la ubicación de cada problema.
- RF-50: EL SISTEMA explicará la causa probable de cada problema del diagnóstico (conductor
  insuficiente, factor de potencia bajo, longitud del alimentador, transformador sobrecargado,
  falta de enlace o de fuente) con la evidencia del flujo que la sostiene.
- RF-51: EL SISTEMA proyectará la demanda en el horizonte del plan del perfil y determinará en
  qué año cada red deja de cumplir la norma.
- RF-52: EL SISTEMA propondrá un plan por etapas: qué obra del PIDE hace falta, dónde y en qué año,
  de modo que cada año cumpla la norma con el menor coste total del horizonte, sin adelantar obras
  que aún no hacen falta.
- RF-53: EL SISTEMA verificará en DIgSILENT cada año del plan propuesto antes de mostrarlo.

### Oráculo y gemelo digital

- RF-18: Dadas inyecciones, fuentes y topología, EL SISTEMA estimará tensiones, flujos, pérdidas
  y cargabilidad con su incertidumbre.
- RF-19: SI la entrada no está cubierta por el dominio del modelo, ENTONCES EL SISTEMA no
  extrapolará como verdad y solicitará cálculo nativo.
- RF-20: EL SISTEMA reproducirá periodos horarios o de 15 minutos y comparará el gemelo con
  medidas de cabecera, barra y alimentador.
- RF-21: SI la desviación temporal supera el perfil, ENTONCES EL SISTEMA localizará instante,
  alimentador y contribución al residuo, y confirmará los candidatos en PowerFactory.
- RF-22: DONDE falte medición de alimentador y exista medida de barra, EL SISTEMA podrá generar
  pseudo-medidas con intervalo, respetando potencia instalada, clientes fijos, pérdidas y suma de
  barra; las marcará siempre como estimadas.
- RF-23: EL SISTEMA podrá ordenar candidatos de reconstrucción o reconfiguración por residuo,
  incertidumbre y violaciones; no escribirá una maniobra recomendada sin simulación y aceptación.

### Caso dorado IN111–TA225

- RF-24: EL SISTEMA incluirá un episodio dorado donde 3091 pertenece a la componente IN111 de
  10 kV y 3092 a la componente transferida TA225 de 22,9 kV; 3091 y 3092 no tendrán continuidad
  eléctrica entre sí, y la componente transferida se alimentará por el enlace existente a TA225.
- RF-25: EL SISTEMA verificará que `Enlace_TA225_IN111` conserva extremos, servicio y huella del
  trazado manual; cambiar su conexión para ajustarlo al nodo 3092 será un fallo.
- RF-26: EL SISTEMA conservará como etiqueta la subtensión de 0,8683 p.u. observada tras la
  reapertura y exigirá que el oráculo la detecte; la convergencia no podrá ocultarla.
- RF-27: EL SISTEMA comprobará el caso dorado después de cerrar y abrir una sesión nativa nueva,
  no solo dentro del proceso que escribió la variación.

## Requisitos no funcionales

- Universal: sin empresa, alimentador, tensión o topología fija; todo lo particular va en datos
  o perfil.
- Local: fuentes, episodios y modelos no salen de la máquina.
- Reproducible: semilla, software, consulta y huellas fijadas.
- Auditable: toda predicción remite a modelo, episodios y ecuaciones/residuos evaluados.
- Modular: captura, búfer, escenarios, entrenamiento, registro e inferencia tienen contratos
  separados.
- Seguro: ninguna recomendación escribe directamente en PowerFactory.
- Compatible: el núcleo funciona sin PyTorch; `ml` es opcional y no comparte proceso con la API
  nativa si sus dependencias binarias fueran incompatibles.
- Escalable: el búfer admite muestreo incremental y no duplica matrices idénticas.

## Orden de entrega

1. Contrato, validador y búfer de episodios.
2. Captura automática desde flujos ya aceptados y caso dorado IN111–TA225.
3. Generador de escenarios y matriz PowerFactory con límites de tiempo y cancelación.
4. Oráculo de flujo estático con incertidumbre y rechazo fuera de distribución.
5. Gemelo temporal con curvas reales.
6. Pseudo-medidas, diagnóstico de red y ordenamiento de maniobras.

## Casos límite

Proyecto sin calibración válida; sistema sin medidores; barra sin medidor; islas; red mallada;
dos fuentes unidas indebidamente; fases incompletas; topología manual; variación que no persiste;
versiones distintas de PowerFactory; cambio de tipo o unidad; episodio duplicado; entrenamiento
interrumpido; modelo antiguo ante un esquema nuevo; topología nunca vista; valores NaN; flujo que
converge con subtensión; deriva temporal; búfer insuficiente o desbalanceado.

## Fuera de alcance

Sustituir PowerFactory en cortocircuito, N-1, confiabilidad o aceptación; control autónomo en
tiempo real de la red en operación; promover un modelo sin pasar las puertas (RF-42); predicción de demanda de largo plazo; enviar datos a servicios externos.

## Criterios de finalización

- Cada RF tiene prueba y evidencia enlazada.
- El esquema del episodio valida casos de uno y varios alimentadores, enlaces y transferencias.
- La captura reconstruye la cadena fuente–PowerFactory y distingue comando, escritura,
  reapertura, convergencia, límites y aceptación.
- El caso IN111–TA225 se captura y se reproduce sin cambiar el trazado manual.
- Existe una matriz con múltiples escenarios nativos; no se acepta entrenamiento con el único
  episodio de hoy.
- El modelo supera umbrales definidos antes de evaluar el conjunto de prueba y rechaza topologías
  fuera de distribución.
- Se demuestra que la repetición del búfer evita degradación material en casos dorados antiguos.
- Ruff pasa sobre el alcance funcional modificado; pruebas focales y aceptación nativa quedan
  registradas por separado.

## Decisiones pendientes para el plan

- Tamaño inicial de la matriz de escenarios por familia topológica y presupuesto de licencia.
- Umbrales del modelo frente a DIgSILENT: se propone que el error de tensión no supere la décima
  parte de la banda de la norma del sistema (±0,005 p.u. con ±5 %); los límites eléctricos no se
  deciden aquí, salen de la norma (RF-31).
- Tolerancia de tensión de la NTCSER en el perfil de Electro Dunas (hoy solo la de la NTCSE).
- Parámetros económicos del Anexo N.º 6 en el perfil (tasa, valor de la ENS, vida útil, costes
  unitarios por alternativa), comprobados contra el texto vigente de R033-2026-OS-CD.
- Nuevo alimentador y nueva SET: hoy ninguna spec los construye; quedan para una spec propia.
- Formato binario final de matrices y política de retención/copia de seguridad del búfer.
- Sistemas dorados adicionales a IN111–TA225 y orden de incorporación.

## Sustento científico verificado

Fundamentos PINN y aprendizaje informado por física:

- Raissi, M., Perdikaris, P., y Karniadakis, G. E. (2019). *Physics-informed neural networks: A
  deep learning framework for solving forward and inverse problems involving nonlinear partial
  differential equations*. Journal of Computational Physics, 378, 686–707.
  https://doi.org/10.1016/j.jcp.2018.10.045
- Karniadakis, G. E., et al. (2021). *Physics-informed machine learning*. Nature Reviews Physics,
  3, 422–440. https://doi.org/10.1038/s42254-021-00314-5

Sistemas eléctricos de potencia:

- Zamzam, A. S., y Sidiropoulos, N. D. (2020). *Physics-Aware Neural Networks for Distribution
  System State Estimation*. IEEE Transactions on Power Systems.
  https://doi.org/10.1109/TPWRS.2020.2988352
- Wang, W., y Yu, N. (2022). *Estimate Three-Phase Distribution Line Parameters With
  Physics-Informed Graphical Learning Method*. IEEE Transactions on Power Systems.
  https://doi.org/10.1109/TPWRS.2021.3134952
- Ngo, Q.-H., Nguyen, B. L. H., Vu, T. V., Zhang, J., y Ngo, T. (2024). *Physics-informed
  graphical neural network for power system state estimation*. Applied Energy, 358, 122602.
  https://doi.org/10.1016/j.apenergy.2023.122602
- Falas, S., Asprou, M., Konstantinou, C., y Michael, M. K. (2025). *Robust Power System State
  Estimation Using Physics-Informed Neural Networks*. IEEE Transactions on Industrial
  Informatics. https://doi.org/10.1109/TII.2025.3582293

Gemelos digitales y actualización continua:

- Somda, B., y Liu, C.-C. (2024). *Digital Twin for Resilient Power Distribution Systems*.
  ISAP 2024. https://doi.org/10.1109/ISAP63260.2024.10744374
- Sifat, M. M. H., Das, S. K., y Choudhury, S. M. (2024). *Design, development, and optimization
  of a conceptual framework of digital twin electric grid using systems engineering approach*.
  Electric Power Systems Research, 226, 109958.
  https://doi.org/10.1016/j.epsr.2023.109958
- Zhi, H., Mao, R., Hao, L., Chang, X., Guo, X., y Ji, L. (2024). *Digital Twin for Modern
  Distribution Networks by Improved State Estimation with Consideration of Bad Date
  Identification*. Electronics, 13(18), 3613.
  https://doi.org/10.3390/electronics13183613
- Cui, K., Gao, T., y Shi, D. (2025). *Physics-Informed Bayesian Neural Network for Li-Ion
  Battery Continual Learning*. IEEE ICPS 2025.
  https://doi.org/10.1109/ICPS65515.2025.11087868

Tesis sobre transferencia y reconfiguración que sustentan la necesidad de conservar frontera,
radialidad y estados de maniobra en cada episodio:

- Qiao, L. (2019). *Load Pickup and Feeder Reconfiguration of Distribution Networks* [Tesis de
  maestría, University of Washington].
  https://labs.ece.uw.edu/real/Library/Thesis/Qiao_Linyue.pdf
- Ghaweta, A. (2019). *Optimal Distribution Feeder Reconfiguration with Distributed Generation
  Using Intelligent Techniques* [Tesis doctoral, University of Kentucky].
  https://uknowledge.uky.edu/ece_etds/134/
