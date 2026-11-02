# Auditoría de los alumnos y su siguiente aprendizaje

Seguimiento: la [entrega de correcciones](CORRECCIONES_ALUMNOS_2026-11-01.md)
documenta los cambios posteriores de spec060, el corpusv5 y un candidato GRU
ajustado/reabierto con observaciones reales de enero. Este documento conserva el
diagnóstico previo y sus métricas históricas; no representa por sí solo el estado posterior.

Revisión del 1 de noviembre de 2026, checkout local ConverterSmartGrid, HEAD `d7a3b4146dbf44976d24d60778bbff8ac5f07bfc`. Es una auditoría: no se reentrenaron modelos ni se cambiaron sus punteros. Se distingue la configuración guardada, la receta futura y los resultados históricos. Un peso finito demuestra integridad numérica, no competencia ni aceptación eléctrica.

## Evidencia de esta revisión

- [Inventario de pesos y metadatos completos](../output/auditoria_alumnos_20261101/inventario_pesos.json): SHA256, tamaños, CRC de archivos PyTorch, tipos de almacenamiento y barrido de valores float32 sin ejecutar pickle ni cargar Torch.
- [Catálogo de bases comprobado nuevamente](../output/auditoria_alumnos_20261101/catalogo_pesos.json): cinco modelos fijados, todos con comprobación satisfactoria de sus artefactos locales.
- [Episodios y registro común](../output/auditoria_alumnos_20261101/episodios_registro.json): lectura de JSON; no recalcula el flujo nativo ni certifica de nuevo los artefactos de cada episodio.
- [Recursos al cierre](../output/auditoria_alumnos_20261101/recursos.json): 2,195 GiB de RAM disponible, 9,382 GiB de memoria comprometible y 9,099 GiB libres en D:. Son una instantánea, no una reserva para entrenar.
- Generadores reproducibles sin carga de redes: [inspeccionar.py](../output/auditoria_alumnos_20261101/inspeccionar.py), [episodios.py](../output/auditoria_alumnos_20261101/episodios.py), [detalles.py](../output/auditoria_alumnos_20261101/detalles.py), [completar.py](../output/auditoria_alumnos_20261101/completar.py).

No se repitió inferencia ni entrenamiento en esta auditoría. Las métricas siguientes son las guardadas en sus respectivos experimentos. Se verificaron nuevamente los bytes de los pesos de los tres modelos heredados; las bases se comprobaron con `tools/preparar_modelos_ia.py`, sin descargar ni activar modelos.

## 1. PINN/GNN: alumno de las soluciones eléctricas

**Existe un ensamble entrenado**, versión `20261028-114528-e6f5`, tres miembros de 1.259.687 bytes cada uno. Cada archivo contiene 309.506 elementos de almacenamiento float32; los tres pasan CRC, SHA256 registrado y barrido completo sin NaN/Inf. No se contó eso como parámetros entrenables: puede incluir buffers. El modelo incorpora mensajes de grafo y celdas GRU; estas celdas no acreditan un predictor temporal GRU separado.

Configuración efectivamente guardada:

| Ajuste | Valor |
|---|---|
| Capas de mensajes / ancho | 8 / 64 |
| LR inicial / mínimo | 0,003 / 0,00001 |
| Peso de la pérdida física | 0,0001 |
| Física / exponente de carga | mallado / 1,0 |
| Límite de épocas / paciencia / evaluación | 300 / 60 / cada 5 |
| Recorte de gradiente | 1,0 |
| Semillas de los miembros | 0, 1, 2 |
| Épocas registradas por miembro | 66, 71, 66 |
| Mejor época registrada | 5, 10, 5 |
| Particiones declaradas | 52 entrenamiento, 10 validación, 10 prueba |
| Intervalo: cobertura nominal / calibración | 0,90 / 10 muestras |

