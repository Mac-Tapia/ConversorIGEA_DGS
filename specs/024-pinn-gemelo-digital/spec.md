# Spec 024 — PINN como oráculo y gemelo digital de la red calibrada

Estado: revisada, pendiente de aprobación final · Fecha: 2026-10-21

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
6. **Aprendizaje local y promovido.** El búfer puede crecer automáticamente; un modelo nuevo no
   pasa a producción hasta superar las puertas nativas y de calidad.

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
- RF-5: SI converge pero viola límites, ENTONCES EL SISTEMA la clasificará como
  `converged_with_violations`, nunca como aceptación operativa.

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
  búfer histórico; nunca modificará silenciosamente el modelo promovido.

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
tiempo real; aprendizaje en línea que cambie el modelo productivo; escribir maniobras sin
aprobación; predicción de demanda de largo plazo; enviar datos a servicios externos.

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
- Umbrales por perfil para MAE de tensión, error de flujo, residuo físico, calibración de
  incertidumbre y detección fuera de distribución.
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
