# Tareas 096

- [x] T1. `suspension.py` y el trabajo que no deja suspender por inactividad y se repite una vez tras una suspensión.
      (RF-1, RF-2, RF-3, RF-4)
      Hecho cuando: `pytest -q tests/test_retomar_tras_suspender.py` en verde.
- [x] T2. Relanzar al arrancar la web el último «Recalibrar» interrumpido de cada espacio, una vez. (RF-5, RF-6, RF-7)
      Hecho cuando: `pytest -q tests/test_retomar_tras_suspender.py` en verde.
- [ ] T3. [DIgSILENT] Una recalibración de Pisco con el equipo suspendido y despertado a mitad termina sola. (RF-2)
      Hecho cuando: el trabajo «Recalibrar» termina sin relanzarlo a mano.

Avance P21 del 2026-11-08, sin cerrar T3: diario real producido por servidores y trabajadores propios,
caída abrupta, cancelación persistida, exclusión de un hijo vivo por PID/creación, dos relanzadores,
rechazo de prevalidación recuperable y monitor del lifecycle con parada esperada antes de shutdown.
Pruebas: `tests/test_trabajos_interrumpidos.py` y `tests/test_retomar_tras_suspender.py`.
Evidencia: `D:/converter/auditorias/diagnostico_produccion_20261107_56172510/implementacion/paralelo_p21_20261108/`.
El consumidor de calibración está sustituido en estas pruebas de recuperación. No hubo motor,
licencia ni suspensión física; siguen pendientes la idempotencia nativa y el criterio íntegro T3.