Las épocas son las registradas por la curva guardada; no equivalen a 300 épocas completas. Hay ajuste desde la versión anterior `20261024-153426-dd63`. El manifiesto registra código de entrenamiento `10956c1aa9980ec3a86bce8b67eddfe03422efc8`, distinto del checkout actual.

Resultados históricos: MAE de tensión **0,002435454 p.u.**, residuo medio **0,019361322**. No hay MAE de casos dorados (`null`). El dominio guardado tiene **4.944 nodos**; no se ha demostrado generalización a cualquier red. Se localizaron los 72 IDs usados: **70 contrafactuales y 2 accepted**. El búfer actual contiene 237 registros: 64 accepted, 106 counterfactual, 31 rejected, 19 converged_with_violations y 17 quarantine. Los 165 no usados no son automáticamente muestras elegibles ni compatibles.

**Qué le falta y qué debe ajustarse:**

1. Auditar familia, fuente, sistema y objetivo de cada muestra; conservar la distinción entre contrafactual calculado y observación operativa. No agregar redes distintas solo para aumentar el número de episodios.
2. Eliminar para la aceptación los respaldos de particiones en `digital_twin/oraculo.py`: líneas 910–911 copian validación a entrenamiento si este queda vacío; líneas 937 y 939 permiten calibrar/evaluar con particiones alternativas. Aunque existan otras puertas posteriores, una campaña válida debe detenerse antes de ajustar si falta una partición independiente. Esto es un hallazgo del código, no prueba de que esos respaldos se activaran en el modelo histórico.
3. Separar selección por parada temprana de calibración conforme. Hoy se reutiliza validación para ambas. La cobertura 0,90 es nominal; falta medir cobertura y ancho fuera de selección, por familia y régimen.
4. Añadir casos dorados independientes y comprobar retención frente al modelo anterior. Auditar también la genealogía de los pesos: mantener familias fuera del entrenamiento de todas las versiones anteriores, no solo de la última época.
5. Comparar física sola, red sin término físico y configuración actual. Ajustar peso físico, LR y capacidad en selección; no aumentar épocas por defecto: las mejores épocas registradas son tempranas.
6. Verificar compatibilidad de arquitectura y características con el código actual, reapertura e inferencia; después validar propuestas en PowerFactory con lectura posterior y criterios eléctricos.

