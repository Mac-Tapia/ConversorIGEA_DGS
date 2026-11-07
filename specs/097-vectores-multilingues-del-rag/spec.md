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
