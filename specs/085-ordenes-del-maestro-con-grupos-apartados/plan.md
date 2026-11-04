# Plan — Spec 085

- `asistente/ordenes_maestro.py` (nuevo): `leer` valida y cuenta (RF-1 a RF-5); `repartir` agrupa con
  `validacion_cruzada.agrupar_familias` y aparta por huella (RF-6 a RF-9); `ampliar` añade al corpus el examen y el entrenamiento,
  descarta lo que choca y quita lo que toca el examen (RF-10 a RF-16); `puerta_de_ordenes` elige el conjunto que decide (RF-19 a RF-22).
  Alternativa descartada: escribir en `ejemplos.jsonl`; lo leen como humano `transformer.ejemplos_reales`, la vigilancia y las señales.
- `destilacion_integral.py`: `preparar_corpus(..., ordenes_maestro=())` llama a `ampliar` tras sellar; `leer_corpus` acepta `ninguna`
  del maestro; `entrenar_destilacion` mide el examen y `decidir_promocion` recibe la medida del maestro (RF-17 a RF-23).
- `tools/asistente_destilar.py` y `tools/asistente_entrenar.py`: leen las órdenes del maestro del almacén.
- `clasificador.entrenar_gobernado`: los orígenes en el manifiesto (RF-25).
- Pruebas sintéticas en `tests/test_ordenes_maestro.py`, sin leer el almacén real; las puertas no cambian (RF-23).
