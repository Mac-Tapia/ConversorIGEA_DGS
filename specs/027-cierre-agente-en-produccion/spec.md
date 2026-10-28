# Spec 027 — Cierre del agente en producción: datos, entrenamiento robusto, verificación y operación

Estado: borrador del 2026-10-28, pendiente de aprobación (spec, plan y tareas) · Fecha: 2026-10-28
Origen: revisión del 2026-10-28 de los modelos de las specs 024 (gemelo) y 026 (asistente).

## Contexto y objetivo

Usuario, 2026-10-28: «revisa la implementación de LLM, PINN, genética, RNN, las capas, los
ajustes, los parámetros, hiperparámetros, dataset, qué falta para ponerlo en producción con el
agente»; «haz un plan de implementación robusta de lo que falta con sustento de artículos y
tesis de doctorado y maestría internacionales de los últimos 5 años; debe cerrar el proyecto
del agente con todos sus módulos y equipos».

La revisión del 2026-10-28 (medida, no supuesta) encontró:

- Gemelo (024): GNN de 8 pasos de mensaje, 64 ocultas, 3 miembros, Adam lr 3·10⁻³, 300
  épocas, peso físico 10⁻⁴; promovido con 0,00095 p.u. frente a DIgSILENT. Pero de 98
  episodios del búfer solo 24 son entrenables y **todos son de IN111–TA225**: 20 de
  entrenamiento, 2 de validación y 2 de prueba. Sin parada temprana, sin planificador de
  tasa, sin recorte de gradiente y con hiperparámetros fijos.
- GRU de curvas: 1 capa de 32, 40 épocas, sin validación; con PyTorch ausente cae a un
  modelo estacional en CPU, contra la regla de la 024 de no caer a CPU.
- Evolutivos (genético, NSGA-II, jDE): correctos y deterministas, pero optimizan contra el
  gemelo sin una regla escrita de verificación en DIgSILENT de lo que proponen.
- Asistente (026): Transformer por caracteres, 98,1 % de tarea y F1 0,869 de datos, entrenado
  sobre todo con órdenes sintéticas: **5 órdenes reales** confirmadas; Ollama local
  (llama3.1:8b) acierta el 76 % de 54 órdenes.
- Web: el trabajo pesado (libros de cabecera de ~400 MB) corre en hilos del proceso de la API;
  el 2026-10-27 la API dejó de responder durante minutos y una vez se quedó sin memoria.

Ahora hay sistemas enteros calibrados en DIgSILENT (Nasca 7/0 y Chincha 26/0 el 2026-10-28;
Pisco e Ica antes), es decir, datos de más de una familia. Esta spec cierra lo que falta para
que el agente opere en producción: datos de todos los sistemas, entrenamiento reproducible y
con parada por validación, incertidumbre calibrada, verificación nativa de cada propuesta,
evaluación del asistente con órdenes reales, operación (registro, deriva, reentrenamiento,
vuelta atrás) y una web que no se bloquea.

## Sustento (2021-2026, verificado el 2026-10-28)

