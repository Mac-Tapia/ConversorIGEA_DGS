# Tareas — Spec 079

- [x] T1 La prueba `sellada_079`, escrita de una vez y antes del currículo, y la sellada anterior sin decidir. (RF-38 a RF-48, RF-60, RF-64)
  Hecho cuando: `pytest -q tests/test_afinado_ordenes.py -k sellada` y `tests/test_asistente_maestro.py` en verde.
- [x] T2 Codificador partido, afinado con parada por selección y artefacto. (RF-1 a RF-24)
  Hecho cuando: `pytest -q tests/test_afinado_ordenes.py -k "afinado or artefacto"` en verde.
- [x] T3 Pérdida contrastiva, grupos, lotes y confusiones. (RF-25 a RF-30)
  Hecho cuando: `pytest -q tests/test_afinado_ordenes.py -k contrastiva` en verde.
- [x] T4 Currículo de las tareas flojas. (RF-31 a RF-37)
  Hecho cuando: `pytest -q tests/test_afinado_ordenes.py -k curriculo` en verde.
- [x] T5 Validación cruzada con afinado y regla de Ollama elegida en desarrollo. (RF-49 a RF-57)
  Hecho cuando: `pytest -q tests/test_afinado_ordenes.py -k "cruzada or regla"` en verde.
- [x] T6 Herramienta, protocolo y caché local. (RF-58, RF-59, RF-61 a RF-63)
  Hecho cuando: `pytest -q tests/test_afinado_ordenes.py -k "herramienta or cache"` en verde.
- [x] T7 [DIgSILENT] El integrador lanza el afinado en la GPU y mide; no usa DIgSILENT, pero es la tarea de la ejecución real.
  Hecho cuando: el registro deja la decisión con las dos selladas, la medida fuera de grupo y la rejilla de la regla de Ollama.
      Hecho el 2026-11-07 (sesión 63935039): `tools/asistente_entrenar.py --integral --afinar --validacion-cruzada --output-json output/asistente_integral_20261106.json`, en CUDA. Transformer: candidato `f8f7472b…` RECHAZADO (76 fallos de puerta), elegido destilado semilla 23 con 29 confirmadas. Decide el examen del maestro (`examen_maestro_085`, 110 órdenes; 43 humanas distintas de 200, no deciden): tarea 0,973 y F1 0,918, bajo 0,98 y 0,95. Selladas: 070 (2068 filas) 0,862 y 0,687; 079 (2104, decide) 0,827 y 0,830. Fuera de grupo (5 vueltas, 43 humanas): 0,721 y 0,750, frente a 0,953 y 0,848 del modelo en uso, que se queda. Rechazo en 206 reservados: 0,927 recogido, 0,0 colado. Regla de Ollama («ninguna entre las 3 primeras opciones, piso 0,3»): no decide, 1,9 % reservados a Ollama, 3,7 % frenadas, cumple. Clasificador de informes PROMOVIDO, `reg-b1682ecdc03e2a13` (tipo 1,0, subtipo 0,980, 151).
