# Tareas — Spec 106

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. Espera del turno con plazo y dueño; la sesión de pytest toma el turno de la máquina; volcado de pila; marca
      `gpu` sola; la puerta cuenta la salida sin turno como fallo. (RF-1 a RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_turno_gpu_de_la_suite.py` en verde.
- [x] T3. Los hijos de las pruebas cargan el src del árbol que se prueba; la puerta corre todo si cambia lo común.
      (RF-12, RF-13)
      Hecho cuando: `tests/test_turno_gpu_de_la_suite.py` (106:RF-12) y `tests/test_puerta_calidad.py` (106:RF-13) en verde, y en rojo con el conftest anterior en un
      worktree.
- [x] T5. El entorno de DIgSILENT no hereda otro paquete del conversor por PYTHONPATH. (RF-14)
      Hecho cuando: `tests/test_powerfactory_versiones.py` (103:RF-6, sin tocar) y `tests/test_turno_gpu_de_la_suite.py`
      (106:RF-14) en verde.
- [x] T4. El resultado de la suite guarda las más lentas y avisa de las que pasan del umbral del volcado. (RF-15)
      Hecho cuando: `tests/test_puerta_calidad.py` (106:RF-15) en verde.
- [ ] T2. Suite completa con un entrenamiento esperando su turno: las 62 de 10a80812 en verde, sin omitidas. (RF-1, RF-4)
      Hecho cuando: la suite completa corrida sola da 0 fallidas, 0 omitidas y 0 errores, y el entrenamiento esperó.
