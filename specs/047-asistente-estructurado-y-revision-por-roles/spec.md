# Spec 047 — Asistente estructurado y revisión por roles

Estado: aprobada · Fecha: 2026-10-31

## Contexto y objetivo

El asistente ya tiene Transformer, clasificador, reglas, Ollama y BM25 con vectores opcionales. TradingAgents inspira roles separados, pero el sistema financiero no se incorpora ni demuestra capacidad eléctrica.

## Usuarios y alcance

Ingeniero de planificación desde web/CLI y agente ejecutor del plan SDD.
Dependencias y relación: 043 y 044; conservar intérprete, resolución, herramientas y confirmaciones de 026–027.

## Requisitos funcionales (EARS)

- RF-1: CUANDO el modelo local interprete una orden, EL SISTEMA validará su salida contra el esquema de tareas y campos admitidos.
- RF-2: SI una entidad no corresponde al contexto vinculado, ENTONCES EL SISTEMA impedirá que esa entidad forme un plan ejecutable.
- RF-3: CUANDO se responda con documentos, EL SISTEMA conservará citas vinculadas a fragmentos de fuente verificables.
- RF-4: CUANDO se evalúe recuperación, EL SISTEMA comparará BM25, híbrido y reranker con el mismo conjunto sellado.
- RF-5: CUANDO se revise una propuesta, EL SISTEMA separará evidencia de fuentes, consistencia física, coste y riesgo en dictámenes trazables.
- RF-6: SI un dictamen carece de evidencia o contradice una restricción determinista, ENTONCES EL SISTEMA impedirá presentarlo como aprobación de ejecución.
- RF-7: MIENTRAS se revise por roles, EL SISTEMA limitará la discusión a dos rondas cancelables sin escrituras nativas.
- RF-8: CUANDO se decida ajustar el LLM, EL SISTEMA exigirá el incumplimiento medido de las puertas del conjunto real.
- RF-9: CUANDO se evalúe el asistente, EL SISTEMA aplicará las puertas de 027:RF-18 sobre órdenes reales independientes.
- RF-10: EL SISTEMA conservará las reglas de autorización y confirmación vigentes al incorporar los nuevos modelos.
- RF-11: CUANDO se destile al alumno, EL SISTEMA conservará autor, revisión, método y etiquetas del maestro sin presentar anotaciones únicas como votos independientes ni como órdenes humanas.
- RF-12: CUANDO se compare destilación con entrenamiento supervisado, EL SISTEMA usará las mismas semillas y particiones independientes y elegirá el candidato únicamente con selección.
- RF-13: CUANDO se informe la calidad del alumno, EL SISTEMA separará las métricas sintéticas, del maestro y humanas con sus denominadores, sin sustituir las 200 propuestas del maestro por un requisito de 200 observaciones humanas para evaluar uso asistido y conservando las confirmaciones de 027.
- RF-14: CUANDO se registre un alumno, EL SISTEMA verificará sus pesos en un proceso nuevo y conservará configuración, corpus, particiones y decisión en el registro común.
- RF-15: CUANDO se ensaye el agente entrenado, EL SISTEMA comprobará interpretación, resolución de entidades y confirmaciones con casos positivos y negativos sin ejecutar escrituras nativas.
- RF-16: CUANDO se publique el conjunto de 200 propuestas del maestro, EL SISTEMA exigirá 200 textos únicos, cobertura de todas las tareas, etiquetas y entidades válidas, huella sellada y ausencia de solapamiento declarado con entrenamiento.
- RF-17: CUANDO se evalúe aceptación, EL SISTEMA publicará por separado aceptación asistida sobre las propuestas, validación humana y aceptación eléctrica, sin convertir propuestas en órdenes humanas ni omitir requisitos incumplidos.
- RF-18: CUANDO se configure revisión obligatoria por el LLM local, EL SISTEMA impedirá que una predicción no validada del alumno evite esa revisión o forme un plan si el revisor no responde.
- RF-19: CUANDO se destile al LLM generativo local como alumno, EL SISTEMA ajustará sus adaptadores con respuestas verificables del maestro, conservará la base fijada y comparará base/alumno mediante selección separada antes de evaluar y autorizar la versión de ejecución.
- RF-20: CUANDO se construya su dataset desde referencia, EL SISTEMA conservará archivo, huella y localizador de cada dato real, identificará las instrucciones redactadas por el maestro y rechazará resultados eléctricos sin evidencia de ejecución nativa.
- RF-21: CUANDO haya vectores para recuperar, EL SISTEMA fusionará por posiciones el ranking BM25 y el de vectores, sin mezclar sus puntuaciones.
- RF-22: SI al índice le faltan vectores y Ollama responde con su modelo de embeddings, ENTONCES EL SISTEMA los calculará en un trabajo cancelable del carril del asistente, sin paso manual.
- RF-23: EL SISTEMA no calculará los vectores del corpus dentro de una petición ni dentro de la respuesta a una pregunta.
- RF-24: SI otra orden espera en el carril o se cancela el trabajo de vectores, ENTONCES EL SISTEMA guardará lo calculado y dejará libre el carril.
- RF-25: SI Ollama no da vectores, ENTONCES EL SISTEMA responderá con BM25.
- RF-26: CUANDO se responda con documentos, EL SISTEMA dirá en la respuesta qué métodos de recuperación usó.
- Aclaración de RF-26 (usuario, 2026-11-14: en la web, ninguna cita de RF ni jerga; aclaración de 070:RF-51): los métodos
  van en el campo `recuperacion` de la respuesta y en el registro, no en el texto que lee el operador.