La incorporación de física necesita comprobar precisión, coste y dominio frente al solucionador. Se fundamenta en la [tesis doctoral de Stiasny, DTU, 2023](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/) y en [Karniadakis et al., Nature Reviews Physics, 2021](https://www.nature.com/articles/s42254-021-00314-5). Estos trabajos no prescriben los umbrales particulares del proyecto.

## 2. Transformer pequeño: alumno de órdenes y entidades

Versión heredada `20261024-150042-37ce`; peso de **2.281.993 bytes**, 567.088 elementos float32, CRC correcto y cero NaN/Inf. Configuración: dimensión128, 4 capas, 4 cabezas, **24 épocas configuradas**, lote64, LR0,001, semilla0, 150 ejemplos por tarea. El metadato no acredita por sí solo una traza completa de las 24 épocas ni contiene curvas de entrenamiento.

Declara 4.055 ejemplos, `reales=1`, prueba540, 27 tareas y 21 etiquetas. Métricas históricas del candidato: acierto de tarea **98,148 %**, F1 de datos **0,86892**. El puntero heredado está promovido, pero su F1 no satisface la puerta actual de 0,95. Además existe un candidato del registro común **RECHAZADO**. No deben presentarse ambos estados como una única aceptación vigente.

**Siguiente enseñanza:** ampliar órdenes humanas verificadas por tarea, errores ortográficos, entidades, fuentes ambiguas y abstenciones; medir matriz de confusión y F1 por entidad/tarea; separar familias de plantillas entre particiones. Conservar un conjunto de selección para comparar LR y regularización antes de decidir más épocas o capacidad. Guardar curva, pasos, temperatura de calibración y errores concretos; comprobar retención. No se infiere dominio del asistente por una sola orden real.

## 3. Clasificador de informes

**Sí tiene pesos**, aunque no figure un candidato actual en el registro común: versión `20261024-150047-b3c4`, **2.258.825 bytes**, 561.288 elementos float32, CRC correcto y cero NaN/Inf. Dimensión128, 4 capas, 4 cabezas, **12 épocas configuradas**, lote64, LR0,001 y semilla0. Distingue 2 tipos y 6 subtipos. El artefacto guarda 150 ejemplos de evaluación, acierto de tipo1,0 y subtipo **0,986667**.

**Qué falta:** el metadato no detalla cantidad/procedencia del entrenamiento, particiones independientes, proporción humana, historial de pérdida ni rendimiento por subtipo. Las 150 evaluaciones no se pueden llamar 150 episodios de entrenamiento. Necesita informes reales autorizados, casos ambiguos y fuera de taxonomía, anotación comprobada, separación por documento/proyecto y calibración de abstención. Medir macro-F1 por subtipo, no solo acierto agregado. Comprobar que el registro común representa correctamente este modelo antes de usar su estado para aceptación integral.

La comparación maestro–base–alumno y las pruebas específicas de dominio de los alumnos de lenguaje se apoyan en la [tesis de maestría de Witossek, Leipzig/DLR, 2025](https://elib.dlr.de/220552/), y en [Gou et al., IJCV, 2021](https://arxiv.org/abs/2006.05525). Sus resultados pertenecen a sus experimentos; no certifican estos clasificadores.

## 4. GRU/RNN temporal

No existe el almacenamiento heredado esperado `output/web/_digital_twin/modelos_temporales`. En los directorios de esta campaña no se acreditó un predictor temporal ajustado. La operación real con el libro 2025 quedó **BLOQUEADO_POR_DATOS: «L-TM105: fecha o potencia ausente»**; [decisión](../output/auditoria_ia_20261101_actual/gru_fuente_real.json).

**Receta del código, todavía no un entrenamiento acreditado:** ventana96 puntos de 15 minutos, 2 entradas, ocultas32, máximo40 épocas, paciencia8, validación interna0,20, recorte1, Adam LR0,01 y programación coseno. El trabajador separa periodos cronológicos con huecos de ventana y selección de semilla. No hay pasos, épocas completadas ni MAE del nuevo alumno que puedan informarse como reales.

**Qué falta:** reconciliar fechas/potencias y cadencia del libro sin imputar silenciosamente; obtener una serie continua trazable, aplicar escalado causal y particiones cronológicas; entrenar y reabrir pesos. Comparar contra persistencia y estacional con iguales horizontes, por alimentador y periodos. Revisar especialmente LR0,01 mediante selección y curvas; es una revisión propuesta, no un LR demostrado incorrecto. No sustituir por Transformer temporal antes de establecer esas referencias. La evaluación por horizonte y uso explícito de entradas temporales se apoya en [Lim et al., International Journal of Forecasting, 2021](https://doi.org/10.1016/j.ijforecast.2021.03.012).

## 5. LLM generativo y destilación

La base **Qwen3-4B-Instruct-2507 NF4** está fijada en revisión `f12db89cd5156e090618dded9b4367f23f8f3b33`; sus pesos de 2.653.133.894 bytes y tokenizer pasan nuevamente el catálogo. Una base descargada o exportada a GGUF no es un alumno especializado.

**Ajuste real existente:** adaptador de prueba de **1 paso**, LoRA rango4, alpha8, dropout0, módulos q_proj/v_proj; 144 tensores F32, **1.474.560 parámetros de adaptador**, 5.917.192 bytes y offsets Safetensors válidos. SHA256 `37a891b4cd9acbc93d7a75959db1546fd8b3e6aff0070de1e8d16302c8a80640`. El informe anterior guarda pérdida5,456531 y reapertura con diferencia de logits0. Esta revisión comprobó estructura/hash; no volvió a ejecutar esa reapertura.

**Receta integral prevista, distinta del ensayo anterior:** rango8, alpha16, dropout0,05, all-linear, BF16, lote1, acumulación8, LR2e-4, calentamiento10 actualizaciones, recorte1, secuencia máxima2048 sin truncamiento, semilla11, hasta2 épocas predeclaradas. Con 1.734 ejemplos y acumulación8 serían **217 actualizaciones por época completa** desde cero y sin alterar el corpus; es un cálculo del presupuesto, no pasos ejecutados.

El corpus v4 declara **1.734 entrenamiento /54 selección /54 calibración /200 prueba** y 3 órdenes humanas reservadas. Sus instrucciones redactadas por maestro usan entidades reales; no son 1.734 observaciones humanas. **El sellado vigente falla** porque cambió `docs/constitution.md`: hash actual `8c60a40a0f4dec9d5366cbbd3047cffbae943f2e9fe5922be9b625405fa68979`. El intento con fuentes reales conserva **BLOQUEADO_POR_DATOS: huella de fuente modificada**. No se encontró un checkpoint de destilación integral; las 30 piezas Safetensors bajo la exportación FP16 son de la base.

**Qué falta:** regenerar y sellar una nueva versión coherente con las fuentes y política actuales, conservar la versión anterior; revisar respuestas del maestro contra herramientas reales y prohibir resultados eléctricos inventados; completar entrenamiento con pérdidas, pasos y checkpoints reabribles. Comparar en selección maestro, base y alumno; calibrar aparte y abrir la prueba final una vez congelada la configuración. No reutilizar resultados del corpus viejo como prueba de uno nuevo. Exigir comparación antes/después de exportación y prueba funcional de herramientas con lectura real de resultados.

La evaluación histórica qwen3:8b obtuvo 188/200 órdenes y F1≈0,9394: tampoco acredita las puertas actuales. No corresponde al alumno4B ni sustituye evaluación de sus pesos.

La receta NF4/LoRA se fundamenta en [Dettmers et al., QLoRA, NeurIPS2023](https://proceedings.neurips.cc/paper_files/paper/2023/hash/1feb87871436031bdc0f2beaa62a049b-Abstract.html). La tesis de maestría anterior fundamenta comparar maestro, base y alumno en tareas de dominio. Ninguna fuente garantiza que dos épocas o rango8 alcancen aceptación en este proyecto.

## 6. Recuperador, embeddings y reranker

**E5 multilingüe, BGE reranker y nomic están instalados** y pasan el catálogo actual. Son modelos preentrenados; los vectores de un índice no equivalen a nuevos pesos aprendidos. No se acreditó un encoder ajustado aceptado en esta campaña. El último intento E5 conserva **ERROR_ENTORNO**, memoria comprometible4,132 GiB frente a la puerta6 GiB; [decisión](../output/auditoria_ia_20261101_actual/embeddings_operacion_real_v2/decision.json).

Receta E5 implementada: AdamW LR2e-5, lote8, temperatura contrastiva0,05, semilla11, recorte1, 1 época por defecto y mínimo20 pares. Los 20 fragmentos literales preparados solo sirven de entrenamiento inicial: no hay evaluación independiente de consultas que justifique aceptación. No existe un nuevo resultado de pérdida ni épocas completadas de este intento.

**Qué falta:** consultas reales con documentos relevantes anotados y negativos difíciles; separar consultas de entrenamiento, selección y prueba, incluyendo ausencia de respuesta; medir Recall@k, MRR y nDCG frente a BM25, E5 y recuperación combinada. Verificar huella del encoder y reconstrucción del índice al cambiar pesos. Comprobar integración efectiva de BGE en el flujo: instalar el modelo no acredita que el asistente lo use. Ajustar temperatura, lote o LR solo con comparación de selección y estabilidad de recuperación. El enfoque de representación contrastiva se documenta en [Wang et al., E5](https://arxiv.org/abs/2212.03533); el preprint no se presenta como artículo indexado y complementa las fuentes académicas anteriores.

## 7. Evolutivos: solucionadores, sin pesos neuronales

No corresponden «épocas del alumno» ni «episodios aprendidos»: aquí hay poblaciones, generaciones, semillas y evaluaciones. La [campaña analítica existente](../output/auditoria_ia_20261101_actual/evolutivos_operacion_real.json) contiene **30 semillas por algoritmo**, 90 ejecuciones, sin promoción ni escrituras eléctricas:

| Algoritmo | Población / máximo generaciones | Evaluaciones totales | Mediana del objetivo del benchmark |
|---|---:|---:|---:|
| GA | 30 /100 | 7.657 | 0 |
| NSGA-II | 30 /40 | 36.896 | 0,0000315694 |
| DE | 30 /250 | 210.330 | 2,7479e-20 |

Además de los valores de campaña, el código define estos valores por defecto de operadores: GA cruce0,9, mutación automática, élite2 y torneo3; NSGA-II cruce0,9, eta de cruce15 y de mutación20; DE usa jDE con F/CR adaptados por individuo. Son defaults del código, no un registro completo de la trayectoria de operadores de cada ejecución histórica.

Los objetivos son diferentes y no sirven para ordenar estos tres algoritmos entre sí. **Qué falta:** registrar todos los hiperparámetros de operadores y restricciones, fijar presupuesto comparable, usar problemas eléctricos del proyecto con límites y variables correctos, comparar referencia determinista y verificar los mejores candidatos mediante el motor nativo. El benchmark analítico acredita ejecución, no decisiones aceptables de bancos, generación o reconfiguración. La selección multiobjetivo y la búsqueda continua tienen como referencias [Deb et al., IEEE Transactions on Evolutionary Computation, 2002](https://ieeexplore.ieee.org/document/996017) y [Storn y Price, Journal of Global Optimization, 1997](https://doi.org/10.1023/A:1008202821328). Su adecuación concreta a las variables y restricciones eléctricas aún debe justificarse y verificarse según spec048.

## Orden de corrección y aceptación por alumno

| Prioridad | Trabajo pendiente | Evidencia que permite avanzar |
|---|---|---|
| P1 | Sellado coherente del corpus LLM | Auditoría de todas las fuentes/política satisfactoria, particiones congeladas |
| P1 | Independencia del PINN y retención | Sin respaldo entre particiones; IDs y familias de selección/calibración/prueba, genealogía y dorados |
| P1 | Fuente temporal completa | Serie trazable, cadencia y datos reconciliados, particiones causales |
| P1 | Estado único de modelos | Concordancia entre punteros heredados, registro común y modelo realmente invocado |
| P2 | Entrenamiento integral LLM, GRU y E5 | Pesos nuevos, curvas/pasos, recursos, reapertura y referencias comparables |
| P2 | Validación externa de clasificadores | Muestra humana por clase/tarea y documentos independientes, calibración y abstención |
| P2 | Optimización eléctrica | Presupuesto/operadores guardados, restricciones y verificación nativa de candidatos |
| P3 | Aprendizaje continuo coordinado | Datos admitidos por fuente, revisión del maestro, entrenamiento, retención, evaluación independiente y promoción reversible |

Para evitar olvido, cada actualización necesita repetir una evaluación histórica congelada y otra de novedades. La [tesis doctoral de Mirzadeh, WSU, 2022](https://rex.libraries.wsu.edu/esploro/outputs/doctoral/Alleviating-Catastrophic-Forgetting-in-Continual-Learning/99900898638301842) fundamenta revisar régimen de entrenamiento y retención. «Autoaprendizaje» no autoriza usar respuestas del propio alumno como verdad ni garantiza mejora monótona.

Estas prioridades son conclusiones de la auditoría local. No se marcaron como implementadas las correcciones ni como completados los entrenamientos pendientes. La nueva evaluación de aceptación se hará tras resolverlas conforme a las specs027 y043–050; las puertas de precisión y aceptación eléctrica son contratos del proyecto, no valores deducidos de las tesis.
