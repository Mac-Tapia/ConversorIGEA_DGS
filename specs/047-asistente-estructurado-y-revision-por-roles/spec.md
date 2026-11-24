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
- RF-52: CUANDO compare los dos valores de una contradicción, EL SISTEMA leerá la cifra aunque venga con separador
  de miles «.», «,», espacio o espacio fino, coma decimal, prefijos «$», «US$», «>», «≈» o «k», marcas como «_3_» o
  «/^3$/i», o dentro de una frase con una sola cifra («Cargabilidad máxima de A71 74 %» es 74 %), sin tomar por cifra
  un elemento de la red («A71», «S-702»); una cifra ambigua («12.400») coincide si una de sus lecturas es la del otro
  valor, y una sin unidad, si es la del otro en la unidad base de su magnitud («1250» y «1,25 MW»). Una frase con
  varias cifras no coincide. MEJ24c, 2026-11-21: con el 047d, «>$14500», «_3_» o una frase con «74 %» bloqueaban sanos.
- RF-53: CUANDO un dictamen traiga una contradicción, EL SISTEMA solo la contará si su valor de la propuesta está,
  normalizado, en el texto de la propuesta y su valor de la evidencia en el fragmento de la fuente citada (de una
  cuenta, cada operando, en la fuente o en la propuesta); si no, o si la fuente no es una evidencia del paquete, la
  descartará como no fundada, con su motivo. Sin el texto de la fuente la mantendrá. Con el 047d, «user», «github»,
  «kOhm» o «Shekels» contaban como valores de la propuesta.
- RF-54: SI el campo de una contradicción es un dato de la propuesta, ENTONCES EL SISTEMA comparará el valor que da la
  propuesta, no el que copió el LLM, y guardará el copiado.
- RF-55: CUANDO se pida un dictamen al LLM, EL SISTEMA le pedirá en cada contradicción la base (total o unidad) y que
  compare el mismo concepto, con la cuenta del total («cantidad × precio») si la evidencia da un precio por unidad;
  el código calcula la cuenta. SI la fuente da la cifra por unidad («por unidad», «por km», «c/u», «/km») o el
  dictamen declara otra base que la del campo de la propuesta, ENTONCES no será una contradicción y se descartará.
- RF-56: SI una contradicción enfrenta el texto de la acción con el de una evidencia, ENTONCES EL SISTEMA la
  descartará (la acción es lo que se revisa, RF-46); una cifra de la acción distinta de la de la evidencia cuenta.
- RF-57: CUANDO se vuelva a sellar con el prompt vigente un corpus reubicado, EL SISTEMA resolverá cada fuente por su
  manifiesto de custodia, comprobando su sha256 y sus bytes con lo custodiado, escribirá cada fuente con su ruta
  resuelta, recalculará de forma determinista `record_id` y `dataset_hash`, y dejará en el manifiesto nuevo el rastro
  del sellado anterior: su manifiesto custodiado, sus huellas de dataset y de prompt, la huella de la reubicación, las
  fuentes resueltas y el par de `record_id` anterior y nuevo de cada registro. MEJ29, 2026-11-21: el sellado v6 de la
  T7 se paraba con «fuente ausente o invalida» porque leía las fuentes en su ruta anterior a la reubicación del 065.
- RF-58: SI una fuente del corpus no tiene resolución en la custodia, o su copia custodiada no casa por sha256 o por
  bytes, o el manifiesto de reubicación falta o tiene otra huella, ENTONCES EL SISTEMA no sellará nada y dirá qué
  fuente se rechaza y por qué.
- RF-59: (d8, 2026-11-20, T4) CUANDO `tools/asistente_qlora.py entrenar` reciba el corpus de órdenes, EL SISTEMA exigirá
  la decisión de `decidir_ajuste` (`--decision`, con `necesaria`) o un experimento autorizado por su id
  (`--experimento-autorizado`, el de T7 del plan); sin ninguno de los dos se niega antes de pedir la GPU, y el manifiesto
  guarda la decisión y el experimento. El corpus de redacción del PIDE (072:RF-51) no lo pide.
