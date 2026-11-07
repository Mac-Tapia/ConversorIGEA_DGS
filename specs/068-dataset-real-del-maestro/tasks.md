# Tareas — Spec 068

- [x] T1 Herramienta `extraer`. (RF-1 a RF-9)
  Hecho cuando: `pytest -q tests/test_maestro_real.py -k extraer` en verde.
- [x] T2 Herramienta `exportar` e `importar`. (RF-10 a RF-20)
  Hecho cuando: `pytest -q tests/test_maestro_real.py -k revision` en verde.
- [x] T3 Lectura y validación de las etiquetas. (RF-21 a RF-24)
  Hecho cuando: `pytest -q tests/test_maestro_real.py -k etiqueta` en verde.
- [x] T4 Etiquetado del maestro sobre los textos reales, en el almacén local. (RF-21)
  Hecho cuando: `<almacén>/maestro_real/etiquetas.jsonl` cubre todos los textos extraídos y `exportar` crea la revisión.
- [x] T5 Segunda pasada del corpus. (RF-25 a RF-34)
  Hecho cuando: `pytest -q tests/test_maestro_real.py -k corpus` en verde.
- [x] T6 Currículo de estilo real y erratas. (RF-35 a RF-42)
  Hecho cuando: `pytest -q tests/test_maestro_real.py -k curriculo` en verde.
- [x] T7 Reentrenar en la GPU con el corpus nuevo y leer la decisión del registro.
  Hecho cuando: el informe del integrador da el estado del candidato por familia y sus denominadores.
      Hecho el 2026-11-07 (sesión 63935039): `tools/asistente_entrenar.py --integral --afinar --validacion-cruzada --output-json output/asistente_integral_20261106.json`, en CUDA. Transformer: candidato `f8f7472b…` RECHAZADO (76 fallos de puerta), elegido destilado semilla 23 con 29 confirmadas. Decide el examen del maestro (`examen_maestro_085`, 110 órdenes; 43 humanas distintas de 200, no deciden): tarea 0,973 y F1 0,918, bajo 0,98 y 0,95. Selladas: 070 (2068 filas) 0,862 y 0,687; 079 (2104, decide) 0,827 y 0,830. Fuera de grupo (5 vueltas, 43 humanas): 0,721 y 0,750, frente a 0,953 y 0,848 del modelo en uso, que se queda. Rechazo en 206 reservados: 0,927 recogido, 0,0 colado. Regla de Ollama («ninguna entre las 3 primeras opciones, piso 0,3»): no decide, 1,9 % reservados a Ollama, 3,7 % frenadas, cumple. Clasificador de informes PROMOVIDO, `reg-b1682ecdc03e2a13` (tipo 1,0, subtipo 0,980, 151).
- [x] T8 Revisión del operador: que marque `revision.xlsx` y se importe.
  Hecho cuando: `importar` anota lo marcado y `ejemplos` crece solo con esas filas.
  Hecho el 2026-11-02: el operador confirmó las 42 filas: 39 importadas, 3 ya estaban, 0 corregidas, 0 contradicciones.
  `ejemplos.jsonl` queda con 44 confirmadas, 42 textos únicos; no entrenan (070:RF-76). Evidencia del integrador; los textos, fuera de git.