- RF-27: EL SISTEMA usará el reranker solo si la decisión guardada de la evaluación sellada lo adoptó según la política declarada en el plan antes de medir.
- RF-28: SI la consulta nombra un código que aparece tal cual en un fragmento, ENTONCES EL SISTEMA pondrá ese fragmento por delante de los demás, con reranker o sin él.
- RF-29: SI una cita no se puede comprobar contra su fichero, ENTONCES EL SISTEMA la quitará de la respuesta y, sin citas, dirá que no lo sabe.
- RF-30: SI el reranker adoptado no puede correr en CUDA, ENTONCES EL SISTEMA conservará el orden sin reranker, sin caer a CPU, y lo dirá en la respuesta.
- RF-31: CUANDO el reranker calibrado haya puntuado, EL SISTEMA decidirá si hay respuesta comparando su mejor puntuación con su umbral calibrado.
- RF-32: SI no hay reranker calibrado que haya puntuado, ENTONCES EL SISTEMA decidirá con los umbrales calibrados de coseno y BM25, o con el de BM25 solo si no hay vectores.
- RF-33: SI no hay umbral calibrado para el método disponible, ENTONCES EL SISTEMA responderá «No lo sé» y lo dirá en la respuesta.
- RF-34: EL SISTEMA fijará los umbrales solo con el conjunto de calibración y guardará su huella, sin usar el conjunto de 76 ni el sellado.
- RF-35: SI ya hay un informe del conjunto sellado de abstención con la misma huella, ENTONCES EL SISTEMA rechazará medirlo de nuevo.
- RF-36: CUANDO se mida el conjunto sellado, EL SISTEMA aplicará a cada método la puerta declarada en el plan e informará si la cumple.
- RF-37: SI la consulta nombra un código que está tal cual en un fragmento hallado, ENTONCES EL SISTEMA lo contará como evidencia sin aplicar el umbral.
- RF-38: SI un dictamen no es favorable y no nombra ninguna contradicción ni incertidumbre, ENTONCES EL SISTEMA lo tratará como dictamen no válido, que bloquea sin contarse como defecto hallado.
- RF-39: CUANDO se pida un dictamen al LLM, EL SISTEMA le enviará solo la propuesta y el localizador y el fragmento de cada evidencia, sin rutas, huellas ni nombres de proyecto o de caso.
- RF-40: CUANDO se pida un dictamen al LLM, EL SISTEMA le pedirá las contradicciones y las incertidumbres antes que la decisión, con la regla que da la decisión a partir de ellas.
- RF-41: CUANDO se mida la revisión, EL SISTEMA guardará en el informe la decisión, la evidencia citada, las contradicciones y las incertidumbres de cada dictamen.
- RF-42: CUANDO una puerta rechace un modelo del asistente por una métrica, EL SISTEMA dirá si falta o si está bajo la
  puerta, con el valor medido y de cuántos ejemplos sale. Ciclo del 2026-11-08: «acierto_tarea ausente, inválido o bajo 0,98»
  escondía que el Transformer se midió (0,71 con 7 ejemplos).