- RF-60: CUANDO se elija la versión del alumno con selección, EL SISTEMA comparará las familias de cada informe con las
  tareas que declara para selección el manifiesto sellado del corpus (`por_tarea`), y no con el catálogo vigente. Exigirá
  que ese manifiesto sea el del mismo `dataset_hash` y `prompt_hash` que los informes. Rechazará un informe al que le
  falte o le sobre una tarea sellada y dirá cuáles. La elección dirá sus tareas selladas y, como «no cubiertas por este
  sellado», las tareas del catálogo vigente que el corpus no tiene, sin darlas por medidas. MEJ29b, 2026-11-21: el
  corpus v6 se selló con 27 tareas, el catálogo creció después, y `elegir` daba «metricas de seleccion incompletas» con
  un informe completo para su corpus.
- RF-61: CUANDO se abra la prueba sellada, EL SISTEMA exigirá que la elección se haya hecho con las tareas que declara
  el manifiesto del corpus. Su informe dirá las tareas selladas de la partición y las no cubiertas por ese sellado.

### Órdenes revisadas por el maestro (T12, MEJ35, 2026-11-21)

El usuario, el 2026-11-19: la revisión de las órdenes la puede hacer una persona o un revisor independiente marcado
`origen: maestro` (como en 085:RF-19 para el intérprete). El 2026-11-21, en la GPU, `decidir_ajuste` seguía en
«bloqueada» con 3 de 200 órdenes humanas, y eso paraba la evaluación final de la T4 y el QLoRA de la campaña 043 T9:
RF-8 y RF-9 solo contaban `gold_human` y la 085 dejó fuera de su alcance `ajuste_condicionado.py`. Esto amplía RF-8 y
RF-9 mientras haya menos de 200 humanas; las del maestro nunca son humanas ni se suman a ellas.

- RF-62: EL SISTEMA registrará las órdenes revisadas por el maestro con `tools/asistente_ordenes_reales.py
  revisar-maestro`, cada una con su texto, su tarea del contrato vigente `TAREAS`, sus datos con sus tramos, su autor,
  su revisor, su veredicto, su motivo y el origen `maestro`, en un conjunto de prueba sellado con su huella
  (`<almacén>/maestro_real/revisadas_047/`), con la calidad `gold_maestro_revisada`, que nunca entrena.
- RF-63: SI una orden revisada no tiene el origen `maestro`, revisor o motivo, nombra una tarea que no existe, un dato
  sale de su texto o no es de su tarea, le falta uno obligatorio, repite el texto de otra, o coincide en texto o
  familia (075:RF-2) con una orden humana o del maestro que entrena (085:RF-1), ENTONCES EL SISTEMA no la sellará y la
  contará por su motivo; las que el revisor rechazó se cuentan y no se sellan. SI el conjunto no cubre todas las
  tareas de `TAREAS`, ENTONCES no sellará nada; y no sustituirá un conjunto ya sellado por otro distinto.
- RF-64: MIENTRAS haya menos de 200 órdenes humanas distintas y haya un conjunto sellado de 200 o más órdenes revisadas
  por el maestro, medido sin fuga con el entrenamiento, EL SISTEMA aplicará las puertas de RF-9 (027:RF-18) y la
  decisión de RF-8 a ese conjunto, con la base `maestro_revisadas`.
- RF-65: CUANDO decida con la base `maestro_revisadas`, EL SISTEMA dirá en la decisión que son órdenes revisadas por el
  maestro, no humanas, con su denominador, su huella y cuántas humanas faltan, y seguirá dando aparte la medida humana,
  sin que decida.
- RF-66: SI el conjunto que decide mezcla calidades, o con la base `maestro_revisadas` hay 200 humanas o más, o el
  conjunto no está sellado o no es de origen `maestro`, ENTONCES EL SISTEMA dará «bloqueada» y dirá por qué; con 200
  humanas o más deciden las humanas, como hasta ahora.
- RF-67: EL SISTEMA no contará las órdenes revisadas por el maestro como humanas en ningún informe, ni para la
  confirmación obligatoria de 027:RF-19 ni para la ejecución autónoma.
- RF-68: CUANDO `tools/aceptar_agente.py evaluar` mida el conjunto sellado, EL SISTEMA comprobará su sello, guardará la
  decisión de ajuste en `decision_ajuste.json`, que lee `tools/asistente_qlora.py --decision`, y
  `tools/reentrenar_modelos.py run --qlora-decision` la pasará a la etapa QLoRA.

### Corpus v7 de órdenes con el contrato vigente (T7d, MEJ34, 2026-11-21)

