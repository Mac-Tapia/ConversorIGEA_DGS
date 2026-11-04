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
- [ ] T6 Entrenar en la GPU con el corpus nuevo y leer la decisión. (RF-17 a RF-22)
  Hecho cuando: el informe del integrador da las tres cifras con sus denominadores y qué conjunto decidió.
