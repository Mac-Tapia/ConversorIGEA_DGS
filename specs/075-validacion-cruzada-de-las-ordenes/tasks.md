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
- [x] T6 [DIgSILENT] El integrador lanza `tools/asistente_entrenar.py --integral --validacion-cruzada` en la GPU y mide.
  Hecho cuando: el registro deja la decisión con la medida fuera de grupo y la de la regla de Ollama.
      Hecho el 2026-11-07 (sesión 63935039): `tools/asistente_entrenar.py --integral --afinar --validacion-cruzada --output-json output/asistente_integral_20261106.json`, en CUDA. Transformer: candidato `f8f7472b…` RECHAZADO (76 fallos de puerta), elegido destilado semilla 23 con 29 confirmadas. Decide el examen del maestro (`examen_maestro_085`, 110 órdenes; 43 humanas distintas de 200, no deciden): tarea 0,973 y F1 0,918, bajo 0,98 y 0,95. Selladas: 070 (2068 filas) 0,862 y 0,687; 079 (2104, decide) 0,827 y 0,830. Fuera de grupo (5 vueltas, 43 humanas): 0,721 y 0,750, frente a 0,953 y 0,848 del modelo en uso, que se queda. Rechazo en 206 reservados: 0,927 recogido, 0,0 colado. Regla de Ollama («ninguna entre las 3 primeras opciones, piso 0,3»): no decide, 1,9 % reservados a Ollama, 3,7 % frenadas, cumple. Clasificador de informes PROMOVIDO, `reg-b1682ecdc03e2a13` (tipo 1,0, subtipo 0,980, 151).