- RF-69: (MEJ34, 2026-11-21, T7d) CUANDO se prepare el corpus de órdenes del alumno destilado, EL SISTEMA cubrirá en sus
  cuatro particiones las 67 tareas del contrato vigente `TAREAS` y lo sellará con el prompt del perfil
  `llm_destilado_v2` (`sistema_alumno_contrato`), que nombra cada una; el perfil `llm_destilado_v1` (29 tareas hasta la
  069) conserva su huella para los corpus v5 y v6. El entrenamiento, la evaluación, la elección y el cliente de Ollama
  usarán el prompt y las tareas del perfil que selló el corpus; la elección compara con las tareas
  que declara su manifiesto sellado (RF-60), y el del v7 declara las 67. Caso real: el v6 cubría 27 de las 67 tareas y su alumno
  no conocía calibrar, escanear, la escalera de obras, el PIT, la nube ni la biblioteca normativa.
- RF-70: EL SISTEMA declarará en cada fila del corpus v7 su origen (maestro o sintético controlado; las órdenes humanas
  confirmadas se reservan aparte, con origen humano, y nunca entran en una partición redactada) y no escribirá ningún
  nombre real: los valores de la fuente (alimentador, SED, SET, sistema, proyecto y rutas) se seudonimizan, el mapa
  guarda solo la huella de cada original, y SI el detector de nombres de la entrega (086:RF-33) encuentra uno en el
  corpus, sus contextos o su manifiesto, ENTONCES no se escribirá nada.
- RF-71: las frases de las tareas posteriores a la 069 serán del maestro, una columna por partición (entrenamiento,
  selección, calibración y prueba) que no se cruzan, con los datos obligatorios de cada tarea; las de entrenamiento suman
  las plantillas del catálogo y `ESTILO_REAL`, y ninguna fila repite un texto de las pruebas selladas del intérprete ni
  una orden humana reservada.
- RF-72: CUANDO ninguna fuente aporte el valor que pide una tarea (la carpeta del caso del VAD, el .json de una norma, la
  carta del solicitante, el libro del PIT, el informe o la salida que se envía o publica), EL SISTEMA usará un valor
  sintético controlado, uno por partición, declarado en la fila (`valores_sinteticos`) y en el manifiesto; la auditoría
  rechaza uno no declarado.
- RF-73: EL SISTEMA copiará cada fuente del corpus v7 a su propia custodia (`fuentes/<sha256>.bin`), comprobando su
  sha256 y sus bytes con los del v6; SI una no casa, ENTONCES no preparará nada y dirá cuál.
- RF-74: la prueba, la selección y la calibración se fijarán con su huella al preparar el corpus, antes de sellar y de
  entrenar; SI al sellar o al leer una partición apartada su huella no es la fijada, ENTONCES EL SISTEMA no la sellará ni
  la leerá. La preparación deja medidos su tiempo y su coste (sin GPU ni llamadas a modelos).
- RF-75: CUANDO el valor de la evidencia de una contradicción sea una cuenta con + − × · x / y paréntesis, EL
  SISTEMA la evaluará con un analizador propio (nunca `eval`) y comparará el resultado con la tolerancia; solo la
  contará si cada operando está, normalizado, en el fragmento de las fuentes citadas o, la cantidad, en la
  propuesta. Una relación como «22,9/0,40 kV» no es una división. MEJ24d, 2026-11-21: con el 047e, «14 × 52 = 728»
  citando solo la fuente de la cantidad se descartaba como no fundada y el defecto se perdía.
- RF-76: SI la fuente da la cifra por unidad o por kilómetro y el campo de la propuesta es un total, ENTONCES EL
  SISTEMA la multiplicará por la cantidad anclada (un único campo de piezas de la propuesta, o las piezas que nombra
  la acción, de las que habla la fuente; los kilómetros de la acción o de un campo `*_km`) y comparará el total, y
  solo sin cantidad la descartará. La base la dice el texto («por unidad», «c/u», «cada uno», «/km», «por km»); la
  que declara el dictamen se guarda y no descarta nada. Con el 047e el modelo declaraba «unidad» en «0,92 p.u.».
