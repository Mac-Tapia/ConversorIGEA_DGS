# Tareas 101

- [x] T1. Selección de las SED que se cambian solas, sin repetir lo aplicado. (RF-1, RF-4, RF-6, RF-12)
      Hecho cuando: `pytest -q tests/test_transformadores_automaticos.py` en verde.
- [x] T2. Rondas de cambio y recalibración dentro de la calibración aplicada, con su Registro y su resultado. (RF-2, RF-3,
      RF-5, RF-7, RF-8, RF-9, RF-10, RF-11, RF-13)
      Hecho cuando: `pytest -q tests/test_transformadores_automaticos.py` en verde.
- [ ] T3. [DIgSILENT] Calibración de CA101 + CHN102 desde la web: termina válida y sin `iopt_lev`, sin pulsar ningún
      botón. (RF-2, RF-3)
      Hecho cuando: el informe de la última ronda da `cuadrado` y la relectura de las cargas cuadra.
