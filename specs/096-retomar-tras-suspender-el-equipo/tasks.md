# Tareas 096

- [x] T1. `suspension.py` y el trabajo que no deja suspender por inactividad y se repite una vez tras una suspensión.
      (RF-1, RF-2, RF-3, RF-4)
      Hecho cuando: `pytest -q tests/test_retomar_tras_suspender.py` en verde.
- [x] T2. Relanzar al arrancar la web el último «Recalibrar» interrumpido de cada espacio, una vez. (RF-5, RF-6, RF-7)
      Hecho cuando: `pytest -q tests/test_retomar_tras_suspender.py` en verde.
- [ ] T3. [DIgSILENT] Una recalibración de Pisco con el equipo suspendido y despertado a mitad termina sola. (RF-2)
      Hecho cuando: el trabajo «Recalibrar» termina sin relanzarlo a mano.