- RF-77: CUANDO se revise una propuesta con `coste_usd` y la evidencia dé sus importes, EL SISTEMA calculará el
  coste sin el LLM (un total explícito «en total»; si no, la suma de las partidas, con cada precio por unidad o por
  km multiplicado por su cantidad anclada, y un importe que es la suma de los demás de su fragmento como su total),
  lo guardará con la cuenta en `comprobaciones_del_codigo` y, si no cuadra con la tolerancia, no aprobará la
  revisión. Sin cantidad anclada, con varios totales explícitos o sin importes no comprobará nada. La medida cuenta
  por modo las que no cuadran.
- RF-78: CUANDO una contradicción cite varias fuentes («e1 e2», «e1, e2»), EL SISTEMA buscará sus valores en todas;
  una que no esté en el paquete la hace no fundada. El encargo lo dice para las cuentas.
- RF-79: SI el código comprobó un campo de la propuesta con la evidencia y cuadra (RF-77), ENTONCES EL SISTEMA
  descartará, con su motivo, las contradicciones del LLM sobre ese campo. MEJ24e, 2026-11-22: con el 047f, el modelo
  comparaba el coste total con cada partida («18900» frente a «16.400») y bloqueaba una propuesta sana.
- RF-80: SI una incertidumbre es solo el nombre de un campo de la propuesta cuyo valor está en la acción, ENTONCES EL
  SISTEMA la descartará con su motivo, porque la acción fija ese valor (RF-46); si el valor solo está en una
  evidencia, se mantiene (y, si el código respalda todos los datos, queda como observación: RF-91). Con algo
  descartado, la decisión sale de las listas que quedan (RF-50).
- RF-81: SI un dictamen no es válido y el revisor respondió (por ejemplo, «bloqueada» sin hallazgo), ENTONCES EL
  SISTEMA se lo pedirá de nuevo en la ronda siguiente, que le muestra el motivo, sin convertirlo en ninguna decisión.
  Con el 047f, un rol de riesgo bloqueó un caso sano sin decir qué estaba mal y no hubo otra ronda.
- RF-82: CUANDO se pida el dictamen de riesgo (o del rol único), EL SISTEMA le dirá que también es un riesgo que la
  evidencia prohíba o limite la forma de hacer la acción (procedimiento de seguridad, trabajo en caliente, maniobra no
  permitida), y que cada riesgo que señala la evidencia va en incertidumbres con el ID y la frase de la evidencia.
- RF-83: SI una contradicción enfrenta un valor de la acción que no es solo una cifra con su unidad (y, como mucho, dos
  palabras), ENTONCES EL SISTEMA la descartará como texto de la acción (RF-56): con el 047f, la frase de la acción
  «… para cambiar 2 aisladores» se leía como la cifra 2 frente a los «22,9 kV» de la evidencia.

- RF-84: (23-11, 047 T7c cortada por una suspensión del equipo) CUANDO se pida `entrenar --reanudar` con un punto de
  control de una época sin terminar, EL SISTEMA retomará esa época desde él, con la verificación de datos, base,
  configuración y época de la reanudación, y lo dirá en el informe (`reanudado_desde`); sin la opción, desde cero.
  (La época 1 de 047 T7c se cortó en el ejemplo 1 352 de 3 280 con un punto de control en la actualización 128.)
- RF-85: SI una incertidumbre es solo el nombre de un campo que el código comprobó con la evidencia y cuadra (RF-77),
  ENTONCES EL SISTEMA la descartará con su motivo, como ya descarta las contradicciones sobre ese campo (RF-79). Con
  el 047g (2026-11-23), el LLM dejaba «coste_usd» como duda en propuestas sanas cuyo coste cuadraba.
- RF-86: SI una incertidumbre, o el valor de la propuesta de una contradicción sobre un campo que la propuesta no tiene,
  es solo la acción o un trozo suyo de tres palabras o más, sin cifras, ENTONCES EL SISTEMA la descartará: la acción es
  lo que se revisa (RF-46). Con el 047g, un rol copiaba la acción entera como duda, y otro enfrentaba «conductor de
  enlace» con la descripción del conductor en la evidencia. Un elemento de la red («estructura E19») sigue contando.
- RF-87: SI una contradicción enfrenta un campo que es una cantidad de elementos (sin unidad ni palabra de magnitud en
  su nombre y con un entero sin unidad) con una cifra de la evidencia que tiene unidad, la del valor o la de esa cifra
  en la fuente, ENTONCES EL SISTEMA la descartará como magnitudes distintas. Con el 047g, la cantidad de picas se
  enfrentaba con la longitud de cada pica.
