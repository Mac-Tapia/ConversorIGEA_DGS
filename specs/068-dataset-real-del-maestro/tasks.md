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
- [ ] T7 Reentrenar en la GPU con el corpus nuevo y leer la decisión del registro.
  Hecho cuando: el informe del integrador da el estado del candidato por familia y sus denominadores.
- [x] T8 Revisión del operador: que marque `revision.xlsx` y se importe.
  Hecho cuando: `importar` anota lo marcado y `ejemplos` crece solo con esas filas.
  Hecho el 2026-11-02: el operador confirmó las 42 filas: 39 importadas, 3 ya estaban, 0 corregidas, 0 contradicciones.
  `ejemplos.jsonl` queda con 44 confirmadas, 42 textos únicos; no entrenan (070:RF-76). Evidencia del integrador; los textos, fuera de git.
