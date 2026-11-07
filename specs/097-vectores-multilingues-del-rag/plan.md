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