- RF-88: SI una frase de la evidencia prohíbe un verbo (en infinitivo, con pronombre o no: «prohíbe abrirlo», «no está
  permitido cortar») y la acción lleva ese verbo, ENTONCES EL SISTEMA lo hallará sin el LLM y lo guardará en
  `comprobaciones_del_codigo` como no coincidente, así que la revisión no se aprobará. Con el 047g, en el modo equipo
  ningún rol vio la maniobra prohibida, aunque el encargo lo pide (RF-82).
- RF-89: EL SISTEMA respaldará sin el LLM cada dato numérico de la propuesta que sea una cantidad de elementos fijada
  por la acción o cuya cifra esté en un fragmento de la evidencia fuera de una cláusula de límite o de norma, y lo
  guardará en `comprobaciones_del_codigo` como coincidente; una duda o una contradicción sobre ese dato se descartará
  como las del coste (RF-79, RF-85). Con el 047h (2026-11-23), el LLM dudaba de una cargabilidad que la evidencia daba
  y enfrentaba la tensión de la máxima con la del valle del mismo fragmento. Faltar en la evidencia no es contradicción.
- RF-90: SI un fragmento de la evidencia nombra un elemento con el mismo prefijo que uno de la acción («S-2209» frente a
  «S-2290») y ninguno de la acción con ese prefijo, ENTONCES EL SISTEMA lo guardará sin el LLM como comprobación no
  coincidente y la revisión no se aprobará. Con el 047h, la medición de otra SED respaldaba el cambio de tap y la
  revisión solo se bloqueó por una duda sin relación.
- RF-91: SI el código respalda cada dato numérico de la propuesta (RF-77, RF-89) y ninguna de sus comprobaciones falla,
  ENTONCES EL SISTEMA guardará como observaciones, sin bloquear, las incertidumbres del LLM y sus contradicciones sobre
  un campo que la propuesta no tiene; las contradicciones sobre un dato siguen contando, y aprobar no autoriza la
  ejecución (RF-6, la confirma el operador). Con el 047h, los roles bloqueaban propuestas sanas preguntando por lo que
  la propuesta no dice («tipo de aislador», «si hacen falta más reconectadores»).
- RF-92: EL SISTEMA leerá como precio por unidad, al calcular el coste (RF-77), «la unidad», «cada una», «por pieza»,
  «por equipo», «por juego», «por elemento» y «por aparato», y como precio por km «el kilómetro» y «cada kilómetro»; y
  SI el fragmento de un precio unitario no nombra la pieza con la palabra de un campo, ENTONCES tomará la cantidad de la
  única cantidad de piezas de la propuesta, y con varias no calculará nada. Con el 047i (2026-11-23), el código daba por
  malo el coste de tres propuestas sanas («185 dólares la unidad», «12.500 USD por equipo», «9.000 USD el kilómetro»).
- RF-93: EL SISTEMA leerá también como prohibición de RF-88 «no permite(n)», «no autoriza(n)», «no admite(n)», «queda(n)
  prohibido», «está(n) vedado», «en ningún caso» y «jamás»; y SI lo prohibido es hacerlo «sin» algo, ENTONCES solo
  contará cuando la acción también lo hace «sin» eso. Con el 047j (2026-11-23), «las reglas de seguridad no permiten
  trabajar … sin puesta a tierra temporal» no se leía como prohibición y en los dos modos se aprobó la acción que lo hacía.
- RF-94: EL SISTEMA leerá también como prohibición de RF-88 una negación («ningún(a)», «nadie», «no») seguida de «está(n)»,
  «queda(n)», «es», «son» o «se encuentra(n)» y un participio de permiso («autorizado», «habilitado», «facultado»,
  «permitido», «acreditado»). Con el 047k (2026-11-24), «ninguna cuadrilla está autorizada a maniobrar con carga los
  seccionadores unipolares» no se leía, y en el modo equipo el caso quedó sin respuesta.
- RF-95: EL SISTEMA leerá como precio por unidad de RF-76 la cifra que va «por» o «cada» una pieza que la acción cuenta
  («US$ 8 800 por banco» con «instalar 2 bancos…»), además de las palabras fijas de RF-76. Con el 047l (2026-11-24),
  antes de medir, la comprobación del código sin LLM leía ese precio como un total y daba una falsa alarma en un caso sano.