| Tema | Fuente | Qué aporta a esta spec |
| --- | --- | --- |
| GNN para flujo de carga | Lin et al., «PowerFlowNet», *Int. J. Electr. Power Energy Syst.* 160 (2024) 110112 | Flujo como regresión de nodos con paso de mensajes; validado en una red real de 6 470 barras |
| Solvers estadísticos (tesis doctoral) | B. Donon, *Deep Statistical Solvers & Power Systems Applications*, tesis doctoral, Univ. Paris-Saclay / RTE, 2022 (HAL tel-03624628) | GNN entrenadas con la física como pérdida y su generalización entre topologías |
| PINN en sistemas eléctricos | B. Huang, J. Wang, «Applications of PINNs in Power Systems — A Review», *IEEE Trans. Power Syst.* 38(1) (2023) 572-588 | Pérdida física, arquitectura informada y modelos híbridos; límites de generalización |
| PINN (tesis doctoral) | J. Stiasny, tesis doctoral, DTU, defendida el 18-09-2023 (PINN para dinámica de sistemas eléctricos) | Entrenamiento y verificación de PINN frente al simulador |
| Estimación de estado con GNN y física (tesis de maestría) | B.P.E. Habib, «Deep Statistical Solver for Distribution System State Estimation», tesis de maestría, TU Delft, 2022 | La física en la pérdida de una GNN para redes de distribución |
| Red neuronal en la red de la región (tesis de maestría) | «Entrenamiento de una red neuronal artificial para el control de voltaje y reducción de pérdidas en la red de subtransmisión de 69 kV de la EERSA», tesis de maestría, Univ. Técnica de Cotopaxi, 2023 | Caso latinoamericano de red neuronal sobre una red real |
| Hiperparámetros | B. Bischl et al., «Hyperparameter Optimization: Foundations, Algorithms, Best Practices and Open Challenges», *WIREs Data Min. Knowl. Discov.* 13 (2023) e1484 | Búsqueda con presupuesto, evaluación anidada y reproducibilidad, en lugar de ajuste a mano |
| Aprendizaje continuo | L. Wang et al., «A Comprehensive Survey of Continual Learning», *IEEE TPAMI* (2024), doi 10.1109/TPAMI.2024.3367329 | Reentrenar sin olvidar lo aprendido (estabilidad y plasticidad) |
| Incertidumbre con cobertura | Mollaali et al. (2024, arXiv 2410.24162) y Renkema et al., *Solar Energy Advances* (2024) | Predicción conforme sobre conjuntos neuronales para intervalos con cobertura |
| Muestreo activo de sustitutos | «Sampling Strategies for Static Powergrid Models» (arXiv 2204.09053, 2022) | Cómo generar escenarios de entrenamiento con pocos datos históricos |
| Evolutivos con sustituto | C. He et al., «A review of surrogate-assisted evolutionary algorithms for expensive optimization problems», *Expert Syst. Appl.* 217 (2023) 119495 | El sustituto propone y el modelo caro (aquí, DIgSILENT) confirma |
| NSGA-II para bancos | El-Saeed et al., *Results in Engineering* (2023) | NSGA-II con decisor difuso para bancos en redes radiales |
| Previsión de demanda con aprendizaje profundo | Dong et al., «Short-Term Electricity-Load Forecasting by Deep Learning: A Comprehensive Survey» (arXiv 2408.16202, 2024) | Validación temporal y métricas de LSTM/GRU/Transformer |
| LLM en el sector eléctrico | Majumder et al., *Joule* (2024), doi 10.1016/j.joule.2024.05.009 | El LLM como copiloto con salvaguardas, herramientas e incertidumbre explícita |
| Agente LLM para simulación eléctrica | M. Jia, Z. Cui, G. Hug, «Enhancing LLMs for Power System Simulations: A Feedback-driven Multi-agent Framework» (arXiv 2411.16707, 2024-2025) | Recuperación, razonamiento y actuación con realimentación del error del simulador |
| Razonar y actuar | S. Yao et al., «ReAct», ICLR 2023 | Intercalar razonamiento y llamadas a herramientas, con traza auditable |
| Recuperación | Y. Gao et al., «Retrieval-Augmented Generation for LLMs: A Survey» (arXiv 2312.10997, 2023-2024) | Respuestas con cita del índice del proyecto |
| Ajuste fino eficiente | E. Hu et al., «LoRA», ICLR 2022; T. Dettmers et al., «QLoRA», NeurIPS 2023 | Adaptar el modelo local con poca memoria de GPU, solo si las puertas lo exigen |
| Preferencias | R. Rafailov et al., «Direct Preference Optimization», NeurIPS 2023 | Aprender de pares «rechazada frente a corregida» sin un modelo de recompensa aparte ni RL |
| Recompensa verbal | N. Shinn et al., «Reflexion: Language Agents with Verbal Reinforcement Learning», NeurIPS 2023 | Penalizar un fallo con una nota en memoria que guía la siguiente decisión, sin reentrenar |
| Abstención calibrada | V. Quach et al., «Conformal Language Modeling», ICLR 2024 | Umbrales con garantía de tasa de error para decidir cuándo preguntar |
| Operación de modelos | D. Kreuzberger, N. Kühl, S. Hirschl, «MLOps: Overview, Definition, and Architecture», *IEEE Access* 11 (2023) 31866-31879 | Registro de modelos, linaje de datos, monitoreo, reentrenamiento y vuelta atrás |

## Requisitos

Datos y episodios

- RF-1: CUANDO termine una calibración, una obra o un estudio de cualquier sistema eléctrico
  desde la web, EL SISTEMA guardará su episodio en el búfer con el sistema, la SET, el caso y
  la huella del proyecto, como ya hace la 024 con IN111–TA225.
- RF-2: EL SISTEMA particionará los episodios por familia de red de modo que ningún sistema
  eléctrico esté a la vez en entrenamiento y en prueba (evaluación «un sistema fuera»).
