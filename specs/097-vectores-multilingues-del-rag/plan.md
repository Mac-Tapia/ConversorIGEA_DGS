# Plan 097 — Vectores multilingües del RAG

## Dónde

- `src/convertersmartgrid/asistente/indice.py`: `vectores_meta.json` ya guarda `modelo` y `prefijo`; el modelo y los prefijos
  pasan a una ficha por modelo (`FICHAS_EMBEDDINGS`) y al leer los vectores se descartan los de otro modelo (RF-1 a RF-3).
- `src/convertersmartgrid/asistente/ollama.py`: `embeddings(textos, modelo)` ya acepta el modelo.
- `tools/asistente_evaluar_rag.py`: `--modelo-vectores` para calibrar y sellar con cada candidato (RF-4 a RF-6).
- Servicio: el modelo de vectores en uso se lee de la política de `reranker.servicio()` junto con el corpus (RF-7).

## Decisiones

- Candidatos: `nomic-embed-text` (en uso), `bge-m3` (Ollama; `ollama pull bge-m3`, unos 1,2 GB) y
  `jeffh/intfloat-multilingual-e5-base` si existe en Ollama; e5 por sentence-transformers queda fuera para no añadir otra vía.
- Se elige con la calibración y se sella una vez: medir varios en el sellado sería elegir con la prueba.

## Pruebas

`tests/test_asistente_vectores_097.py`: vectores de otro modelo no cuentan y se recalculan; prefijos por ficha; la elección
con métricas sintéticas; sin pasar la puerta sigue el modelo en uso.

## T3 (2026-11-13): elección con intervalo, puntero en uso y conjunto del operador (RF-9 a RF-18)

- `evaluacion_rag.py`: `leer_puntuaciones` lleva la huella y el tipo de cada pregunta; `calibracion_con_senales` guarda las
  señales sin el texto (RF-9); `conserva_con_intervalo` y `elegir_con_intervalo` recalibran el par coseno-BM25 en cada
  remuestreo estratificado, vectorizado con numpy (RF-10, RF-11); `con_intervalos` da cada métrica con su IC95 % y por tipo,
  y `evaluar` y `medir_sellado` lo guardan (RF-15); `_SigueMovidos` sigue a un fichero que cambió de carpeta con nombre
  único (RF-18); `cargar_conjunto_operador` y `por_procedencia` (RF-16, RF-17).
- `indice.py`: `PUNTERO_VECTORES` (`vectores_en_uso.json` en la carpeta del asistente) y `modelo_vectores()` lo lee
  (RF-12); `poner_en_uso` comprueba la puerta de la 047 (`_puerta`) frente a la sellada del modelo en uso y solo con
  `escribir` deja el puntero (RF-5, RF-6, RF-14).
- `reranker.py`: `abstencion` rechaza la calibración de otro modelo de vectores (RF-13) y, sin ruta, usa la del puntero;
  `servicio` toma la medición del 077 del puntero y la rechaza si es de otro modelo.
- `tools/asistente_evaluar_rag.py`: `--calibracion`, `--elegir`, `--remuestreos`, `--operador`, `--poner-en-uso`
  (`--sellado-047`, `--sellado-077`, `--calibracion-077`, `--sellado-en-uso`, `--aplicar`); la calibración guarda el p95 de
  latencia de la consulta y la memoria de GPU que da Ollama (`/api/ps`).
- Decisión: regla de elección por «conserva» con abstención fija, no por MRR@10 del híbrido (descartado: con 37 preguntas el
  MRR del híbrido apenas separa de BM25). Decisión: seguir los ficheros movidos al resolver, no un conjunto v2 (descartado:
  un conjunto nuevo cambia el sello que cita la política en uso, `docs/EVALUACION_RAG_047.json`).
- Pruebas: `tests/test_asistente_vectores_097_t3.py`, sintéticas sorteadas.

