# Tareas — Spec 106

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. Espera del turno con plazo y dueño; la sesión de pytest toma el turno de la máquina; volcado de pila; marca
      `gpu` sola; la puerta cuenta la salida sin turno como fallo. (RF-1 a RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_turno_gpu_de_la_suite.py` en verde.
- [ ] T2. Suite completa con un entrenamiento esperando su turno: las 62 de 10a80812 en verde, sin omitidas. (RF-1, RF-4)
      Hecho cuando: la suite completa corrida sola da 0 fallidas, 0 omitidas y 0 errores, y el entrenamiento esperó.