- RF-3: SI una familia tiene menos de [NECESITA ACLARACIÓN: ¿5 o 10?] episodios de prueba,
  ENTONCES EL SISTEMA no promoverá un modelo por su resultado en esa familia y lo dirá.
- RF-4: EL SISTEMA generará escenarios de entrenamiento en copias del proyecto (024:RF-10)
  con un muestreo que cubra el rango de carga medido de cada sistema, no solo su punta.

Entrenamiento robusto y reproducible (PINN y GRU)

- RF-5: EL SISTEMA detendrá el entrenamiento cuando el error de validación no mejore en un
  número de épocas fijado en la configuración, y guardará los pesos de la mejor época.
- RF-6: EL SISTEMA aplicará un planificador de la tasa de aprendizaje y un recorte de la norma
  del gradiente, con sus valores en la configuración del modelo.
- RF-7: CUANDO el operador pida una búsqueda de hiperparámetros, EL SISTEMA la hará con un
  presupuesto de ensayos y de tiempo, evaluando cada ensayo solo en validación, y guardará
  todos los ensayos y la configuración elegida.
- RF-8: EL SISTEMA guardará con cada modelo su manifiesto: episodios (con su huella), código
  (commit), configuración, semilla, dispositivo y métricas por familia.
- RF-9: Con el mismo manifiesto y la misma GPU, EL SISTEMA reproducirá el modelo con una
  diferencia de MAE de tensión menor que 10⁻⁵ p.u.
- RF-10: SI no hay GPU CUDA, ENTONCES EL SISTEMA no entrenará ni el gemelo ni la GRU y lo dirá,
  sin caer a un modelo en CPU (regla de la 024).
- RF-11: EL SISTEMA validará la GRU con la última parte de cada serie (validación temporal) y
  la promoverá solo si mejora al modelo estacional en esa parte.

Incertidumbre y dominio

- RF-12: EL SISTEMA calibrará la dispersión del conjunto con predicción conforme sobre la
  partición de validación, para dar por barra un intervalo de tensión con la cobertura
  fijada en la configuración (por defecto 90 %).
- RF-13: SI la anchura del intervalo de una barra supera la banda de la norma del sistema,
  ENTONCES EL SISTEMA marcará la predicción como no confiable y no la usará para decidir.

Optimización verificada (genético, NSGA-II, jDE)

- RF-14: EL SISTEMA verificará en DIgSILENT las k mejores soluciones de cada optimización
  antes de proponerlas, con k fijado en la configuración (por defecto 3).
- RF-15: SI la solución verificada en DIgSILENT se aparta de la predicha más que la tolerancia
  del gemelo, ENTONCES EL SISTEMA la descartará, guardará el episodio y repetirá con la
  siguiente.
- RF-16: EL SISTEMA dirá en cada propuesta la evaluación del gemelo y la de DIgSILENT.

Asistente (LLM)

- RF-17: EL SISTEMA guardará cada orden real del operador, con lo que confirmó o corrigió,
  como ejemplo de evaluación del asistente.
- RF-18: EL SISTEMA evaluará el asistente con un conjunto fijo de órdenes reales separado del
  de entrenamiento y lo promoverá solo con acierto de tarea ≥ 0,98 y F1 de datos ≥ 0,95.
- RF-19: MIENTRAS el conjunto real tenga menos de [NECESITA ACLARACIÓN: ¿200 órdenes?], EL
  SISTEMA pedirá confirmación de toda acción que escribe, aunque el asistente esté seguro.
- RF-20: CUANDO una acción ejecutada por el asistente devuelva un error, EL SISTEMA dará al
  modelo el error y su contexto y le dejará un único nuevo intento antes de devolver la orden
  al operador (realimentación del error).
- RF-21: DONDE el modelo local no supere las puertas de RF-18 con el conjunto real, EL SISTEMA
  podrá ajustarlo con LoRA o QLoRA en la GPU local, sin datos fuera de la máquina (P9).

Operación

- RF-22: EL SISTEMA vigilará la deriva de los datos de entrada de cada modelo frente a su
  dominio y avisará cuando una familia salga de él.
- RF-23: CUANDO haya deriva o al menos [NECESITA ACLARACIÓN: ¿10?] episodios nuevos de una
  familia, EL SISTEMA propondrá un reentrenamiento, que se promueve solo con las puertas.
- RF-24: EL SISTEMA permitirá volver al modelo anterior con una sola orden desde la web.

