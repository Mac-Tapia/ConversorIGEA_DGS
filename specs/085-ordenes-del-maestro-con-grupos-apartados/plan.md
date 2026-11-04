# Plan — Spec 085

- `asistente/ordenes_maestro.py` (nuevo): `leer` valida y cuenta (RF-1 a RF-5); `repartir` agrupa con
  `validacion_cruzada.agrupar_familias` y aparta por huella (RF-6 a RF-9); `ampliar` añade al corpus el examen y el entrenamiento,
  descarta lo que choca y quita lo que toca el examen (RF-10 a RF-16); `puerta_de_ordenes` elige el conjunto que decide (RF-19 a RF-22).
  Alternativa descartada: escribir en `ejemplos.jsonl`; lo leen como humano `transformer.ejemplos_reales`, la vigilancia y las señales.
- `destilacion_integral.py`: `preparar_corpus(..., ordenes_maestro=())` llama a `ampliar` tras sellar; `leer_corpus` acepta `ninguna`
  del maestro; `entrenar_destilacion` mide el examen y `decidir_promocion` recibe la medida del maestro (RF-17 a RF-23).
- `tools/asistente_destilar.py` y `tools/asistente_entrenar.py`: leen las órdenes del maestro del almacén.
- `clasificador.entrenar_gobernado`: los orígenes en el manifiesto (RF-25).
- `model_registry.py`: `anotar_uso_provisional` añade la decisión a `usos_provisionales.jsonl` junto a los candidatos; no toca `decision.json`,
  que entra en la identidad del candidato, ni `active.json` (RF-26 a RF-28). Alternativa descartada: registrar un candidato copia con la decisión
  `PROMOVIDO` y `approved` verdadero, que falsificaría justo lo que las puertas guardan.
- `modelos_en_uso.py`: `poner_provisional` copia a la versión `prov-…` y mueve el mismo puntero; lo provisional se deduce del puntero (`uso_provisional`),
  sin una marca aparte que se quede atrás al volver (RF-29). `aviso_provisional` da el texto con las cifras del registro (RF-30).
- `plan.py`, `web/services.py`, `web/app.py`: `Plan.espera_confirmacion` decide qué se lanza solo; la confianza no entra (RF-31, RF-32).
- `tools/asistente_modelo_provisional.py`: `ver`, `poner`, `volver` (RF-33). `Asistente.tsx`: el aviso y el botón de volver (RF-30).
- Pruebas sintéticas en `tests/test_ordenes_maestro.py`, sin leer el almacén real; las puertas no cambian (RF-23).
