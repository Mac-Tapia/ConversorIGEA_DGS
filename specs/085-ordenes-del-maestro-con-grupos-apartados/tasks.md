# Tareas — Spec 085

- [x] T1 Lectura y validación de las órdenes del maestro. (RF-1 a RF-5)
  Hecho cuando: `pytest -q tests/test_ordenes_maestro.py -k leer` en verde.
- [x] T2 Grupos apartados y corpus. (RF-6 a RF-16)
  Hecho cuando: `pytest -q tests/test_ordenes_maestro.py -k "reparto or corpus"` en verde.
- [x] T3 Tres cifras y puerta de órdenes. (RF-17 a RF-24)
  Hecho cuando: `pytest -q tests/test_ordenes_maestro.py -k puerta` en verde.
- [x] T4 Orígenes en el manifiesto del clasificador. (RF-25)
  Hecho cuando: `pytest -q tests/test_ordenes_maestro.py -k clasificador` en verde.
- [x] T5 Órdenes del maestro en el almacén local para las 48 tareas. (RF-1, RF-7)
  Hecho cuando: `tools/asistente_destilar.py preparar` las lee sin rechazos y cada tarea con 2 familias o más tiene examen.
  Hecho el 2026-11-03: 423 órdenes válidas (387 de las 48 tareas, 36 «ninguna»), 0 rechazadas; examen 110 órdenes de las 48 tareas, 308 entrenan, 5 descartadas por chocar con lo que mide. Los textos, fuera de git.
- [x] T6 Entrenar en la GPU con el corpus nuevo y leer la decisión. (RF-17 a RF-22)
  Hecho cuando: el informe del integrador da las tres cifras con sus denominadores y qué conjunto decidió.
      Hecho el 2026-11-07 (sesión 63935039): `tools/asistente_entrenar.py --integral --afinar --validacion-cruzada --output-json output/asistente_integral_20261106.json`, en CUDA. Transformer: candidato `f8f7472b…` RECHAZADO (76 fallos de puerta), elegido destilado semilla 23 con 29 confirmadas. Decide el examen del maestro (`examen_maestro_085`, 110 órdenes; 43 humanas distintas de 200, no deciden): tarea 0,973 y F1 0,918, bajo 0,98 y 0,95. Selladas: 070 (2068 filas) 0,862 y 0,687; 079 (2104, decide) 0,827 y 0,830. Fuera de grupo (5 vueltas, 43 humanas): 0,721 y 0,750, frente a 0,953 y 0,848 del modelo en uso, que se queda. Rechazo en 206 reservados: 0,927 recogido, 0,0 colado. Regla de Ollama («ninguna entre las 3 primeras opciones, piso 0,3»): no decide, 1,9 % reservados a Ollama, 3,7 % frenadas, cumple. Clasificador de informes PROMOVIDO, `reg-b1682ecdc03e2a13` (tipo 1,0, subtipo 0,980, 151).
- [x] T7 Modelo en uso provisional por decisión del usuario, sin aprobarlo: registro, puntero, avisos y herramienta. (RF-26 a RF-33)
  Hecho cuando: `pytest -q tests/test_modelo_provisional.py` en verde. El usuario lo aplica con `tools/asistente_modelo_provisional.py poner`.