Robustez de la web

- RF-25: EL SISTEMA ejecutará los trabajos del motor que leen libros o convierten en un
  proceso trabajador aparte del de la API.
- RF-26: MIENTRAS corra un trabajo del motor, EL SISTEMA responderá a `/api/health` y al
  seguimiento de trabajos en menos de 1 s.
- RF-27: SI un trabajo del motor supera un límite de memoria fijado en la configuración,
  ENTONCES EL SISTEMA lo detendrá y lo dirá, sin detener la API.

Asistente: aprendizaje, razonamiento, decisión, recompensas y penalizaciones

Lo que hay (revisión del 2026-10-28): (1) comprensión: el Transformer da tarea, confianza y
datos; con confianza menor que el umbral pasa a Ollama, y si nadie llega pregunta; lo que tiene
forma inequívoca (periodo, número, ruta) lo fijan reglas; (2) razonamiento: `plan.resolver`
contrasta cada dato con lo que existe (parecido ≥ 0,8) y escribe su razón; (3) decisión: umbrales
fijos y pasos fijos por tarea; todo lo que escribe espera confirmación; (4) aprendizaje: solo
supervisado, con las órdenes confirmadas o corregidas (5 hoy) repetidas ×5 junto a las
sintéticas; **no hay recompensa ni penalización**: una orden rechazada o una ejecución fallida
no enseñan nada; (5) consultas por prompt: recuperación BM25 + vectores (50/50), «No lo sé»
por umbral y respuesta de Ollama con citas.

- RF-35: EL SISTEMA guardará con cada orden su señal: confirmada (recompensa), corregida
  (penalización de la interpretación del modelo y ejemplo positivo de la corregida),
  rechazada (penalización) y ejecución fallida (penalización de la acción, con el error).
- RF-36: EL SISTEMA formará, con cada corrección, un par de preferencia (la interpretación
  rechazada frente a la corregida) para el ajuste por preferencias directas (DPO) del modelo
  local con LoRA, dentro de RF-21.
- RF-37: CUANDO una ejecución falle o el operador corrija una orden, EL SISTEMA guardará una
  nota con la causa y la corrección, y la dará como contexto cuando llegue una orden parecida
  (memoria de reflexiones, sin cambiar pesos).
- RF-38: EL SISTEMA calibrará por tarea, con las órdenes reales, el umbral de confianza a
  partir del cual no pregunta, de modo que la tasa de error de lo que interpreta sin preguntar
  no supere la fijada en la configuración (por defecto 2 %); por debajo, preguntará.
- RF-39: CUANDO pase una orden a Ollama, EL SISTEMA le dará como ejemplos las k órdenes
  confirmadas más parecidas (por defecto 5).
- RF-40: EL SISTEMA decidirá según el impacto: una consulta de lectura puede responderse sin
  confirmar; toda escritura en DIgSILENT o en disco espera confirmación mientras se cumpla
  RF-19.
- RF-41: EL SISTEMA comprobará que cada cita de una respuesta exista en el índice y comparta
  términos con la frase que apoya; una respuesta con una cita que no la apoya se cambia por los
  trozos citados.
- RF-42: EL SISTEMA medirá las consultas con un conjunto de preguntas reales del operador: la
  fracción respondida con cita correcta y la fracción de «No lo sé» acertados.

Proyecto completo desde cero y PIDE (usuario, 2026-10-28: «el agente debe hacer desde cero y toda
la norma PIDE ya implementada, debe saber ejecutar todo el proyecto, debe usar para el
entrenamiento los archivos ya entregables de PIDE que están en la subcarpeta PIDEELOR»)

- RF-43: CUANDO el operador lo pida, EL SISTEMA (el agente) ejecutará el proyecto entero desde
  un espacio vacío, por las rutas de la web: cargar las fuentes, convertir por sistema,
  importar en DIgSILENT, verificar el «Caso base», calibrar, integrar cargas nuevas, obras,
  estudios, PIDE e informes.
- RF-44: EL SISTEMA guardará un punto de control al terminar cada etapa de RF-43 y retomará
  desde el último si la ejecución se corta, sin repetir lo hecho.
- RF-45: EL SISTEMA producirá el PIDE completo con lo ya implementado (`pide.py`,
  `pide_economia.py`, 024:T13 y T14) y el contrato universal de 2017
  (`config/pide_universal_2017.json`: artículos 1 a 20, formatos F01 a F15 y alternativas),
  sin una segunda implementación de la norma.