- RF-43: CUANDO se mida la revisión con un conjunto de casos, EL SISTEMA comprobará antes de medir que su huella es la
  declarada, la escribirá en el informe, y no medirá un conjunto sin huella declarada o con otra. T8, 2026-11-19: los 12
  casos del 2026-11-03 ya orientaron el diagnóstico, así que la medida que cierra la T8 usa otro conjunto declarado antes.
- RF-44: CUANDO se pida un dictamen al LLM, EL SISTEMA le dirá que, con alguna contradicción o incertidumbre pendiente,
  la decisión nunca es «favorable», sino «revisar» (requiere revisión) o «bloqueada». MEJ24, 2026-11-21: con el 047b,
  todas las «sin respuesta» de qwen3:8b eran dictámenes favorables con listas pendientes, que RF-40 anula.
- RF-45: CUANDO se pida un dictamen al LLM, EL SISTEMA no le enviará las restricciones deterministas, que comprueba el
  código, y en la segunda ronda le dirá que los dictámenes anteriores no son evidencia ni se copian: solo cuenta lo de su
  encargo que compruebe en la evidencia.
- RF-46: CUANDO se pida un dictamen al LLM, EL SISTEMA le dirá que una evidencia de otro elemento (alimentador, SET,
  tramo, poste, nodo o equipo) no confirma un dato, que el mismo valor con otro formato no es una contradicción, que lo
  confirmado no va en las listas y que el coste de la propuesta es el total de lo que la evidencia dice que pide la acción.
- RF-47: CUANDO se mida la revisión, EL SISTEMA guardará en el informe el tope de tokens por intervención, la
  intervención más larga, cuántas llegaron al tope y, de cada dictamen no válido, la decisión y las listas que devolvió
  el LLM; el tope por omisión es 1024 y se elige con `--tokens`.
- RF-48: CUANDO se pida un dictamen al LLM, EL SISTEMA le pedirá cada contradicción con su campo, el valor de la
  propuesta, el valor de la evidencia y la fuente (el ID de la evidencia), y tratará como dictamen no válido el que
  traiga una contradicción con otra forma; una contradicción en texto libre, del formato anterior, se sigue admitiendo.
  MEJ24b, 2026-11-21: con el 047c, qwen3:8b escribía en «contradicciones» las comprobaciones que coinciden
  («coste_usd: 11200 vs 11200», «38 kW vs 38 kW (no contradicción)»), sin que el código pudiera distinguirlas.
- RF-49: CUANDO un dictamen traiga contradicciones, EL SISTEMA decidirá si cada una lo es comparando sus dos valores
  con la unidad normalizada (%, kW, MW, kvar, kVA, A, kV, p.u., USD, km, mm², h, ohm…) y una tolerancia relativa del
  0,5 % de la mayor; descartará, con su motivo en el dictamen, las que coinciden, que no cuentan. De una en texto libre
  interpretará «campo: X vs Y» (o «frente a»); si no puede leerla, o la cifra es ambigua («1.250»), o las magnitudes
  son distintas, la mantendrá como contradicción.
- RF-50: SI el código descartó alguna contradicción de un dictamen, ENTONCES EL SISTEMA aplicará la regla de RF-40 a
  las listas que quedan, guardará la decisión que devolvió el LLM y dirá en el informe de la medida, por modo, cuántas
  contradicciones descartó y cuántas decisiones recalculó. Sin nada descartado, la decisión es la del LLM.
- RF-51: CUANDO se pida un dictamen al LLM, EL SISTEMA le dirá que anote solo los valores distintos: si los dos
  valores son iguales, no es una contradicción y no se escribe.

