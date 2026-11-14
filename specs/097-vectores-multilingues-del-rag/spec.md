# Spec 097 — Vectores multilingües para la búsqueda del asistente

Estado: aprobada · Fecha: 2026-11-07 · Origen: usuario, 2026-11-07: «¿el RAG y el LLM están correctamente
sincronizados?» y «si existen fallos o vacíos, buscar soluciones en la web y GitHub; que funcione cada modelo a su máximo
potencial».

## Contexto y objetivo

Los vectores del índice del asistente (047, 077) salen de `nomic-embed-text`, cuya ficha solo declara inglés, y todo el
corpus del proyecto está en español. La búsqueda servida (047) da un Recall@10 de 0,553, y el corpus ampliado (077), que
añade skills, documentos y la API, no pasó su puerta: con 19 758 fragmentos el Recall@10 baja a 0,406 y el MRR@10 empeora
(`docs/EVALUACION_ABSTENCION_077.json`). Hay modelos de vectores multilingües evaluados en MTEB y MIRACL
(multilingual-e5, bge-m3); ninguna fuente los compara en este corpus, así que se miden aquí.

## Usuarios / actores

Operador que pregunta al asistente desde la web; el integrador que mide en la GPU.

## Requisitos funcionales (EARS)

- RF-1: EL SISTEMA guardará con los vectores de cada corpus el modelo que los calculó y sus prefijos, y no mezclará en un
  índice vectores de dos modelos.
- RF-2: CUANDO el modelo de vectores de un corpus cambie, EL SISTEMA dará por pendientes todos sus vectores y los volverá a
  calcular con el nuevo.
- RF-3: EL SISTEMA usará con cada modelo los prefijos de consulta y de documento de su ficha.
- RF-4: EL SISTEMA medirá con el conjunto de calibración de cada corpus el modelo en uso y los candidatos multilingües del
  plan, y elegirá el de mayor MRR@10 y, a igualdad, el de mayor Recall@10.
- RF-5: EL SISTEMA confirmará el elegido una sola vez con el conjunto sellado de su corpus y lo pondrá en uso solo si pasa
  la puerta de la 047 frente al modelo en uso.
- RF-6: SI el elegido no pasa la puerta, ENTONCES EL SISTEMA seguirá con el modelo en uso y el informe dirá qué métrica lo
  impidió.
- RF-7: DONDE el corpus ampliado (077) pase su puerta con el modelo elegido, EL SISTEMA lo servirá en lugar del 047.
- RF-8: SI una pregunta del conjunto de cualquiera de los dos corpus perdió su ancla porque su fuente cambió de sitio, ENTONCES EL SISTEMA medirá sin esa fila, como 077:RF-49, sin editar el conjunto ni cambiar su sello.

### Elección con intervalo y puesta en uso (T3, 2026-11-13)

Origen: auditor del integrador, 2026-11-13. En la calibración de la 047 el híbrido «conserva» 1,000 con bge-m3, 0,973 con
e5-large y 0,811 con nomic, pero con 37 preguntas con respuesta una diferencia de una pregunta no separa dos modelos; el
077 no estaba calibrado, y el MRR@10 del híbrido (0,565) apenas supera al de BM25 (0,553), así que RF-4 elegiría con
ruido. La elección pasa a la operación que sirve la web: abstención fija y cuántas preguntas con respuesta conserva.

- Aclaración de RF-4: la elección la hace RF-11 con la calibración de la abstención; MRR@10 y Recall@10 siguen midiéndose
  (RF-15) y deciden en la puerta de RF-5 frente al modelo en uso.
- RF-9: CUANDO se calibre la abstención con un modelo de vectores, EL SISTEMA guardará con los umbrales las señales de cada
  pregunta (su huella, si tiene respuesta, su tipo y la mejor puntuación de cada método), sin el texto de la pregunta.
- RF-10: EL SISTEMA dará, por modelo y corpus, la fracción de preguntas con respuesta que conserva el híbrido con la
  abstención objetivo y su intervalo bootstrap del 95 %, recalibrando en cada remuestreo estratificado (con y sin
  respuesta por separado).
- RF-11: EL SISTEMA elegirá el modelo de vectores con esta regla, declarada antes de medir el 077: compite el que tiene
  calibración en el 047 y en el 077; queda fuera el que otro supera en un corpus con el intervalo pareado de la diferencia
  de «conserva» por encima de cero sin quedar por debajo en el otro; entre los que quedan, el de menor p95 de latencia de
  la consulta si la diferencia pasa del 20 %, y si no, el de menor memoria de GPU medida.
- RF-12: EL SISTEMA leerá el modelo de vectores en uso de un puntero en la carpeta del asistente, y sin puntero o con un
  modelo sin ficha seguirá con `nomic-embed-text`.
- RF-13: SI la calibración de la abstención se hizo con un modelo de vectores distinto del que está en uso, ENTONCES EL
  SISTEMA la tratará como no calibrada, porque el umbral del coseno depende de la escala de cada modelo.
- RF-14: CUANDO se ponga en uso un modelo de vectores, EL SISTEMA escribirá el puntero solo si su medición sellada del 047
  es de ese modelo y pasa la puerta de RF-5 frente a la medición sellada del modelo en uso.
- RF-15: EL SISTEMA informará de cada medición de recuperación R@1, R@5, R@10, MRR@10, nDCG@10, cita exacta@1 y el p95 de
  latencia, cada una con su intervalo bootstrap del 95 %, con el desglose por tipo de pregunta y por corpus.