- RF-46: EL SISTEMA construirá el corpus de entrenamiento y de consulta desde
  `referencia/PIDEELOR` con `pide_dataset` (manifiesto con custodia y huella de cada fichero,
  fragmentos de texto y tablas), local y fuera de git.
- RF-47: EL SISTEMA tratará el corpus como contexto, nunca como norma: lo que dice un
  entregable ilustra cómo se hizo; lo que manda es el contrato de 2017.
- RF-48: EL SISTEMA sacará del corpus ejemplos para el agente: por cada artículo, sus
  evidencias y entregables en los PIDE 2021 y 2026 entregados; por cada formato F01 a F15, sus
  hojas y columnas tal como se entregaron.
- RF-49: EL SISTEMA comparará cada formato que produce con el entregado del mismo código
  (hojas, columnas y unidades) y dirá la fracción de campos que coinciden.
- RF-50: EL SISTEMA aprenderá la estructura de los informes entregados (secciones del Informe
  de Largo Plazo 4.1 y del Informe PIDE 4.2) para redactar los del proyecto con la misma
  estructura.
- RF-51: SI un fichero del expediente es de un formato que el conversor no lee (proyectos MPP,
  planos DWG, comprimidos RAR), ENTONCES EL SISTEMA lo inventariará con su huella y lo dirá,
  sin descartarlo en silencio.
- RF-52: [NECESITA ACLARACIÓN: la base «BASE DE DATOS GIS MT BT IQUITOS» viene en shapefile
  (SHP/DBF/SHX): ¿convertir la red de Iquitos desde ese GIS a DIgSILENT entra en esta spec, como
  una cuarta fuente junto a TXT, MDB y VNR-GIS, o solo se usa como corpus?]

Auditoría del dataset de cada modelo (antes de entrenar)

- RF-29: CUANDO se pida entrenar cualquier modelo, EL SISTEMA auditará antes su dataset y
  guardará el informe: muestras, redes distintas, nodos, columnas de entrada, fracción
  etiquetada, rangos, valores no finitos y duplicados.
- RF-30: SI el dataset tiene valores no finitos, ENTONCES EL SISTEMA no entrenará y nombrará
  los episodios que los traen.
- RF-31: SI una rama tiene una impedancia por debajo de un umbral en p.u. fijado en la
  configuración (puentes y maniobras: 1,4·10⁻⁶ p.u. en IN111–TA225, relación máx/mín
  6·10⁷), ENTONCES EL SISTEMA fundirá sus dos nodos en la física de la PINN, en vez de
  invertir esa impedancia.
- RF-32: SI una tensión objetivo cae fuera de un rango plausible fijado en la configuración
  (0,61 p.u. en IN111–TA225), ENTONCES EL SISTEMA la marcará en el informe y la excluirá de la
  pérdida salvo que el operador la confirme.
- RF-33: EL SISTEMA dirá en el informe la relación entre parámetros del modelo y etiquetas
  independientes (928 518 parámetros de la PINN frente a 58 707 tensiones de una sola red;
  567 088 del Transformer frente a 4055 órdenes, una real) y avisará cuando el número de redes
  o de órdenes reales distintas sea menor que [NECESITA ACLARACIÓN: ¿2 redes / 200 órdenes?].
- RF-34: EL SISTEMA medirá el asistente solo con órdenes reales, nunca con las sintéticas que
  genera para entrenar, para las puertas de RF-18.

Aceptación

- RF-28: EL SISTEMA dará por cerrada esta spec cuando, desde la web y con el asistente, se
  calibren en DIgSILENT todos los sistemas eléctricos de la estructura, el gemelo promovido
  pase sus puertas con al menos dos familias de prueba y el asistente pase RF-18.

## Fuera de alcance

- Modelos en la nube o servicios de terceros: todo es local (P9).
- Cambiar las reglas de calibración de las specs 015, 021, 022 y 025: el agente las usa, no las
  redefine.
- Entrenar modelos de lenguaje desde cero.
- Operar la red en tiempo real: el agente planifica y propone; no maniobra equipos.

## Dudas abiertas

- [NECESITA ACLARACIÓN: «todos sus módulos y equipos»: ¿«equipos» son los equipos de la red
  (transformadores, bancos, reguladores) que el agente debe saber modelar y proponer, o el
  hardware (GPU, servidor) en que corre?]
- [NECESITA ACLARACIÓN: umbrales de RF-3, RF-19 y RF-23.]