## Requisitos no funcionales

Python 3.12; datos locales; entrenamiento CUDA exclusivo sin fallback silencioso a
CPU; trabajo nativo en carril único y tareas largas cancelables. Preservar entrada,
referencias, parches ajenos y determinismo del conversor. Adaptadores ML opcionales
no bloquean el núcleo. Identidad de fuente/caso y norma se conservan en informes.

## Casos límite

- JSON válido con tarea inexistente: T1, test_tarea_desconocida_rechaza.
- SED en otro alimentador pese al libro viejo: T1, test_entidad_respeta_fuente_activa.
- Reranker elimina coincidencia exacta de código: T2, test_codigo_exacto_se_conserva.
- Ollama apagado, o sin el modelo de embeddings: T2, test_sin_ollama_responde_con_bm25_y_lo_dice.
- Un fragmento cambió y su vector falta: T2, test_vectores_parciales_no_apagan_la_recuperacion.
- Sin CUDA o sin memoria para el reranker: T2, test_sin_cuda_queda_el_orden_hibrido_y_lo_dice.
- Cuatro roles repiten la misma afirmación sin fuente: T3, test_critico_sin_evidencia_no_aprueba.
- Dataset sintético supera umbral de 200 reales: T4, test_qlora_sin_gold_real_bloquea.

## Fuera de alcance

Trading financiero; ejecución autónoma de maniobras por consenso LLM; datos empresariales en API externas; QLoRA obligatorio sin déficit demostrado.

## Criterios de finalización

Cada RF tiene una prueba con cita `047:RF-n`, su tarea cerrada con evidencia y
las regresiones afectadas en verde. Las tareas nativas solo se cierran con el motor
real, sin skip/xfail ni dobles como sustituto. Si se modifica lector/modelo, incluir
los datos reales exigidos por la constitución y las dos disposiciones si aplica.
No declarar promoción, entrenamiento ni aceptación eléctrica a partir del plan.

## Fundamento científico y técnico

El fundamento general incluye la [tesis de maestría de Zhang (UCR, 2024)](https://escholarship.org/uc/item/4g839337), la [tesis doctoral de Stiasny (DTU, 2023)](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/) y los artículos de revistas indexadas citados en la [investigación](../../docs/INVESTIGACION_IA_GEMELO_CONVERSOR_2026-10-31.md#8-fundamento-académico-consultado). Justifican evaluar modelos físicos/híbridos y su trazabilidad; no sustituyen evidencia local ni fijan límites normativos.

[TradingAgents oficial](https://github.com/TauricResearch/TradingAgents) inspira revisión por roles, con licencia Apache-2.0; su paper/repo financiero no se presenta como evidencia eléctrica. [Ollama Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs) y [retrieve/rerank](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html) sustentan los contratos técnicos.

## Clarificaciones de diseño

Continuación solicitada por el usuario: las 200 son propuestas del maestro. Se
corrige la restricción adicional introducida en la ejecución anterior; las tres
órdenes humanas únicas siguen informándose como tales. Las puertas de precisión
no se reducen. Aceptación asistida no concede ejecución autónoma ni acredita
persistencia eléctrica; las acciones que escriben conservan confirmación.

El usuario autorizó la implementación y el entrenamiento con destilación. El estado
aprobada conserva visibles las tareas sin completar.
Las capacidades, datos o licencias ausentes son condiciones detectables de bloqueo,
no autorizaciones para inventar resultados.

El alumno solicitado es el LLM generativo local. Los entrenamientos anteriores del
Transformer clasificador y el ensayo LoRA de un paso se conservan como antecedentes;
no acreditan la destilación completa de este LLM. La autorización expresa permite
experimentar con respuestas del maestro fundamentadas en archivos reales locales;
no convierte instrucciones redactadas en órdenes humanas ni elimina las puertas.
Los 200 casos ya examinados se conservan como benchmark histórico, sin entrenar
sobre sus errores; la nueva prueba se declara y separa antes del nuevo ajuste.

