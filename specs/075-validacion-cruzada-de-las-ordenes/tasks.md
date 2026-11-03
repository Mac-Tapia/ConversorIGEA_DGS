# Tareas — Spec 075

- [x] T1 Familias y reparto en vueltas. (RF-1 a RF-9)
  Hecho cuando: `pytest -q tests/test_validacion_cruzada_ordenes.py -k "familia or reparto"` en verde.
- [x] T2 Vueltas, medida fuera de grupo y tareas sin independencia. (RF-10 a RF-20, RF-23 a RF-25)
  Hecho cuando: `pytest -q tests/test_validacion_cruzada_ordenes.py -k "vuelta or independencia"` en verde.
- [x] T3 Modelo final y decisión. (RF-21, RF-22, RF-26 a RF-34, RF-46)
  Hecho cuando: `pytest -q tests/test_validacion_cruzada_ordenes.py -k "final or decision"` en verde.
- [x] T4 Opción de la herramienta. (RF-35, RF-36)
  Hecho cuando: `pytest -q tests/test_validacion_cruzada_ordenes.py -k opcion` en verde.
- [x] T5 Regla de Ollama y su medida. (RF-37 a RF-45)
  Hecho cuando: `pytest -q tests/test_validacion_cruzada_ordenes.py -k ollama` en verde.
- [ ] T6 [DIgSILENT] El integrador lanza `tools/asistente_entrenar.py --integral --validacion-cruzada` en la GPU y mide.
  Hecho cuando: el registro deja la decisión con la medida fuera de grupo y la de la regla de Ollama.