- RF-96: EL SISTEMA no tomará como cantidad de piezas una cifra de la acción seguida de una unidad física («150 kvar»,
  «200 A»), y la cifra que va «por» o «cada» una pieza tomará la cantidad de esa pieza. Con el 047m (2026-11-24),
  «USD 2 600 por banco» y «montar 3 bancos … de 150 kvar» no se comprobaban y el modelo bloqueó el caso sano.
- RF-97: SI una frase de la evidencia exige algo («exige», «requiere», «debe», «es obligatorio»…) antes del verbo de la
  acción Y la acción lo hace «sin» algo que comparte una palabra con lo exigido, ENTONCES EL SISTEMA lo contará como
  incumplimiento (sin el LLM); si la acción no dice «sin», lo decide el revisor. Los sistemas de cumplimiento normativo
  clasifican cada frase por su modalidad (obligación, permiso, prohibición) con sus disparadores (ComplianceNLP,
  arXiv 2604.23585; LEXDEMOD). Con el 047m, el modelo aprobó en los dos modos reponer un fusible sin despejar la causa.
- RF-98: SI un dato de la propuesta en %, pu, A, kA, kW, kVA o MW (o de usuarios) nombra un elemento, o la acción lo
  nombra, Y un fragmento da para ese elemento, fuera de las cláusulas que empiezan por un límite («límite…», «capacidad
  del…», «el mínimo es…»), una única cifra distinta en esa unidad, ENTONCES EL SISTEMA lo contará como contradicción
  (sin el LLM). Con el 047m, el modelo aprobó «carga 64 %» frente a «la SED … trabaja al 141 %».
- RF-99: EL SISTEMA leerá con una sola regla las cotas cuantitativas de la evidencia, se escriban como se escriban
  (superiores: «como máximo», «a lo sumo», «no más de», «límite de», «no puede pasar de», «no debe superar»…; inferiores:
  «como mínimo», «al menos», «no menos de»…; y la que se da por su consecuencia, «mayor de 40 K … se pierde la
  coordinación»), con la cantidad llevada a una unidad base por magnitud (minutos, A, kW, kVA, kV, %, pu, K), y contará
  como incumplimiento la acción cuya cifra en esa magnitud la pase; también la prohibición dicha con el sustantivo del
  verbo de la acción («prohíbe la poda»), por su tema léxico. Con el 047n (2026-11-24), «admite como máximo 2 horas de
  corte» frente a «desconectar … 4 horas» se escapó a las dos formas sueltas que había antes, y al modelo en los dos modos.
- RF-100: SI la acción maniobra, corta o trabaja en un elemento Y la evidencia dice que a ese elemento le falta una
  salvaguarda («sin seccionador ni interruptor», «sin enlace con otro alimentador», «sin respaldo»), ENTONCES EL SISTEMA
  no la aprobará sola: queda para el operador. Es la lista de comprobación de seguridad que el código arma antes del
  revisor (AGrail, arXiv 2502.11448): los riesgos que no dependen de interpretar la red no se dejan al modelo de 8B.
  Lo mismo SI la evidencia solo permite algo a un agente («solo el centro de control puede ordenar la apertura…») Y la
  acción trata de lo mismo sin nombrar a ese agente: un permiso restringido es una prohibición para los demás.
- RF-101: SI un resultado físico de la propuesta (kW, kVA, kvar, MW, MVA, pu, %, A, kA, kV) no lo respalda ni lo
  contradice ningún fragmento, ENTONCES EL SISTEMA no lo aprobará: queda sin fuente. Con el 047, el modelo aprobó una
  «reducción de pérdidas de 120 kW» que ninguna evidencia daba.
- RF-102: SI tras el reintento de RF-81 un revisor sigue diciendo «bloqueada» o «revisar» sin ninguna contradicción
  ni incertidumbre Y el código respalda todos los datos de la propuesta sin ninguna comprobación fallida, ENTONCES EL
  SISTEMA lo guardará como observación y decidirá la comprobación del código; en la primera ronda, o sin todo
  respaldado, sigue sin respuesta (RF-38). EL SISTEMA dará también por respaldado un coste 0 cuando la evidencia diga
  que no lo hay («sin materiales», «sin costo», «no necesita materiales»). Con el 047o (2026-11-24), en los dos modos,
  dos sanos con todos sus datos respaldados quedaron sin respuesta porque el modelo bloqueó sin motivo en las dos rondas.

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