Fuentes, con lo que se toma de cada una:
- [BGE-M3, Chen et al. 2024, arXiv 2402.03216](https://arxiv.org/abs/2402.03216) y su
  [ficha](https://huggingface.co/BAAI/bge-m3): más de 100 idiomas, hasta 8192 tokens, y «no longer requires adding
  instructions to the queries»: prefijos vacíos (RF-3).
- [mE5, Wang et al. 2024, arXiv 2402.05672](https://arxiv.org/abs/2402.05672) y la
  [ficha de multilingual-e5-large](https://huggingface.co/intfloat/multilingual-e5-large): «query: » y «passage: », sin
  ellos el rendimiento cae; trunca a 512 tokens.
- [MMTEB, arXiv 2502.13595](https://arxiv.org/abs/2502.13595) y el
  [leaderboard MTEB](https://huggingface.co/spaces/mteb/leaderboard): define MTEB(Europe) y sitúa multilingual-e5-large
  4.º en MTEB(Multilingual) y MTEB(Europe); no se halló una tabla solo de español, por eso se mide en este corpus.
- [BEIR, Thakur et al. 2021, arXiv 2104.08663](https://arxiv.org/html/2104.08663v4), §3.3: nDCG@10 como métrica principal
  porque equilibra relevancia binaria y graduada; MRR@10 y Recall@k como en MTEB (RF-15).
- [bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3): 0,6 B, sobre bge-m3, multilingüe;
  [mmarco-mMiniLMv2-L12-H384-v1](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1): 0,1 B, mMARCO
  traducido a 14 idiomas; el reranker en uso no cambia (fuera de alcance).
- Efron y Tibshirani, *An Introduction to the Bootstrap* (1993): intervalo percentil por remuestreo de la unidad
  experimental (la pregunta), estratificado como la calibración.

## Fuga de los conjuntos y hit@10 (2026-11-13, RF-19 a RF-23)

- `fuga_evaluacion.py` (nuevo): `CONJUNTOS_RAG` (qué conjunto mide qué corpus), `preguntas_de` (las tres formas de los
  conjuntos; del JSONL de la 076, un reparto), `fugas` (por palabras sin tildes, mayúsculas ni signos, buscando cada
  pregunta por sus primeras palabras, desde seis o desde las que se pidan), `fugas_del_corpus` y `fugas_del_interprete`
  (solo cuentas, nunca textos del operador).
- Decisión del usuario (2026-11-13, opción A): el documento del maestro se queda en el 077 (076:RF-29, 076 T8). RF-19 se
  cumple al formar los conjuntos: `evaluacion_rag.conjunto_de_entregables(..., sin_las_del_corpus=True)` quita las filas
  cuya pregunta, o una de su grupo de paráfrasis, está literal en un trozo del corpus que no es su fuente, de cualquier
  longitud (`fugas(..., min_palabras=1)`: ahí una coincidencia que no es copia solo quita una pregunta, y el documento trae
  67 de menos de seis palabras), lo ajeno que también esté, y las sin respuesta que el maestro marcó incorrectas (dicen que
  el repositorio sí la tiene). El fichero guarda `origen_de_las_preguntas` y lo excluido por cada motivo.
  `tools/asistente_indice_ampliado.py conjuntos` forma así los dos conjuntos; `--rehacer-calibracion` rehace la
  calibración, que no está sellada; el sellado existente no se rehace (077:RF-46) y RF-20 comprueba que ya cumple.
  Descartado (la primera corrección, opción B): quitar del índice los ficheros que copian un conjunto; sacaba el documento que
  el usuario decidió indexar.
- La calibración del 077 rehecha el 2026-11-13: 58 preguntas (33 con respuesta, 25 ajenas), de las 308 de antes; fuera, 269
  filas que el corpus ya lleva, 8 sin respuesta sin confirmar y 13 sin fuente indexada. Ninguna «dominio»: las sin
  respuesta confirmadas del reparto `corpus` están todas en el documento. Formarla tarda 1,2 s. La anterior tenía 233 de
  sus preguntas en el corpus (232 en el documento del maestro), 176 de seis palabras o más. `docs/CALIBRACION_ABSTENCION_077.json`
  queda con el sello del conjunto anterior y `reranker.abstencion` la trata como no calibrada hasta recalibrar (T5).
- Umbral de seis palabras de la comprobación permanente, medido: las coincidencias que no son copia llegan a cinco
  («¿Y «Con proyecto»?» en 38 ficheros, «si no se puede deducir» en un procedimiento, «como va el avance» citada en la 075);
  la copia del caso traía cientos de seis o más. Las más cortas se cuentan (`cortas_sin_comprobar`). Del JSONL de la 076 se
  comprueba el reparto `sellado`: el `corpus` es corpus por decisión del usuario, y lo que de él mide está en la calibración.
- `embeddings.evaluar_recuperador` y `evaluacion_rag._METRICAS_IC`: `hit@10` por pregunta, global y con IC; los resúmenes de
  `tools/asistente_evaluar_rag.py` lo muestran. `decidir`, `_puerta` y la elección de RF-11 no lo leen (RF-23).
- Pruebas en los ficheros que ya había: la comprobación del repositorio entero (RF-20) en `tests/test_auditoria_raiz.py`, que
  ya es de gobierno (corre en cada commit), con el documento del maestro dentro del 077; RF-19 (sorteada y sobre la
  calibración real), el detector y las anclas reales de RF-18 en
  `tests/test_asistente_corpus_ampliado.py`; RF-21 y RF-22 en `tests/test_ordenes_maestro.py`, con el almacén por
  `CSG_ASISTENTE_REAL` (en `VARIABLES` de la puerta y en `config/suite_completa.example.json`), copiado a una carpeta temporal
  (unos 20 s con `preparar_corpus`); RF-23 en `tests/test_asistente_embeddings.py`.
- Fuera de lo que comprueba RF-21, medido el 2026-11-13: 10 de las 40 órdenes fijas de prueba (027:RF-66) están en el
  entrenamiento integral por `ordenes_fijas.FRASES` (070:RF-75); la integral no las mide, solo las veda en lo añadido.