- RF-16: EL SISTEMA guardará las preguntas reales que el operador hizo al asistente en un conjunto propio, con su
  procedencia y su huella, separado del sintético del maestro.
- RF-17: EL SISTEMA medirá las preguntas reales del operador aparte de las sintéticas y nunca sumará las dos cifras, como
  085:RF-23.
- RF-18: SI el fichero de la fuente de una pregunta ya no está en el corpus y hay en él un único fichero con el mismo nombre,
  ENTONCES EL SISTEMA buscará el ancla en ese fichero, sin editar el conjunto ni cambiar su sello (el frontend pasó de
  `components/` a `features/` y 34 de 308 preguntas de la calibración del 077 perdían su ancla).

### Ningún conjunto de evaluación dentro de lo que lo juzga, y hit@10 (2026-11-13)

Origen: diagnóstico D077 del integrador, 2026-11-13. 231 de las 308 preguntas de la calibración de la abstención del 077
estaban literales en `docs/PREGUNTAS_MAESTRO_076.md`, que el corpus 077 indexaba por `docs/*.md` (076:RF-29). La calibración
sale del reparto «corpus» de la 076 y 076:RF-31 solo apartaba el «sellado»: BM25 encontraba la pregunta copiada y no su
respuesta, el umbral de abstención subía con ella y Recall@10 del sellado con la puerta calibrada caía a ~0,05 (sin la
copia, 0,125, lo medido el 2026-11-03). Con hasta 16 trozos que responden una pregunta, Recall@10 tampoco dice si se halló
alguno.

Decisión del usuario, 2026-11-13 (opción A): `docs/PREGUNTAS_MAESTRO_076.md` se queda en el corpus 077, como decidió el
2026-11-04 (076 T8, «sí entran»); la fuga se corrige cambiando de dónde salen las preguntas que miden el corpus, no sacando
el documento. Descartada la opción B (sacarlo por su contenido): anulaba esa decisión.

- RF-19: EL SISTEMA formará la calibración y el sellado de un corpus del asistente con preguntas que no aparecen en él: sin
  las que, ellas o una de su grupo de paráfrasis, estén literales en un fichero del corpus que no sea su fuente, y con las
  sin respuesta solo si el maestro confirmó que el repositorio no la tiene; los documentos que el corpus indexa por decisión
  del usuario (076:RF-29) siguen en él. No calibrará con menos de 100 preguntas sin respuesta ni de 30 con ella, y dirá cuántas faltan:
  con n sin respuesta el umbral es su cuantil ⌈(n+1)(1−α)⌉/n (Angelopoulos y Bates, arXiv 2107.07511), que con 25 y
  α=0,05 es el máximo. El maestro amplía la calibración con preguntas nuevas, de origen `maestro`, que no estén en el corpus.
- Aclaración de 077:RF-44 por RF-19: la calibración del 077 sigue saliendo del reparto `corpus` de la 076, sin las filas que
  el corpus ya lleva (el documento del maestro copia las marcadas correctas; quedan las que no copia, 076:RF-30).
- RF-20: EL SISTEMA comprobará en cada commit que ninguna pregunta de seis palabras o más de un conjunto de evaluación de la
  recuperación (047, el reparto `sellado` de la 076, 077 y el del operador de RF-16) aparece literal en el corpus que la
  mide, con el documento del maestro dentro del 077, salvo en un fichero que la propia pregunta cita como su fuente.
- RF-21: DONDE esté el almacén real del asistente, EL SISTEMA comprobará que ninguna orden de entrenamiento del intérprete
  tiene el texto de una de selección, calibración, prueba, examen del maestro (085), humana confirmada, mensaje reservado o
  prueba sellada (070, 079).
- RF-22: SI falta el almacén real del asistente, ENTONCES EL SISTEMA omitirá la comprobación de RF-21 nombrando la variable
  que lo indica.
- RF-23: EL SISTEMA dará en cada medición de recuperación, además de Recall@10, la fracción de preguntas con respuesta que
  tienen algún trozo correcto entre los 10 primeros (hit@10), sin que decida ninguna puerta ni la elección del modelo.

## Requisitos no funcionales

Local, sin red al responder (P9); los vectores se calculan como trabajo aparte y cancelable (047:RF-22 a RF-24); solo CUDA
para medir.

## Casos límite

Un candidato que Ollama no tiene instalado se omite y se dice; un corte a mitad de cálculo conserva lo hecho (047:RF-24).

## Fuera de alcance

Entrenar o afinar el modelo de vectores; cambiar el reranker o los umbrales de la 047 sin su calibración.

## Criterios de finalización

Cada RF citado por una prueba (`grep -rnoE "097:RF-[0-9]+" tests`); informe de calibración y sellado en `docs/`, fuera de
los datos de la distribuidora.

## Fundamento

- [nomic-embed-text v1.5, ficha](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5): solo la etiqueta «English».
- [Multilingual E5 Text Embeddings: A Technical Report](https://arxiv.org/pdf/2402.05672).
- [BGE M3-Embedding](https://www.emergentmind.com/papers/2402.03216): más de 100 idiomas; en Ollama, solo vectores densos.
- Las fuentes de RF-9 a RF-17, con lo que se toma de cada una, están en el plan (sección «T3»).
- RF-19 a RF-23: el diagnóstico D077 (`D:/csg/D077/fuga_sin_respuesta_077.py`, `diagnostico_anclas_077.py`), en el plan
  (sección «Fuga de los conjuntos»).
