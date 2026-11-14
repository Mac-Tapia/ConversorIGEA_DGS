# Tareas 097

- [x] T1. Modelo y prefijos de los vectores por ficha, sin mezclar modelos en un índice. (RF-1, RF-2, RF-3)
      Hecho cuando: `pytest -q tests/test_asistente_vectores_097.py tests/test_asistente_indice.py` en verde.
- [x] T2. Elección del modelo con la calibración en `asistente_evaluar_rag.py` (`--modelo-vectores`, `--comparar`). (RF-4)
      Hecho cuando: `pytest -q tests/test_asistente_vectores_097.py` en verde.
- [x] T3. Medición real en la GPU: calibrar los candidatos en 047 y 077, sellar una vez el elegido. (RF-4, RF-5, RF-6, RF-7, RF-8)
      Hecho cuando: el informe está en `docs/` con las métricas de cada candidato y la decisión anotada aquí.
      Hecho el 2026-11-13 (`docs/EVALUACION_VECTORES_097.json`; salidas en `D:/csg/rag_097_20261113`). «Conserva» del
      híbrido con abstención 0,95: en el 047, bge-m3 1,000 [0,946; 1,000], e5-large 0,973 [0,919; 1,000] y nomic 0,811
      [0,676; 1,000]; en el 077, 0,064, 0,059 y 0,047. Por RF-11 ninguno queda fuera (bge-m3 − nomic en el 047:
      [0,000; 0,297]) y decide la memoria (320 frente a 596 y 657 MiB, latencias dentro del 20 %): **sigue
      nomic-embed-text** (RF-6), y la web no cambia. Sellado con nomic: la puerta del reranker pasa en el 047 (Recall@10
      0,974) y falla en el 077 (0,526 → 0,039), así que el 077 no se sirve (RF-7).
- [x] T4. Señales de calibración, elección con intervalo, puntero en uso, métricas con IC, conjunto del operador y
      fuentes movidas; y, ampliada el 2026-11-13, la calibración y el sellado con preguntas que no están en el corpus
      que miden (con el documento del maestro dentro, decisión del usuario, opción A), la calibración del 077 rehecha
      con `tools/asistente_indice_ampliado.py conjuntos --rehacer-calibracion`, la comprobación permanente de los
      conjuntos del RAG y del intérprete, y hit@10. (RF-9, RF-10, RF-11, RF-12, RF-13, RF-14, RF-15,
      RF-16, RF-17, RF-18, RF-19, RF-20, RF-21, RF-22, RF-23)
      Hecho cuando: `pytest -q tests/test_asistente_vectores_097_t3.py tests/test_asistente_vectores_097.py
      tests/test_asistente_reranker.py tests/test_asistente_corpus_ampliado.py tests/test_auditoria_raiz.py
      tests/test_ordenes_maestro.py tests/test_asistente_embeddings.py tests/test_preguntas_entregables.py` en verde, con
      `CSG_ASISTENTE_REAL` y sin ella (la de RF-21 se omite nombrándola, RF-22).
- [ ] T5. Poner en uso el elegido con `--poner-en-uso … --aplicar` y recalcular los vectores de la web, cuando lo decida el
      usuario. (RF-5, RF-7, RF-14, RF-19)
      Hecho cuando: antes, con la calibración del 077 rehecha sin las preguntas que el corpus ya lleva (RF-19), se
      recalibra la abstención y se sella una vez por modelo de vectores en la GPU, y se repite la elección de RF-11; las
      cifras van a `docs/EVALUACION_VECTORES_097.json` (las de la T3 en el 077 se midieron con la calibración anterior,
      que tenía 233 de sus 308 preguntas en el corpus). Por modelo `<m>`
      (nomic-embed-text, bge-m3, jeffh/intfloat-multilingual-e5-large:f16), con `S=D:/csg/rag_097_limpio`:
      `python tools/asistente_evaluar_rag.py --corpus 077 --calibrar --modelo-vectores <m> --datos $S/m_<m> --salida $S/calibra_077_<m>.json`
      y `python tools/asistente_evaluar_rag.py --corpus 077 --sellado --modelo-vectores <m> --calibracion $S/calibra_077_<m>.json --datos $S/m_<m> --salida $S/sellado_077_<m>.json`;
      después `python tools/asistente_evaluar_rag.py --elegir D:/csg/rag_097_20261113/calibra_047_*.json $S/calibra_077_*.json --salida $S/eleccion_097.json`.
      Y luego `vectores_en_uso.json` existe en la carpeta del asistente y la web responde con el modelo elegido.
